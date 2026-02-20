local conf = require('cassandra_ai.config')
local logger = require('cassandra_ai.logger')
local state = require('cassandra_ai.suggest.state')
local renderer = require('cassandra_ai.suggest.renderer')

local M = {}

local validate_or_defer, show_validated_completion, reset_validation_idle_timer

function M.cancel_validation_timer()
  if state.validation_idle_timer then
    state.validation_idle_timer:stop()
    state.validation_idle_timer:close()
    state.validation_idle_timer = nil
  end
end

function M.clear_validation_state()
  state.auto_triggered = false
  state.pending_validation = nil
  M.cancel_validation_timer()
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
    M.clear_validation_state()
    return
  end

  local cur = vim.api.nvim_win_get_cursor(0)
  state.cursor_pos = cur
  state.completions = trimmed
  state.current_index = 1
  M.clear_validation_state()
  renderer.render(state.completions[state.current_index])
end

validate_or_defer = function()
  local pv = state.pending_validation
  if not pv then
    return
  end

  local typed = compute_typed_since_trigger(pv)
  if typed == nil then
    logger.trace('deferred: cursor moved off trigger line, discarding')
    if pv.request_id then
      require('cassandra_ai.telemetry'):log_acceptance(pv.request_id, { accepted = false, rejection_reason = 'cursor_moved' })
    end
    M.clear_validation_state()
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
    M.clear_validation_state()
    return
  end

  -- Check if past the validation threshold
  local overlap = conf:get('suggest').auto_trigger_overlap or '1+1'
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
  M.cancel_validation_timer()
  state.validation_idle_timer = vim.uv.new_timer()
  local idle_ms = conf:get('suggest').deferred_idle_ms

  local function show_completion()
    local pv = state.pending_validation
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
    state.validation_idle_timer:start(
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

M.validate_or_defer = function()
  validate_or_defer()
end

return M
