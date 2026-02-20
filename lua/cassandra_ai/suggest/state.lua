local M = {
  generation = 0,
  current_job = nil,
  debounce_timer = nil,
  completions = {},
  current_index = 0,
  is_visible = false,
  cursor_pos = nil,
  bufnr = nil,
  internal_move = false,
  current_request_id = nil,
  pending_rejected = {},

  auto_triggered = false,
  pending_validation = nil, -- { completions, trigger_pos, trigger_bufnr, trigger_line_text }
  validation_idle_timer = nil,
}

M.ns = vim.api.nvim_create_namespace('cassandra_ai_suggest')

return M
