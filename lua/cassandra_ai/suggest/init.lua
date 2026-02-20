local conf = require('cassandra_ai.config')
local logger = require('cassandra_ai.logger')
local state = require('cassandra_ai.suggest.state')
local renderer = require('cassandra_ai.suggest.renderer')
local validation = require('cassandra_ai.suggest.validation')
local pipeline = require('cassandra_ai.suggest.pipeline')
local util = require('cassandra_ai.util')

local M = {}

-- Seed RNG once on module load for UUID generation
math.randomseed(os.clock() * 1e6 + (vim.uv.hrtime() % 1e9))

-- Re-export for testing
M._compute_overlap_threshold = validation._compute_overlap_threshold

-- ---------------------------------------------------------------------------
-- Request management
-- ---------------------------------------------------------------------------

local function cancel_request()
  if state.current_job then
    pcall(function()
      state.current_job:shutdown()
    end)
    state.current_job = nil
  end
end

local function cancel_debounce()
  if state.debounce_timer then
    state.debounce_timer:stop()
    state.debounce_timer:close()
    state.debounce_timer = nil
  end
end

-- ---------------------------------------------------------------------------
-- Trigger
-- ---------------------------------------------------------------------------

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
  renderer.clear()
  validation.clear_validation_state()

  state.generation = state.generation + 1
  state.auto_triggered = opts.auto or false

  state.bufnr = vim.api.nvim_get_current_buf()
  state.cursor_pos = vim.api.nvim_win_get_cursor(0)
  state.completions = {}
  state.current_index = 0

  local rejected = state.pending_rejected
  state.pending_rejected = {}

  local service = conf:get('provider')
  if service == nil then
    logger.warn('trigger: no provider configured')
    return
  end

  local req = {
    gen = state.generation,
    ft = ft,
    rejected = rejected,
    request_id = util.generate_uuid(),
  }
  state.current_request_id = req.request_id

  logger.info('trigger: generation=' .. req.gen .. ' buf=' .. state.bufnr .. ' ft=' .. ft)

  pipeline.extract_surround(req, function(surround_context)
    if req.gen ~= state.generation then
      return
    end

    req.before = surround_context.lines_before
    req.after = surround_context.lines_after

    vim.api.nvim_exec_autocmds({ 'User' }, {
      pattern = 'CassandraAiRequestStarted',
    })

    service:resolve_model(function(model_info)
      if req.gen ~= state.generation then
        return
      end
      local fmt = pipeline.resolve_formatter(model_info)
      pipeline.gather_and_dispatch(req, service, fmt, model_info)
    end)
  end)
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

function M.is_visible()
  return state.is_visible
end

function M.dismiss()
  if state.is_visible and state.current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(state.current_request_id, { accepted = false })
  end
  cancel_request()
  cancel_debounce()
  renderer.clear()
  validation.clear_validation_state()
  state.completions = {}
  state.current_index = 0
  state.current_request_id = nil
  state.pending_rejected = {}
end

