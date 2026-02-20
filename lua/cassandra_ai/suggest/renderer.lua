local state = require('cassandra_ai.suggest.state')

local M = {}

function M.clear()
  if state.bufnr and vim.api.nvim_buf_is_valid(state.bufnr) then
    vim.api.nvim_buf_clear_namespace(state.bufnr, state.ns, 0, -1)
  end
  state.is_visible = false
end

function M.render(text)
  if not state.bufnr or not vim.api.nvim_buf_is_valid(state.bufnr) then
    return
  end
  M.clear()
  if not text or text == '' then
    return
  end

  require('cassandra_ai.integrations').close_completion_menus()

  local lines = vim.split(text, '\n', { plain = true })
  local row = state.cursor_pos[1] - 1 -- 0-indexed
  local col = state.cursor_pos[2]

  local virt_text = { { lines[1], 'CassandraAiSuggest' } }
  local virt_lines = nil

  if #lines > 1 then
    virt_lines = {}
    for i = 2, #lines do
      table.insert(virt_lines, { { lines[i], 'CassandraAiSuggest' } })
    end
  end

  vim.api.nvim_buf_set_extmark(state.bufnr, state.ns, row, col, {
    virt_text = virt_text,
    virt_text_pos = 'inline',
    virt_lines = virt_lines,
  })
  state.is_visible = true
end

return M
