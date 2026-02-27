local M = {}

--- Generate a UUID v4
function M.generate_uuid()
  local template = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
  return string.gsub(template, '[xy]', function(c)
    local v = (c == 'x') and math.random(0, 0xf) or math.random(8, 0xb)
    return string.format('%x', v)
  end)
end

--- Safely serialize provider config for logging
--- Only logs provider.params (never api_key or headers)
--- Replaces functions with type metadata
function M.safe_serialize_config(params)
  if type(params) ~= 'table' then
    return params
  end

  local result = {}
  for key, value in pairs(params) do
    local value_type = type(value)
    if value_type == 'function' then
      result[key] = { __type = 'function' }
    elseif value_type == 'table' then
      result[key] = M.safe_serialize_config(value) -- Recursive
    elseif value_type == 'string' or value_type == 'number' or value_type == 'boolean' then
      result[key] = value
    else
      -- Thread, userdata, etc.
      result[key] = { __type = value_type }
    end
  end
  return result
end

--- Filter a list of strings by prefix match against arglead
--- @param items string[] List of completion candidates
--- @param arglead string The current argument lead to match against
--- @return string[] Filtered list of matching items
function M.filter_completions(items, arglead)
  local matches = {}
  for _, item in ipairs(items) do
    if item:find('^' .. vim.pesc(arglead)) then
      table.insert(matches, item)
    end
  end
  return matches
end

--- Create a markdown floating popup window with q-to-close binding
--- @param lines string[] Content lines for the popup
--- @param title string Window title
--- @param opts? table Optional overrides: width_pct (0-1), height_pct (0-1)
function M.create_popup(lines, title, opts)
  opts = opts or {}
  local popup_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(popup_buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(popup_buf, 'modifiable', false)
  vim.api.nvim_buf_set_option(popup_buf, 'buftype', 'nofile')
  vim.api.nvim_buf_set_option(popup_buf, 'filetype', 'markdown')

  local width_pct = opts.width_pct or 0.8
  local height_pct = opts.height_pct or 0.8
  local width = math.floor(vim.o.columns * width_pct)
  local height = math.floor(vim.o.lines * height_pct)
  local row = math.floor((vim.o.lines - height) / 2)
  local col = math.floor((vim.o.columns - width) / 2)

  local win = vim.api.nvim_open_win(popup_buf, true, {
    relative = 'editor',
    width = width,
    height = height,
    row = row,
    col = col,
    style = 'minimal',
    border = 'rounded',
    title = ' ' .. title .. ' ',
    title_pos = 'center',
  })

  vim.api.nvim_win_set_option(win, 'wrap', true)
  vim.api.nvim_win_set_option(win, 'linebreak', true)
  vim.api.nvim_buf_set_keymap(popup_buf, 'n', 'q', ':close<CR>', { noremap = true, silent = true })

  return win, popup_buf
end

--- Create a toggle/enable/disable command tree node
--- @param name string Display name for notifications (e.g. 'auto_trigger')
--- @param get_fn fun(): boolean Returns current boolean state
--- @param set_fn fun(enabled: boolean) Applies the new state
--- @return table Command node with complete and execute functions
function M.create_toggle_command(name, get_fn, set_fn)
  return {
    description = 'Toggle, enable, or disable ' .. name,
    complete = function(arglead)
      return M.filter_completions({ 'toggle', 'enable', 'disable' }, arglead)
    end,
    execute = function(opts)
      local action = opts[1]
      local enabled

      if action == 'toggle' then
        enabled = not get_fn()
      elseif action == 'enable' then
        enabled = true
      elseif action == 'disable' then
        enabled = false
      else
        vim.notify('Usage: :Cassy config ' .. name .. ' toggle|enable|disable', vim.log.levels.ERROR)
        return
      end

      set_fn(enabled)
      vim.notify(name .. ': ' .. (enabled and 'enabled' or 'disabled'), vim.log.levels.INFO)
    end,
  }
end

return M