function M.next()
  if #state.completions == 0 then
    return
  end
  state.current_index = state.current_index % #state.completions + 1
  logger.info('next completion: ' .. state.current_index .. '/' .. #state.completions)
  renderer.render(state.completions[state.current_index])
end

function M.prev()
  if #state.completions == 0 then
    return
  end
  state.current_index = (state.current_index - 2) % #state.completions + 1
  logger.info('prev completion: ' .. state.current_index .. '/' .. #state.completions)
  renderer.render(state.completions[state.current_index])
end

function M.regenerate()
  if not state.is_visible or state.current_index == 0 or #state.completions == 0 then
    return
  end

  local text = state.completions[state.current_index]
  if not text or text == '' then
    return
  end

  if state.current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(state.current_request_id, { accepted = false })
  end

  logger.info('regenerate: rejecting completion and requesting new one')
  table.insert(state.pending_rejected, text)
  M.trigger()
end

function M.accept()
  if not state.is_visible or state.current_index == 0 or #state.completions == 0 then
    return false
  end

  local text = state.completions[state.current_index]
  if not text or text == '' then
    return false
  end

  local num_lines = #vim.split(text, '\n', { plain = true })
  logger.info('completion accepted (' .. num_lines .. ' lines)')

  if state.current_request_id then
    require('cassandra_ai.telemetry'):log_acceptance(state.current_request_id, { accepted = true, acceptance_type = 'full', lines_accepted = num_lines, lines_remaining = 0 })
  end

  local row = state.cursor_pos[1] -- 1-indexed
  local col = state.cursor_pos[2] -- 0-indexed bytes

  renderer.clear()

  local cur_line = vim.api.nvim_buf_get_lines(state.bufnr, row - 1, row, false)[1] or ''
  local before = cur_line:sub(1, col)
  local after_cursor = cur_line:sub(col + 1)

  local comp_lines = vim.split(text, '\n', { plain = true })

  state.internal_move = true

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

  vim.api.nvim_buf_set_lines(state.bufnr, row - 1, row, false, new_lines)

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

  state.completions = {}
  state.current_index = 0
  state.current_request_id = nil

  vim.schedule(function()
    state.internal_move = false
  end)

  return true
end

--- Accept the first `n` lines of the current completion, keeping the rest as ghost text.
local function accept_n_lines(n)
  if not state.is_visible or state.current_index == 0 or #state.completions == 0 then
    return false
  end

  local text = state.completions[state.current_index]
  if not text or text == '' then
    return false
  end

  local comp_lines = vim.split(text, '\n', { plain = true })

  if n >= #comp_lines then
    return M.accept()
  end

  local lines_remaining = #comp_lines - n
  logger.info('accept_n_lines(' .. n .. '/' .. #comp_lines .. ')')

  if state.current_request_id then
    local accepted_text = table.concat(comp_lines, '\n', 1, n)
    require('cassandra_ai.telemetry'):log_acceptance(state.current_request_id, { accepted = true, acceptance_type = 'partial', lines_accepted = n, lines_remaining = lines_remaining, accepted_text = accepted_text })
  end

  renderer.clear()
  state.internal_move = true

  local row = state.cursor_pos[1] -- 1-indexed
  local col = state.cursor_pos[2] -- 0-indexed bytes

  local cur_line = vim.api.nvim_buf_get_lines(state.bufnr, row - 1, row, false)[1] or ''
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

  vim.api.nvim_buf_set_lines(state.bufnr, row - 1, row, false, new_lines)

  -- Position cursor after the indentation
  local new_row = row + n -- 1-indexed
  local new_col = #indent
  vim.api.nvim_win_set_cursor(0, { new_row, new_col })
  state.cursor_pos = { new_row, new_col }

  -- Build remaining completion, stripping the consumed indent from the first remaining line
  comp_lines[n + 1] = next_line:sub(#indent + 1)
  local remaining = table.concat(comp_lines, '\n', n + 1)
  state.completions = { remaining }
  state.current_index = 1

  renderer.render(remaining)

  vim.schedule(function()
    state.internal_move = false
  end)

  return true
end

function M.accept_line()
  return accept_n_lines(1)
end

function M.accept_paragraph()
  if not state.is_visible or state.current_index == 0 or #state.completions == 0 then
    return false
  end

  local text = state.completions[state.current_index]
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
  if state.auto_triggered then
    return
  end
  cancel_debounce()
  local sc = conf:get('suggest')
  if not sc.auto_trigger then
    return
  end
  if require('cassandra_ai.integrations').is_completion_menu_visible() then
    return
  end
  state.debounce_timer = vim.uv.new_timer()
  state.debounce_timer:start(
    sc.debounce_ms,
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
  local group = vim.api.nvim_create_augroup('cassandra_ai_suggest', { clear = true })

  vim.api.nvim_create_autocmd('CursorMovedI', {
    group = group,
    callback = function()
      if state.internal_move then
        return
      end
      if state.pending_validation then
        validation.validate_or_defer()
        return
      end
      if state.is_visible and state.cursor_pos and #state.completions > 0 then
        local cur = vim.api.nvim_win_get_cursor(0)
        if cur[1] == state.cursor_pos[1] and cur[2] == state.cursor_pos[2] then
          -- Cursor hasn't moved (e.g. after partial accept) — keep ghost text
          return
        end
        if cur[1] == state.cursor_pos[1] and cur[2] > state.cursor_pos[2] then
          -- User typed forward on the same line — check if it matches the completion
          local advance = cur[2] - state.cursor_pos[2]
          local text = state.completions[state.current_index]
          local prefix = text:sub(1, advance)
          local line = vim.api.nvim_buf_get_lines(state.bufnr, cur[1] - 1, cur[1], false)[1] or ''
          local typed = line:sub(state.cursor_pos[2] + 1, cur[2])
          if typed == prefix then
            -- Still matching — trim completion and re-render at new cursor
            local trimmed = text:sub(advance + 1)
            if trimmed == '' then
              M.dismiss()
            else
              state.completions[state.current_index] = trimmed
              state.cursor_pos = cur
              renderer.render(trimmed)
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
      if state.internal_move then
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

local prev_keymaps = {}

local function cleanup_keymaps()
  for _, key in ipairs(prev_keymaps) do
    pcall(vim.keymap.del, 'i', key)
  end
  prev_keymaps = {}
end

local function setup_keymaps()
  cleanup_keymaps()
  local km = conf:get('suggest').keymap

  local function set(key, fn, opts)
    if not key then
      return
    end
    vim.keymap.set('i', key, fn, opts)
    prev_keymaps[#prev_keymaps + 1] = key
  end

  set(km.accept, function()
    if M.is_visible() then
      -- Schedule accept so buffer modification happens outside expr evaluation
      vim.schedule(M.accept)
      return ''
    end
    -- Fall through to original mapping
    return vim.api.nvim_replace_termcodes(km.accept, true, false, true)
  end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion' })

  set(km.accept_line, function()
    if M.is_visible() then
      vim.schedule(M.accept_line)
      return ''
    end
    return vim.api.nvim_replace_termcodes(km.accept_line, true, false, true)
  end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion line' })

  set(km.accept_paragraph, function()
    if M.is_visible() then
      vim.schedule(M.accept_paragraph)
      return ''
    end
    return vim.api.nvim_replace_termcodes(km.accept_paragraph, true, false, true)
  end, { expr = true, noremap = true, silent = true, desc = 'Accept AI completion paragraph' })

  set(km.dismiss, function()
    M.dismiss()
  end, { noremap = true, silent = true, desc = 'Dismiss AI completion' })

  set(km.next, function()
    M.next()
  end, { noremap = true, silent = true, desc = 'Next AI completion' })

  set(km.prev, function()
    M.prev()
  end, { noremap = true, silent = true, desc = 'Previous AI completion' })

  set(km.regenerate, function()
    M.regenerate()
  end, { noremap = true, silent = true, desc = 'Regenerate AI completion' })

  set(km.toggle_cmp, function()
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

-- ---------------------------------------------------------------------------
-- Setup
-- ---------------------------------------------------------------------------

function M.setup(opts)
  logger.trace('suggest setup called')
  -- Define highlight group
  vim.api.nvim_set_hl(0, 'CassandraAiSuggest', { link = opts.highlight, default = true })

  setup_autocmds()
  setup_keymaps()
  require('cassandra_ai.integrations').setup()
end

return M
