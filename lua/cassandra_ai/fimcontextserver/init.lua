--- FIM Context Server lifecycle management
--- Manages a single fimcontextserver process per Neovim session
local logger = require('cassandra_ai.logger')

local M = {}

-- Server state
local server = {
  job_id = nil,
  status = 'stopped', -- 'starting' | 'ready' | 'error' | 'stopped'
  project_root = nil,
  line_buffer = '',
  pending = {}, -- {[msg_id] = {callback, timer}}
  next_id = 1,
  restart_count = 0,
  config = nil,
  init_result = nil, -- result from initialize (file_count, bm25_chunks)
}

-- Queue of callbacks waiting for server to become ready
local ready_callbacks = {}

local MAX_RESTARTS = 5
local REQUEST_TIMEOUT_MS = 5000

--- Process a complete JSON line from the server
local function process_line(line)
  if line == '' then
    return
  end

  local ok, response = pcall(vim.json.decode, line)
  if not ok then
    logger.warn('fimcontextserver: malformed JSON response: ' .. line:sub(1, 200))
    return
  end

  local id = response.id
  if id == nil then
    logger.trace('fimcontextserver: notification (no id): ' .. line:sub(1, 200))
    return
  end

  local entry = server.pending[id]
  if not entry then
    logger.trace('fimcontextserver: response for unknown id=' .. tostring(id))
    return
  end

  -- Clear timeout timer
  if entry.timer then
    vim.fn.timer_stop(entry.timer)
  end
  server.pending[id] = nil

  if response.error then
    logger.warn('fimcontextserver: RPC error (id=' .. id .. '): ' .. (response.error.message or 'unknown'))
    entry.callback(nil, response.error)
  else
    entry.callback(response.result, nil)
  end
end

--- stdout handler with line buffering (standard Neovim jobstart pattern)
local function on_stdout(_, data, _)
  for i, chunk in ipairs(data) do
    if i == 1 then
      server.line_buffer = server.line_buffer .. chunk
    else
      if server.line_buffer ~= '' then
        process_line(server.line_buffer)
      end
      server.line_buffer = chunk
    end
  end
end

--- stderr handler — log server output
local function on_stderr(_, data, _)
  for _, line in ipairs(data) do
    if line ~= '' then
      logger.trace('fimcontextserver[stderr]: ' .. line)
    end
  end
end

--- Fail all pending requests (e.g., on crash)
local function fail_all_pending(err_msg)
  for id, entry in pairs(server.pending) do
    if entry.timer then
      vim.fn.timer_stop(entry.timer)
    end
    entry.callback(nil, { code = -32000, message = err_msg })
  end
  server.pending = {}
end

--- Notify ready callbacks
local function fire_ready_callbacks(ok)
  local cbs = ready_callbacks
  ready_callbacks = {}
  for _, cb in ipairs(cbs) do
    cb(ok)
  end
end

--- Schedule auto-restart with exponential backoff
local function schedule_restart()
  if server.restart_count >= MAX_RESTARTS then
    logger.error('fimcontextserver: max restarts (' .. MAX_RESTARTS .. ') reached, giving up')
    server.status = 'error'
    fire_ready_callbacks(false)
    return
  end

  server.restart_count = server.restart_count + 1
  local delay_s = math.min(30, 2 ^ (server.restart_count - 1))
  logger.warn('fimcontextserver: scheduling restart in ' .. delay_s .. 's (attempt ' .. server.restart_count .. '/' .. MAX_RESTARTS .. ')')

  vim.defer_fn(function()
    if server.status == 'stopped' or server.status == 'error' then
      M._start(server.project_root, server.config)
    end
  end, delay_s * 1000)
end

--- on_exit handler
local function on_exit(_, exit_code, _)
  local was_status = server.status
  server.job_id = nil
  server.line_buffer = ''

  if was_status == 'stopped' then
    -- Expected shutdown
    logger.debug('fimcontextserver: process exited (shutdown)')
    return
  end

  logger.warn('fimcontextserver: process exited unexpectedly (code=' .. exit_code .. ')')
  server.status = 'stopped'
  fail_all_pending('server process exited')
  fire_ready_callbacks(false)
  schedule_restart()
end

