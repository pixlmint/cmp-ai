local conf = require('cassandra_ai.config')
local logger = require('cassandra_ai.logger')

local M = {}

-- Module state
local generation = 0
local current_job = nil
local debounce_timer = nil
local completions = {}
local current_index = 0
local is_visible = false
local cursor_pos = nil
local bufnr = nil
local internal_move = false
local current_request_id = nil
local pending_rejected = {}

local auto_triggered = false
local pending_validation = nil -- { completions, trigger_pos, trigger_bufnr, trigger_line_text }
local validation_idle_timer = nil

local validate_or_defer, show_validated_completion, reset_validation_idle_timer

local ns = vim.api.nvim_create_namespace('cassandra_ai_inline')

-- ---------------------------------------------------------------------------
-- Request Logging
-- ---------------------------------------------------------------------------

--- Generate a UUID v4
local function generate_uuid()
  local template = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
  return string.gsub(template, '[xy]', function(c)
    local v = (c == 'x') and math.random(0, 0xf) or math.random(8, 0xb)
    return string.format('%x', v)
  end)
end

--- Safely serialize provider config for logging
--- Only logs provider.params (never api_key or headers)
--- Replaces functions with type metadata
local function safe_serialize_config(params)
  if type(params) ~= 'table' then
    return params
  end

  local result = {}
  for key, value in pairs(params) do
    local value_type = type(value)
    if value_type == 'function' then
      result[key] = { __type = 'function' }
    elseif value_type == 'table' then
      result[key] = safe_serialize_config(value) -- Recursive
    elseif value_type == 'string' or value_type == 'number' or value_type == 'boolean' then
      result[key] = value
    elseif value_type == 'nil' then
      -- Skip nil values
    else
      -- Thread, userdata, etc.
      result[key] = { __type = value_type }
    end
  end
  return result
end

-- ---------------------------------------------------------------------------
-- Virtual text rendering
-- ---------------------------------------------------------------------------

local function clear_ghost_text()
  if bufnr and vim.api.nvim_buf_is_valid(bufnr) then
    vim.api.nvim_buf_clear_namespace(bufnr, ns, 0, -1)
  end
  is_visible = false
end

local function render_ghost_text(text)
  if not bufnr or not vim.api.nvim_buf_is_valid(bufnr) then
    return
  end
  clear_ghost_text()
  if not text or text == '' then
    return
  end

  require('cassandra_ai.integrations').close_completion_menus()

  local lines = vim.split(text, '\n', { plain = true })
  local row = cursor_pos[1] - 1 -- 0-indexed
  local col = cursor_pos[2]

  local virt_text = { { lines[1], 'CassandraAiInline' } }
  local virt_lines = nil

  if #lines > 1 then
    virt_lines = {}
    for i = 2, #lines do
      table.insert(virt_lines, { { lines[i], 'CassandraAiInline' } })
    end
  end

  vim.api.nvim_buf_set_extmark(bufnr, ns, row, col, {
    virt_text = virt_text,
    virt_text_pos = 'inline',
    virt_lines = virt_lines,
  })
  is_visible = true
end

-- ---------------------------------------------------------------------------
-- Request management
-- ---------------------------------------------------------------------------

local function cancel_request()
  if current_job then
    pcall(function()
      current_job:shutdown()
    end)
    current_job = nil
  end
end

local function cancel_debounce()
  if debounce_timer then
    debounce_timer:stop()
    debounce_timer:close()
    debounce_timer = nil
  end
end

-- ---------------------------------------------------------------------------
-- Response post-processing
-- ---------------------------------------------------------------------------

