--- Context provider that bridges to the fimcontextserver JSON-RPC server
local BaseContextProvider = require('cassandra_ai.context.base')
local logger = require('cassandra_ai.logger')

local FimserverContextProvider = BaseContextProvider:new()

function FimserverContextProvider:new(opts)
  local o = BaseContextProvider.new(self, opts)
  setmetatable(o, self)
  self.__index = self
  return o
end

function FimserverContextProvider:get_context(params, callback)
  local project = require('cassandra_ai.fimcontextserver.project')
  local fimcontextserver = require('cassandra_ai.fimcontextserver')

  local filepath = vim.api.nvim_buf_get_name(params.bufnr)
  if not filepath or filepath == '' then
    callback({ content = '', metadata = { source = 'fimcontextserver' } })
    return
  end

  local root = project.get_project_root(filepath)
  if not root then
    logger.trace('fimcontextserver: no project root for ' .. filepath)
    callback({ content = '', metadata = { source = 'fimcontextserver' } })
    return
  end

  local proj_conf = project.get_config(root)

  -- Compute byte offset from cursor position
  local cursor_line = params.cursor_pos.line -- 0-indexed
  local cursor_col = params.cursor_pos.col
  local all_lines = vim.api.nvim_buf_get_lines(params.bufnr, 0, -1, false)
  local content = table.concat(all_lines, '\n')

  local byte_offset = 0
  for i = 1, cursor_line do
    byte_offset = byte_offset + #all_lines[i] + 1 -- +1 for newline
  end
  byte_offset = byte_offset + cursor_col

  fimcontextserver.get_or_start(root, proj_conf, function(ok)
    if not ok then
      logger.warn('fimcontextserver: server not ready, returning empty context')
      callback({ content = '', metadata = { source = 'fimcontextserver' } })
      return
    end

    fimcontextserver.request('getContext', {
      filepath = filepath,
      content = content,
      cursor_offset = byte_offset,
    }, function(result, err)
      if err then
        logger.warn('fimcontextserver: getContext error: ' .. (err.message or 'unknown'))
        callback({ content = '', metadata = { source = 'fimcontextserver' } })
        return
      end

      local ctx = (result and result.context) or ''
      logger.trace('fimcontextserver: got context (' .. #ctx .. ' chars)')
      callback({ content = ctx, metadata = { source = 'fimcontextserver' } })
    end)
  end)
end

function FimserverContextProvider:is_available()
  return true -- always available; gracefully returns empty when no project config
end

function FimserverContextProvider:get_name()
  return 'fimcontextserver'
end

return FimserverContextProvider
