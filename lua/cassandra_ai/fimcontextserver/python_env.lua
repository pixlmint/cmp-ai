--- Python environment management for fimcontextserver
--- Manages a venv at stdpath('data')/cassandra-ai/python-env/
local logger = require('cassandra_ai.logger')

local M = {}

local venv_dir = vim.fn.stdpath('data') .. '/cassandra-ai/python-env'
local marker_file = venv_dir .. '/.installed'
local cached_python_path = nil

--- Get the path to requirements.txt bundled with the plugin
local function get_requirements_path()
  -- Resolve relative to this file's location: ../../../python/requirements.txt
  local source = debug.getinfo(1, 'S').source:sub(2)
  local plugin_root = vim.fn.fnamemodify(source, ':h:h:h:h')
  return plugin_root .. '/python/requirements.txt'
end

--- Get the plugin root directory
local function get_plugin_root()
  local source = debug.getinfo(1, 'S').source:sub(2)
  return vim.fn.fnamemodify(source, ':h:h:h:h')
end

--- Compute SHA256 hash of a file's contents
local function file_hash(path)
  local f = io.open(path, 'r')
  if not f then
    return nil
  end
  local content = f:read('*a')
  f:close()
  return vim.fn.sha256(content)
end

--- Read the stored hash from the marker file
local function read_marker_hash()
  local f = io.open(marker_file, 'r')
  if not f then
    return nil
  end
  local hash = f:read('*l')
  f:close()
  return hash
end

--- Write the current requirements hash to the marker file
local function write_marker_hash(hash)
  local f = io.open(marker_file, 'w')
  if not f then
    logger.error('python_env: failed to write marker file: ' .. marker_file)
    return
  end
  f:write(hash)
  f:close()
end

--- Detect available Python environment manager
--- @return {type: string, executable: string}|nil
function M._detect_env_manager()
  local conf = require('cassandra_ai.config')
  local fcs_conf = conf:get('fimcontextserver') or {}
  local py_conf = fcs_conf.python or {}

  -- User override
  if py_conf.env_manager then
    if py_conf.env_manager == 'uv' and vim.fn.executable('uv') == 1 then
      return { type = 'uv', executable = 'uv' }
    elseif py_conf.env_manager == 'pip' then
      local py = vim.fn.executable('python3') == 1 and 'python3' or 'python'
      return { type = 'pip', executable = py }
    elseif py_conf.env_manager == 'conda' and vim.fn.executable('conda') == 1 then
      return { type = 'conda', executable = 'conda' }
    end
  end

  -- Auto-detect: uv > pip > conda
  if vim.fn.executable('uv') == 1 then
    return { type = 'uv', executable = 'uv' }
  end

  if vim.fn.executable('python3') == 1 then
    return { type = 'pip', executable = 'python3' }
  elseif vim.fn.executable('python') == 1 then
    return { type = 'pip', executable = 'python' }
  end

  if vim.fn.executable('conda') == 1 then
    return { type = 'conda', executable = 'conda' }
  end

  return nil
end

--- Check if the venv is ready (exists + deps installed with matching hash)
--- @return boolean
function M.is_ready()
  local python_path = venv_dir .. '/bin/python'
  if vim.fn.executable(python_path) ~= 1 then
    return false
  end

  local req_path = get_requirements_path()
  local current_hash = file_hash(req_path)
  if not current_hash then
    return false
  end

  local stored_hash = read_marker_hash()
  return stored_hash == current_hash
end

--- Get cached python path if ready
--- @return string|nil
function M.get_python_path()
  local conf = require('cassandra_ai.config')
  local fcs_conf = conf:get('fimcontextserver') or {}
  local py_conf = fcs_conf.python or {}

  -- User-specified python path bypasses venv entirely
  if py_conf.python_path then
    return py_conf.python_path
  end

  if cached_python_path then
    return cached_python_path
  end

  if M.is_ready() then
    cached_python_path = venv_dir .. '/bin/python'
    return cached_python_path
  end

  return nil
end

--- Run a sequence of shell commands asynchronously
--- @param commands string[] Commands to run sequentially
--- @param callback function Called with (ok: boolean) when done
local function run_commands_sequential(commands, callback)
  local idx = 0

  local function run_next()
    idx = idx + 1
    if idx > #commands then
      callback(true)
      return
    end

    local cmd = commands[idx]
    logger.debug('python_env: running: ' .. cmd)

    vim.fn.jobstart(cmd, {
      on_exit = function(_, exit_code)
        if exit_code ~= 0 then
          logger.error('python_env: command failed (exit ' .. exit_code .. '): ' .. cmd)
          callback(false)
        else
          run_next()
        end
      end,
      on_stderr = function(_, data)
        for _, line in ipairs(data) do
          if line ~= '' then
            logger.trace('python_env: ' .. line)
          end
        end
      end,
    })
  end

  run_next()
end

--- Ensure the Python environment is ready, creating/installing if needed
--- @param callback function Called with (ok: boolean, python_path: string|nil)
function M.ensure(callback)
  -- Check for user-specified python path
  local conf = require('cassandra_ai.config')
  local fcs_conf = conf:get('fimcontextserver') or {}
  local py_conf = fcs_conf.python or {}

  if py_conf.python_path then
    logger.debug('python_env: using user-specified python: ' .. py_conf.python_path)
    cached_python_path = py_conf.python_path
    callback(true, py_conf.python_path)
    return
  end

  -- Already ready?
  if M.is_ready() then
    cached_python_path = venv_dir .. '/bin/python'
    logger.trace('python_env: venv already ready')
    callback(true, cached_python_path)
    return
  end

  local env_manager = M._detect_env_manager()
  if not env_manager then
    logger.error('python_env: no Python environment manager found (need uv, python3, or conda)')
    callback(false, nil)
    return
  end

  logger.info('python_env: setting up venv using ' .. env_manager.type .. ' (' .. env_manager.executable .. ')')

  local req_path = get_requirements_path()
  local python_path = venv_dir .. '/bin/python'
  local commands = {}

  -- Ensure parent directory exists
  vim.fn.mkdir(vim.fn.fnamemodify(venv_dir, ':h'), 'p')

  if env_manager.type == 'uv' then
    commands = {
      'uv venv ' .. vim.fn.shellescape(venv_dir),
      'uv pip install -r ' .. vim.fn.shellescape(req_path) .. ' --python ' .. vim.fn.shellescape(python_path),
    }
  elseif env_manager.type == 'pip' then
    commands = {
      env_manager.executable .. ' -m venv ' .. vim.fn.shellescape(venv_dir),
      vim.fn.shellescape(python_path) .. ' -m pip install -r ' .. vim.fn.shellescape(req_path),
    }
  elseif env_manager.type == 'conda' then
    commands = {
      'conda create -p ' .. vim.fn.shellescape(venv_dir) .. ' python=3.11 -y',
      'conda run -p ' .. vim.fn.shellescape(venv_dir) .. ' pip install -r ' .. vim.fn.shellescape(req_path),
    }
  end

  run_commands_sequential(commands, function(ok)
    if ok then
      local hash = file_hash(req_path)
      if hash then
        write_marker_hash(hash)
      end
      cached_python_path = python_path
      logger.info('python_env: setup complete')
      callback(true, python_path)
    else
      logger.error('python_env: setup failed')
      callback(false, nil)
    end
  end)
end

--- Get the plugin root directory (exposed for server spawning)
M.get_plugin_root = get_plugin_root

return M