--- Strip lines from the edges of a completion that overlap with surrounding context.
--- Some models echo back parts of the before/after text in their response.
local function strip_context_overlap(text, lines_before, lines_after)
  local lines = vim.split(text, '\n', { plain = true })
  if #lines == 0 then
    return text
  end

  local before_split = vim.split(lines_before, '\n', { plain = true })
  local after_split = vim.split(lines_after, '\n', { plain = true })

  local before_set = {}
  for _, line in ipairs(before_split) do
    local trimmed = vim.trim(line)
    if trimmed ~= '' then
      before_set[trimmed] = true
    end
  end

  local after_set = {}
  for _, line in ipairs(after_split) do
    local trimmed = vim.trim(line)
    if trimmed ~= '' then
      after_set[trimmed] = true
    end
  end

  -- Strip leading lines that appear in before context
  local start_strip = 0
  for i = 1, #lines do
    local trimmed = vim.trim(lines[i])
    if trimmed ~= '' and before_set[trimmed] then
      start_strip = i
    else
      break
    end
  end

  -- Strip trailing lines that appear in after context.
  -- Allow short trailing lines (e.g. }, ), ]) that aren't in after_set
  -- to be bridged over, since the after context may have been truncated.
  local tail_skip = 0
  for i = #lines, start_strip + 1, -1 do
    local trimmed = vim.trim(lines[i])
    if trimmed == '' or after_set[trimmed] then
      break
    elseif #trimmed <= 2 then
      tail_skip = tail_skip + 1
      if tail_skip > 2 then
        tail_skip = 0
        break
      end
    else
      tail_skip = 0
      break
    end
  end

  local end_strip = 0
  for i = #lines - tail_skip, start_strip + 1, -1 do
    local trimmed = vim.trim(lines[i])
    if trimmed == '' or after_set[trimmed] then
      end_strip = end_strip + 1
    else
      break
    end
  end

  -- Only count tail_skip if we found actual after-context matches
  if end_strip > 0 then
    end_strip = end_strip + tail_skip
  end

  if start_strip == 0 and end_strip == 0 then
    return text
  end

  local result = {}
  for i = start_strip + 1, #lines - end_strip do
    result[#result + 1] = lines[i]
  end

  -- Don't strip everything - return original if nothing would remain
  if #result == 0 then
    return text
  end

  return table.concat(result, '\n')
end

--- Strip markdown code fences some providers wrap responses in.
local function strip_markdown_fences(text)
  local lines = vim.split(text, '\n', { plain = true })
  if #lines < 2 then
    return text
  end
  if lines[1]:match('^```') then
    table.remove(lines, 1)
    if #lines > 0 then
      lines[1] = lines[1]:gsub('^%s+', '')
    end
  end
  if #lines > 0 and lines[#lines]:match('^```') then
    table.remove(lines, #lines)
  end
  return table.concat(lines, '\n')
end

--- Post-process completion candidates: strip fences and context overlap.
local function postprocess_completions(data, lines_before, lines_after)
  for i, item in ipairs(data) do
    data[i] = strip_context_overlap(strip_markdown_fences(item), lines_before, lines_after)
  end
  return data
end

-- ---------------------------------------------------------------------------
-- Deferred validation
-- ---------------------------------------------------------------------------

local function cancel_validation_timer()
  if validation_idle_timer then
    validation_idle_timer:stop()
    validation_idle_timer:close()
    validation_idle_timer = nil
  end
end

local function clear_validation_state()
  auto_triggered = false
  pending_validation = nil
  cancel_validation_timer()
end

--- Get text typed since the trigger position by comparing current buffer state.
--- Returns nil if cursor moved to a different line or backward past trigger column.
local function compute_typed_since_trigger(pv)
  if vim.api.nvim_get_current_buf() ~= pv.trigger_bufnr then
    return nil
  end
  local cur = vim.api.nvim_win_get_cursor(0)
  if cur[1] ~= pv.trigger_pos[1] then
    return nil
  end
  if cur[2] < pv.trigger_pos[2] then
    return nil
  end
  local line = vim.api.nvim_buf_get_lines(pv.trigger_bufnr, cur[1] - 1, cur[1], false)[1] or ''
  return line:sub(pv.trigger_pos[2] + 1, cur[2])
end

--- Parse an overlap config string into (words, chars).
--- Format: [N][+M] where N = whole words, M = extra chars (or fraction if < 1).
--- Returns words (int or nil), chars (number or nil).
local function parse_overlap(s)
  if not s or s == '' then
    return nil, nil
  end
  local words, chars
  local plus = s:find('+', 1, true)
  if plus then
    local before = s:sub(1, plus - 1)
    local after = s:sub(plus + 1)
    words = before ~= '' and tonumber(before) or nil
    chars = after ~= '' and tonumber(after) or nil
  else
    words = tonumber(s)
  end
  return words, chars
end

--- Classify a character into a word category (matching vim's `w` motion).
--- Uses iskeyword to distinguish keyword chars from punctuation.
--- Returns: 1 = keyword, 2 = non-keyword/non-whitespace (punctuation), 3 = whitespace
local function char_class(ch)
  if ch:match('%s') then
    return 3
  end
  if vim.fn.match(ch, '\\k') == 0 then
    return 1
  end
  return 2
end

--- Walk text and return a list of word spans: { {start, end_}, ... }
--- A "word" is a maximal run of same-class non-whitespace characters,
--- matching vim's `w` motion (keyword vs punctuation are separate words).
local function find_words(text)
  local result = {}
  local len = #text
  local i = 1
  while i <= len do
    local ch = text:sub(i, i)
    local cls = char_class(ch)
    if cls ~= 3 then
      local start = i
      i = i + 1
      while i <= len do
        local c2 = text:sub(i, i)
        if char_class(c2) ~= cls then
          break
        end
        i = i + 1
      end
      result[#result + 1] = { start, i - 1 }
    else
      i = i + 1
    end
  end
  return result
end

--- Compute how many characters of a completion the user must type before showing it.
--- Words are defined by vim's iskeyword (same as `w` motion), so `this.call(arg`
--- is 5 words: `this`, `.`, `call`, `(`, `arg`.
--- Returns nil if the completion text doesn't have enough content (fall back to idle timer).
local function compute_overlap_threshold(text, overlap_str)
  local words_n, chars = parse_overlap(overlap_str)

  -- "+M" with no words: M is total characters
  if not words_n then
    return chars
  end

  local word_spans = find_words(text)

  if #word_spans < words_n then
    return nil -- not enough words
  end

  -- Position after N-th word
  local last_word_end = word_spans[words_n][2]

  -- No +M: require N complete words plus any trailing whitespace
  if not chars then
    -- Find start of next word (or end of text) to include trailing whitespace
    if #word_spans > words_n then
      return word_spans[words_n + 1][1] - 1
    end
    -- No next word — check if there's trailing whitespace after last word
    if last_word_end < #text then
      return #text
    end
    return nil -- word isn't "complete" (no trailing space/punctuation boundary)
  end

  -- Need a next word to apply +M against
  if #word_spans <= words_n then
    return nil
  end

  local next_span = word_spans[words_n + 1]
  local next_word_start = next_span[1]
  local next_word_len = next_span[2] - next_span[1] + 1

  local extra
  if chars > 0 and chars < 1 then
    extra = math.ceil(chars * next_word_len)
  else
    extra = math.min(math.floor(chars), next_word_len)
  end

  return (next_word_start - 1) + extra
end

-- Expose for testing
M._compute_overlap_threshold = compute_overlap_threshold

--- Trim the typed prefix from all completion candidates, filter out empty results.
local function trim_completions(comps, prefix)
  local result = {}
  for _, c in ipairs(comps) do
    if c:sub(1, #prefix) == prefix then
      local trimmed = c:sub(#prefix + 1)
      if trimmed ~= '' then
        result[#result + 1] = trimmed
      end
    end
  end
  return result
end

show_validated_completion = function(pv, typed)
  local trimmed = trim_completions(pv.completions, typed)
  if #trimmed == 0 then
    logger.trace('deferred: all completions empty after trimming')
    clear_validation_state()
    return
  end

  local cur = vim.api.nvim_win_get_cursor(0)
  cursor_pos = cur
  completions = trimmed
  current_index = 1
  clear_validation_state()
  render_ghost_text(completions[current_index])
end

validate_or_defer = function()
  local pv = pending_validation
  if not pv then
    return
  end

  local typed = compute_typed_since_trigger(pv)
  if typed == nil then
    logger.trace('deferred: cursor moved off trigger line, discarding')
    if pv.request_id then
      require('cassandra_ai.telemetry'):log_acceptance(pv.request_id, { accepted = false, rejection_reason = 'cursor_moved' })
    end
    clear_validation_state()
    return
  end

  -- Check that what the user typed is a prefix of at least one completion
  local has_match = false
  for _, c in ipairs(pv.completions) do
    if c:sub(1, #typed) == typed then
      has_match = true
      break
    end
  end

  if not has_match then
    logger.trace('deferred: typed "' .. typed .. '" mismatches all completions, discarding')
    if pv.request_id then
      require('cassandra_ai.telemetry'):log_acceptance(pv.request_id, { accepted = false, rejection_reason = 'mismatch', typed_text = typed })
    end
    clear_validation_state()
    return
  end

  -- Check if past the validation threshold
  local overlap = conf:get('inline').auto_trigger_overlap or '1+1'
  local threshold = compute_overlap_threshold(pv.completions[1], overlap)
  if threshold and #typed >= threshold then
    logger.info('deferred: threshold reached (' .. #typed .. '>=' .. threshold .. '), showing completion')
    show_validated_completion(pv, typed)
    return
  end

  -- Not enough typed yet — (re)start idle timer
  reset_validation_idle_timer()
end

reset_validation_idle_timer = function()
  cancel_validation_timer()
  validation_idle_timer = vim.uv.new_timer()
  local idle_ms = conf:get('inline').deferred_idle_ms

  local function show_completion()
    local pv = pending_validation
    if not pv then
      return false
    end
    local typed = compute_typed_since_trigger(pv) or ''
    show_validated_completion(pv, typed)
    return true
  end

  if idle_ms == 0 then
    show_completion()
  elseif idle_ms > -1 then
    validation_idle_timer:start(
      idle_ms,
      0,
      vim.schedule_wrap(function()
        if show_completion() then
          logger.info('deferred: idle timer fired, showing completion')
        end
      end)
    )
  end
end

-- ---------------------------------------------------------------------------
-- Completion pipeline
-- ---------------------------------------------------------------------------

--- Resolve the prompt formatter from model info and config.
local function resolve_formatter(model_info)
  local formatters = require('cassandra_ai.prompt_formatters')
  local fmt = (model_info and model_info.formatter) or conf:get('formatter') or formatters.fim
  if type(fmt) == 'string' then
    if formatters[fmt] then
      fmt = formatters[fmt]
    else
      logger.warn('config: unknown formatter "' .. fmt .. '", falling back to fim')
      fmt = formatters.fim
    end
  end
  return fmt
end

--- Handle a completion response from the provider.
local function handle_completion_response(req, data)
  current_job = nil
  local elapsed_ms = (os.clock() - req.start_time) * 1000
  local telemetry = require('cassandra_ai.telemetry')
  telemetry:log_response(req.request_id, {
    response_raw = data,
    response_time_ms = elapsed_ms,
  })

  if req.gen ~= generation then
    logger.trace('on_complete() -> discarding: stale generation')
    return
  end
  if not vim.api.nvim_buf_is_valid(bufnr) then
    logger.trace('on_complete() -> discarding: buffer invalid')
    clear_validation_state()
    return
  end
  if vim.fn.mode() ~= 'i' then
    logger.trace('on_complete() -> discarding: left insert mode')
    clear_validation_state()
    return
  end

  local cur = vim.api.nvim_win_get_cursor(0)
  local ic = conf:get('inline')
  local use_deferred = auto_triggered and ic.deferred_validation

  if use_deferred then
    if cur[1] ~= cursor_pos[1] then
      logger.trace('on_complete() -> discarding: cursor moved to different line')
      clear_validation_state()
      return
    end
  else
    if cur[1] ~= cursor_pos[1] or cur[2] ~= cursor_pos[2] then
      logger.trace('on_complete() -> discarding: cursor moved')
      return
    end
  end

  vim.api.nvim_exec_autocmds({ 'User' }, {
    pattern = 'CassandraAiRequestComplete',
  })

  if not data or #data == 0 then
    logger.trace('on_complete() -> no completions returned')
    clear_validation_state()
    return
  end

  postprocess_completions(data, req.before, req.after)

  logger.info(string.format('completion received: %d item(s) in %.0fms', #data, elapsed_ms))

  if use_deferred then
    pending_validation = {
      completions = data,
      trigger_pos = cursor_pos,
      trigger_bufnr = bufnr,
      trigger_line_text = vim.api.nvim_buf_get_lines(bufnr, cursor_pos[1] - 1, cursor_pos[1], false)[1] or '',
      request_id = current_request_id,
    }
    logger.trace('on_complete() -> deferred: stored ' .. #data .. ' completion(s) for validation')
    validate_or_defer()
  else
    completions = data
    current_index = 1
    render_ghost_text(completions[current_index])
  end
end

--- Build prompt and send the completion request.
local function dispatch_request(req, service, fmt, model_info, additional_context)
  if req.gen ~= generation then
    return
  end
  req.start_time = os.clock()
  local prompt_data = fmt(req.before, req.after, { filetype = req.ft, rejected_completions = req.rejected }, additional_context)

  local provider = conf:get('provider')
  require('cassandra_ai.telemetry'):log_request(req.request_id, {
    cwd = vim.fn.getcwd(),
    filename = vim.api.nvim_buf_get_name(0),
    filetype = req.ft,
    cursor = { line = cursor_pos[1], col = cursor_pos[2] },
    lines_before = req.before,
    lines_after = req.after,
    provider = provider.name,
    provider_config = safe_serialize_config(provider.params),
    model = model_info and model_info.model,
    prompt_data = prompt_data,
    additional_context = additional_context,
  })

  current_job = service:complete(prompt_data, function(data)
    handle_completion_response(req, data)
  end, model_info or {})
end

--- Gather additional context (if enabled) and dispatch the request.
local function gather_and_dispatch(req, service, fmt, model_info)
  local context_manager = require('cassandra_ai.context')
  local supports_context = (fmt == require('cassandra_ai.prompt_formatters').chat)

  if context_manager.is_enabled() and supports_context then
    logger.trace('gather_and_dispatch() -> collecting context')
    local params = {
      bufnr = bufnr,
      cursor_pos = { line = cursor_pos[1] - 1, col = cursor_pos[2] },
      lines_before = req.before,
      lines_after = req.after,
      filetype = req.ft,
    }
    context_manager.gather_context(params, function(additional_context)
      dispatch_request(req, service, fmt, model_info, additional_context)
    end)
  else
    dispatch_request(req, service, fmt, model_info, nil)
  end
end

--- Extract surrounding context using the configured strategy.
local function extract_surround(req, callback)
  local surround_extractor = require('cassandra_ai.context.surround_extractor')
  local ctx = {
    cursor = { line = cursor_pos[1], col = cursor_pos[2] },
    bufnr = bufnr,
  }
  local strategy = conf:get('surround_extractor_strategy')
  if strategy == 'smart' then
    require('cassandra_ai.context.utils').detect_suggestion_context(bufnr, cursor_pos, function(current_context)
      if req.gen ~= generation then
        return
      end
      ctx.current_context = current_context
      callback(surround_extractor.smart_extractor(ctx))
    end)
  else
    callback(surround_extractor.simple_extractor(ctx))
  end
end

function M.trigger(opts)
  opts = opts or {}

  if vim.fn.mode() ~= 'i' then
    return
  end

  local ft = vim.bo.filetype
  if conf:get('ignored_file_types')[ft] then
    return
  end

  cancel_request()
  cancel_debounce()
  clear_ghost_text()
  clear_validation_state()

  generation = generation + 1
  auto_triggered = opts.auto or false

  bufnr = vim.api.nvim_get_current_buf()
  cursor_pos = vim.api.nvim_win_get_cursor(0)
  completions = {}
  current_index = 0

  local rejected = pending_rejected
  pending_rejected = {}

  local service = conf:get('provider')
  if service == nil then
    logger.warn('trigger: no provider configured')
    return
  end

  local req = {
    gen = generation,
    ft = ft,
    rejected = rejected,
    request_id = generate_uuid(),
  }
  current_request_id = req.request_id

  logger.info('trigger: generation=' .. req.gen .. ' buf=' .. bufnr .. ' ft=' .. ft)

  extract_surround(req, function(surround_context)
    if req.gen ~= generation then
      return
    end

    req.before = surround_context.lines_before
    req.after = surround_context.lines_after

    vim.api.nvim_exec_autocmds({ 'User' }, {
      pattern = 'CassandraAiRequestStarted',
    })

    service:resolve_model(function(model_info)
      if req.gen ~= generation then
        return
      end
      local fmt = resolve_formatter(model_info)
      gather_and_dispatch(req, service, fmt, model_info)
    end)
  end)
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

function M.is_visible()
  return is_visible
end

function M.dismiss()
  if is_visible and current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(current_request_id, { accepted = false })
  end
  cancel_request()
  cancel_debounce()
  clear_ghost_text()
  clear_validation_state()
  completions = {}
  current_index = 0
  current_request_id = nil
  pending_rejected = {}
end

function M.next()
  if #completions == 0 then
    return
  end
  current_index = current_index % #completions + 1
  logger.info('next completion: ' .. current_index .. '/' .. #completions)
  render_ghost_text(completions[current_index])
end

function M.prev()
  if #completions == 0 then
    return
  end
  current_index = (current_index - 2) % #completions + 1
  logger.info('prev completion: ' .. current_index .. '/' .. #completions)
  render_ghost_text(completions[current_index])
end

function M.regenerate()
  if not is_visible or current_index == 0 or #completions == 0 then
    return
  end

  local text = completions[current_index]
  if not text or text == '' then
    return
  end

  if current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(current_request_id, { accepted = false })
  end

  logger.info('regenerate: rejecting completion and requesting new one')
  table.insert(pending_rejected, text)
  M.trigger()
end

function M.accept()
  if not is_visible or current_index == 0 or #completions == 0 then
    return false
  end

  local text = completions[current_index]
  if not text or text == '' then
    return false
  end

  local num_lines = #vim.split(text, '\n', { plain = true })
  logger.info('completion accepted (' .. num_lines .. ' lines)')

  if current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(current_request_id, { accepted = true, acceptance_type = 'full', lines_accepted = num_lines, lines_remaining = 0 })
  end

  local row = cursor_pos[1] -- 1-indexed
  local col = cursor_pos[2] -- 0-indexed bytes

  clear_ghost_text()

  local cur_line = vim.api.nvim_buf_get_lines(bufnr, row - 1, row, false)[1] or ''
  local before = cur_line:sub(1, col)
  local after_cursor = cur_line:sub(col + 1)

  local comp_lines = vim.split(text, '\n', { plain = true })

  internal_move = true

  local new_lines
  if #comp_lines == 1 then
    new_lines = { before .. comp_lines[1] .. after_cursor }
  else
    new_lines = {}
    new_lines[1] = before .. comp_lines[1]
    for i = 2, #comp_lines - 1 do
      new_lines[#new_lines + 1] = comp_lines[i]
    end
    new_lines[#new_lines + 1] = comp_lines[#comp_lines] .. after_cursor
  end

  vim.api.nvim_buf_set_lines(bufnr, row - 1, row, false, new_lines)

  -- Set cursor at end of completion text
  local new_row = row - 1 + #new_lines -- 1-indexed
  local last_comp_line = comp_lines[#comp_lines]
  local new_col
  if #comp_lines == 1 then
    new_col = #before + #last_comp_line
  else
    new_col = #last_comp_line
  end
  vim.api.nvim_win_set_cursor(0, { new_row, new_col })

  completions = {}
  current_index = 0
  current_request_id = nil

  vim.schedule(function()
    internal_move = false
  end)

  return true
end

--- Accept the first `n` lines of the current completion, keeping the rest as ghost text.
local function accept_n_lines(n)
  if not is_visible or current_index == 0 or #completions == 0 then
    return false
  end

  local text = completions[current_index]
  if not text or text == '' then
    return false
  end

  local comp_lines = vim.split(text, '\n', { plain = true })

  if n >= #comp_lines then
    return M.accept()
  end

  local lines_remaining = #comp_lines - n
  logger.info('accept_n_lines(' .. n .. '/' .. #comp_lines .. ')')

  if current_request_id then
    local accepted_text = table.concat(comp_lines, '\n', 1, n)
    require('cassandra_ai.telemetry'):log_acceptance(current_request_id, { accepted = true, acceptance_type = 'partial', lines_accepted = n, lines_remaining = lines_remaining, accepted_text = accepted_text })
  end

  clear_ghost_text()
  internal_move = true

  local row = cursor_pos[1] -- 1-indexed
  local col = cursor_pos[2] -- 0-indexed bytes

  local cur_line = vim.api.nvim_buf_get_lines(bufnr, row - 1, row, false)[1] or ''
  local before = cur_line:sub(1, col)
  local after_cursor = cur_line:sub(col + 1)

  local new_lines = {}
  new_lines[1] = before .. comp_lines[1]
  for i = 2, n do
    new_lines[#new_lines + 1] = comp_lines[i]
  end
  -- Consume leading whitespace from the next completion line so the cursor lands after indentation
  local next_line = comp_lines[n + 1]
  local indent = next_line:match('^(%s*)') or ''
  new_lines[#new_lines + 1] = indent .. after_cursor

  vim.api.nvim_buf_set_lines(bufnr, row - 1, row, false, new_lines)

  -- Position cursor after the indentation
  local new_row = row + n -- 1-indexed
  local new_col = #indent
  vim.api.nvim_win_set_cursor(0, { new_row, new_col })
  cursor_pos = { new_row, new_col }

  -- Build remaining completion, stripping the consumed indent from the first remaining line
  comp_lines[n + 1] = next_line:sub(#indent + 1)
  local remaining = table.concat(comp_lines, '\n', n + 1)
  completions = { remaining }
  current_index = 1

  render_ghost_text(remaining)

  vim.schedule(function()
    internal_move = false
  end)

  return true
end

function M.accept_line()
  return accept_n_lines(1)
end

function M.accept_paragraph()
  if not is_visible or current_index == 0 or #completions == 0 then
    return false
  end

  local text = completions[current_index]
  if not text or text == '' then
    return false
  end

  local comp_lines = vim.split(text, '\n', { plain = true })

  -- Find first empty line and accept through it (so cursor lands on the next meaningful line)
  for i, line in ipairs(comp_lines) do
    if vim.trim(line) == '' then
      return accept_n_lines(i)
    end
  end

  -- No empty line found — accept all
  return M.accept()
end

-- ---------------------------------------------------------------------------
-- Debounce
-- ---------------------------------------------------------------------------

local function debounced_trigger()
  if auto_triggered then
    return
  end
  cancel_debounce()
  local ic = conf:get('inline')
  if not ic.auto_trigger then
    return
  end
  if require('cassandra_ai.integrations').is_completion_menu_visible() then
    return
  end
  debounce_timer = vim.uv.new_timer()
  debounce_timer:start(
    ic.debounce_ms,
    0,
    vim.schedule_wrap(function()
      M.trigger({ auto = true })
    end)
  )
end

-- ---------------------------------------------------------------------------
-- Autocmds
-- ---------------------------------------------------------------------------

local function setup_autocmds()
  local group = vim.api.nvim_create_augroup('cassandra_ai_inline', { clear = true })

  vim.api.nvim_create_autocmd('CursorMovedI', {
    group = group,
    callback = function()
      if internal_move then
        return
      end
      if pending_validation then
        validate_or_defer()
        return
      end
      if is_visible and cursor_pos and #completions > 0 then
        local cur = vim.api.nvim_win_get_cursor(0)
        if cur[1] == cursor_pos[1] and cur[2] == cursor_pos[2] then
          -- Cursor hasn't moved (e.g. after partial accept) — keep ghost text
          return
        end
        if cur[1] == cursor_pos[1] and cur[2] > cursor_pos[2] then
          -- User typed forward on the same line — check if it matches the completion
          local advance = cur[2] - cursor_pos[2]
          local text = completions[current_index]
          local prefix = text:sub(1, advance)
          local line = vim.api.nvim_buf_get_lines(bufnr, cur[1] - 1, cur[1], false)[1] or ''
          local typed = line:sub(cursor_pos[2] + 1, cur[2])
          if typed == prefix then
            -- Still matching — trim completion and re-render at new cursor
            local trimmed = text:sub(advance + 1)
            if trimmed == '' then
              M.dismiss()
            else
              completions[current_index] = trimmed
              cursor_pos = cur
              render_ghost_text(trimmed)
            end
            return
          end
        end
        -- Mismatch or moved elsewhere — dismiss and allow re-trigger
        M.dismiss()
      end
      debounced_trigger()
    end,
  })

  vim.api.nvim_create_autocmd('InsertEnter', {
    group = group,
    callback = function()
      if internal_move then
        return
      end
      debounced_trigger()
    end,
  })

  vim.api.nvim_create_autocmd('InsertLeave', {
    group = group,
    callback = function()
      M.dismiss()
    end,
  })

  vim.api.nvim_create_autocmd('BufLeave', {
    group = group,
    callback = function()
      M.dismiss()
    end,
  })
end

-- ---------------------------------------------------------------------------
-- Keymaps
-- ---------------------------------------------------------------------------

local function setup_keymaps()
  local km = conf:get('inline').keymap

  if km.accept then
    vim.keymap.set('i', km.accept, function()
      if M.is_visible() then
        -- Schedule accept so buffer modification happens outside expr evaluation
        vim.schedule(M.accept)
        return ''
      end
      -- Fall through to original mapping
      return vim.api.nvim_replace_termcodes(km.accept, true, false, true)
    end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion' })
  end

  if km.accept_line then
    vim.keymap.set('i', km.accept_line, function()
      if M.is_visible() then
        vim.schedule(M.accept_line)
        return ''
      end
      return vim.api.nvim_replace_termcodes(km.accept_line, true, false, true)
    end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion line' })
  end

  if km.accept_paragraph then
    vim.keymap.set('i', km.accept_paragraph, function()
      if M.is_visible() then
        vim.schedule(M.accept_paragraph)
        return ''
      end
      return vim.api.nvim_replace_termcodes(km.accept_paragraph, true, false, true)
    end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion paragraph' })
  end

  if km.dismiss then
    vim.keymap.set('i', km.dismiss, function()
      M.dismiss()
    end, { noremap = true, silent = true, desc = 'Dismiss AI completion' })
  end

  if km.next then
    vim.keymap.set('i', km.next, function()
      M.next()
    end, { noremap = true, silent = true, desc = 'Next AI completion' })
  end

  if km.prev then
    vim.keymap.set('i', km.prev, function()
      M.prev()
    end, { noremap = true, silent = true, desc = 'Previous AI completion' })
  end

  if km.regenerate then
    vim.keymap.set('i', km.regenerate, function()
      M.regenerate()
    end, { noremap = true, silent = true, desc = 'Regenerate AI completion' })
  end

  if km.toggle_cmp then
    vim.keymap.set('i', km.toggle_cmp, function()
      local integrations = require('cassandra_ai.integrations')
      if M.is_visible() then
        -- Ghost text visible → dismiss it and let cmp show
        M.dismiss()
        integrations.trigger_completion_menu()
      elseif integrations.is_completion_menu_visible() then
        -- Cmp menu visible → close it and trigger ghost text
        integrations.close_completion_menus()
        M.trigger()
      end
    end, { noremap = true, silent = true, desc = 'Toggle between AI completion and cmp' })
  end
end

-- ---------------------------------------------------------------------------
-- Setup
-- ---------------------------------------------------------------------------

function M.setup(opts)
  logger.trace('inline setup called')
  -- Define highlight group
  vim.api.nvim_set_hl(0, 'CassandraAiInline', { link = opts.highlight, default = true })

  setup_autocmds()
  setup_keymaps()
  require('cassandra_ai.integrations').setup()
end

return M