--- Start the fimcontextserver process (internal)
function M._start(project_root, config)
  local python_env = require('cassandra_ai.fimcontextserver.python_env')

  python_env.ensure(function(ok, python_path)
    if not ok then
      logger.error('fimcontextserver: Python environment not ready')
      server.status = 'error'
      fire_ready_callbacks(false)
      return
    end

    local plugin_root = python_env.get_plugin_root()

    server.status = 'starting'
    server.project_root = project_root
    server.config = config
    server.line_buffer = ''

    logger.info('fimcontextserver: starting server for project ' .. project_root)

    server.job_id = vim.fn.jobstart({ python_path, '-m', 'fimcontextserver', '--log-level', 'DEBUG' }, {
      env = { PYTHONPATH = plugin_root .. '/python' },
      on_stdout = on_stdout,
      on_stderr = on_stderr,
      on_exit = on_exit,
    })

    if server.job_id <= 0 then
      logger.error('fimcontextserver: failed to start process (jobstart returned ' .. server.job_id .. ')')
      server.status = 'error'
      server.job_id = nil
      fire_ready_callbacks(false)
      return
    end

    -- Send initialize request
    local init_params = {
      project_root = project_root,
      include_paths = config.include_paths or {},
      bm25 = config.bm25 or false,
    }

    M.request('initialize', init_params, function(result, err)
      if err then
        logger.error('fimcontextserver: initialize failed: ' .. (err.message or 'unknown'))
        server.status = 'error'
        fire_ready_callbacks(false)
        return
      end

      server.status = 'ready'
      server.restart_count = 0 -- Reset backoff on successful init
      server.init_result = result
      logger.info('fimcontextserver: ready (' .. (result and result.file_count or '?') .. ' files, ' .. (result and result.bm25_chunks or '?') .. ' BM25 chunks)')
      fire_ready_callbacks(true)
    end)
  end)
end

--- Ensure server is running and initialized for the given project
--- @param project_root string
--- @param config table Project config from project.lua
--- @param callback function Called when server is ready: callback(ok: boolean)
function M.get_or_start(project_root, config, callback)
  -- Already running for this project?
  if server.status == 'ready' and server.project_root == project_root then
    callback(true)
    return
  end

  -- Currently starting?
  if server.status == 'starting' then
    table.insert(ready_callbacks, callback)
    return
  end

  -- Need to (re)start — different project or stopped/error
  if server.job_id and server.project_root ~= project_root then
    -- Shut down old server first
    M.shutdown()
  end

  table.insert(ready_callbacks, callback)
  M._start(project_root, config)
end

--- Send a JSON-RPC request to the server
--- @param method string RPC method name
--- @param params table Request parameters
--- @param callback function Called with (result, error)
function M.request(method, params, callback)
  if not server.job_id then
    callback(nil, { code = -32000, message = 'server not running' })
    return
  end

  local id = server.next_id
  server.next_id = server.next_id + 1

  local request = vim.json.encode({
    jsonrpc = '2.0',
    id = id,
    method = method,
    params = params,
  })

  logger.trace('fimcontextserver: request id=' .. id .. ' method=' .. method)

  -- Set per-request timeout
  local conf = require('cassandra_ai.config')
  local fcs_conf = conf:get('fimcontextserver') or {}
  local timeout_ms = fcs_conf.timeout_ms or REQUEST_TIMEOUT_MS

  local timer = vim.fn.timer_start(timeout_ms, function()
    local entry = server.pending[id]
    if entry then
      server.pending[id] = nil
      logger.warn('fimcontextserver: request timed out (id=' .. id .. ' method=' .. method .. ')')
      entry.callback(nil, { code = -32000, message = 'request timed out' })
    end
  end)

  server.pending[id] = { callback = callback, timer = timer }

  -- Send newline-delimited JSON
  vim.fn.chansend(server.job_id, request .. '\n')
end

--- Shutdown the server gracefully
function M.shutdown()
  if not server.job_id then
    return
  end

  logger.debug('fimcontextserver: shutting down')
  server.status = 'stopped'
  fail_all_pending('server shutting down')
  fire_ready_callbacks(false)

  -- Send shutdown request, then stop the job
  local request = vim.json.encode({
    jsonrpc = '2.0',
    id = server.next_id,
    method = 'shutdown',
    params = {},
  })
  server.next_id = server.next_id + 1

  pcall(vim.fn.chansend, server.job_id, request .. '\n')

  -- Give the server a moment to exit gracefully, then force stop
  local job_id = server.job_id
  vim.defer_fn(function()
    if job_id and server.job_id == job_id then
      pcall(vim.fn.jobstop, job_id)
      server.job_id = nil
    end
  end, 1000)
end

--- Get current server status info
--- @return table {status, project_root, file_count, bm25_chunks}
function M.get_status()
  return {
    status = server.status,
    project_root = server.project_root,
    file_count = server.init_result and server.init_result.file_count,
    bm25_chunks = server.init_result and server.init_result.bm25_chunks,
    restart_count = server.restart_count,
  }
end

--- Register VimLeavePre autocmd for cleanup
vim.api.nvim_create_autocmd('VimLeavePre', {
  group = vim.api.nvim_create_augroup('cassandra_ai_fimcontextserver', { clear = true }),
  callback = function()
    M.shutdown()
  end,
})

return M
