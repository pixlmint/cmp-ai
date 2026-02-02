local M = {}

local conf = require('cmp_ai.config')
local api = vim.api


function M.simple_extractor(ctx)
  local max_lines = conf:get('max_lines')
  local cursor = ctx.context.cursor
  local cur_line = ctx.context.cursor_line
  -- properly handle utf8
  -- local cur_line_before = string.sub(cur_line, 1, cursor.col - 1)
  local cur_line_before = vim.fn.strpart(cur_line, 0, math.max(cursor.col - 1, 0), true)

  -- properly handle utf8
  -- local cur_line_after = string.sub(cur_line, cursor.col) -- include current character
  local cur_line_after = vim.fn.strpart(cur_line, math.max(cursor.col - 1, 0), vim.fn.strdisplaywidth(cur_line), true) -- include current character

  local lines_before = api.nvim_buf_get_lines(0, math.max(0, cursor.line - max_lines), cursor.line, false)
  table.insert(lines_before, cur_line_before)

  local lines_after = api.nvim_buf_get_lines(0, cursor.line + 1, cursor.line + max_lines, false)
  table.insert(lines_after, 1, cur_line_after)

  return {
    lines_before = table.concat(lines_before, '\n'),
    lines_after = table.concat(lines_after, '\n'),
  }
end

function M.smart_extractor(ctx)
  return {
    lines_before = '',
    lines_after = '',
  }
end

return M
