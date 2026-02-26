local M = {}

local conf = {
  max_lines = 50,
  -- Strategy to use for extracting code that should be sent to the model
  -- Options:
  --    lines: Just grab a preset maximum number of lines (defined by max_lines)
  --    smart: For example when writing a function, only include the
  --           function body and doc comment
  surround_extractor_strategy = 'lines', -- lines | smart
  -- List of additional context providers
  -- Builtin options:
  --    - diagnostics: Show LSP diagnostics in the current file
  --    - metadata: git branch name, project name, filename...
  --    - LSP completions
  extra_context_providers = {},
  provider = 'Ollama',
  provider_options = {},

  ignored_file_types = {
    -- default is not to ignore
    -- uncomment to ignore in lua:
    -- lua = true
  },

  logging = {
    level = 'WARN', -- TRACE | DEBUG | INFO | WARN | ERROR (set to nil to disable logging)
    file = vim.fn.stdpath('data') .. '/cassandra-ai/cassandra-ai.log',
  },

  telemetry = {
    enabled = false,
    file = vim.fn.stdpath('data') .. '/cassandra-ai/completions.jsonl',
    buffer_size = 50,
  },

  -- Context providers configuration
  context_providers = {
    providers = {},
    merge_strategy = 'concat', -- 'concat' | 'weighted' | 'custom'
    custom_merger = nil,
    timeout_ms = 500,
  },

  -- FIM context server configuration
  fimcontextserver = {
    enabled = false,
    timeout_ms = 5000,
    python = {
      env_manager = nil, -- 'uv' | 'pip' | 'conda' | nil (auto-detect)
      python_path = nil, -- skip venv entirely, use this python
    },
  },

  -- Per-project configuration overrides (keyed by project root path)
  projects = {},

  -- Suggestion completion configuration (managed by suggest/)
  suggest = {
    debounce_ms = 150,
    auto_trigger = true,
    deferred_validation = true,
    deferred_idle_ms = 1000,
    auto_trigger_overlap = '1+1',
    highlight = 'Comment',
    cmp_integration = true,
    keymap = {
      accept = '<Tab>',
      accept_line = '<M-l>',
      accept_paragraph = '<M-p>',
      dismiss = '<C-]>',
      next = '<M-]>',
      prev = '<M-[>',
      regenerate = '<C-<>',
      toggle_cmp = '<M-x>',
    },
  },
}

-- Caches for project root detection and effective config
local root_cache = {} -- dir -> project_root or false
local effective_cache = {} -- project_root -> merged config
local global_projects_json = nil -- contents of ~/.config/cassandra.json

--- Read and parse a JSON file
--- @param path string Absolute file path
--- @return table|nil parsed JSON, or nil on failure
local function read_json_file(path)
  local logger = require('cassandra_ai.logger')
  local f = io.open(path, 'r')
  if not f then
    return nil
  end

  local content = f:read('*a')
  f:close()

  local ok, parsed = pcall(vim.json.decode, content)
  if not ok then
    logger.warn('config: failed to parse JSON at ' .. path .. ': ' .. tostring(parsed))
    return nil
  end

  return parsed
end

--- Read ~/.config/cassandra.json (global per-project overrides)
--- @return table dict of project_root -> config overrides
local function read_global_projects_config()
  local logger = require('cassandra_ai.logger')
  local path = vim.fn.expand('~/.config/cassandra.json')
  local parsed = read_json_file(path)
  if parsed then
    logger.debug('config: loaded global projects config from ' .. path)
  end
  return parsed or {}
end

--- Walk up from filepath looking for .cassandra.json, then check known project roots,
--- then fall back to filesystem markers (.git, etc.)
--- @param filepath string Absolute file path
--- @return string|nil project_root
function M:get_project_root(filepath)
  if not filepath or filepath == '' then
    return nil
  end

  local dir = vim.fn.fnamemodify(filepath, ':h')
  if root_cache[dir] ~= nil then
    return root_cache[dir] or nil
  end

  local logger = require('cassandra_ai.logger')

  -- Walk up looking for .cassandra.json first (project-specific config)
  local cassandra_root = vim.fn.findfile('.cassandra.json', dir .. ';')
  if cassandra_root ~= '' then
    local root = vim.fn.fnamemodify(cassandra_root, ':h')
    root_cache[dir] = root
    return root
  end

  -- Check if filepath is under any known project root from plugin config
  local projects = conf.projects or {}
  for root, _ in pairs(projects) do
    if vim.startswith(filepath, root .. '/') then
      root_cache[dir] = root
      return root
    end
  end

  -- Check if filepath is under any known project root from global JSON config
  local global_json = global_projects_json or {}
  for root, _ in pairs(global_json) do
    if vim.startswith(filepath, root .. '/') then
      root_cache[dir] = root
      return root
    end
  end

  -- Fall back to common project root markers
  local root = vim.fs.root(filepath, { '.git', 'package.json', 'Cargo.toml', 'go.mod', 'pyproject.toml', 'Makefile', '.hg', 'flake.nix' })
  if root then
    root_cache[dir] = root
    logger.trace('config: detected project root via filesystem markers: ' .. root)
    return root
  end

  root_cache[dir] = false
  return nil
end

--- Check if filepath belongs to a registered project (has .cassandra.json, is in
--- config.projects, or is in ~/.config/cassandra.json). Unlike get_project_root(),
--- this skips the generic filesystem marker fallback (.git, etc.)
--- @param filepath string Absolute file path
--- @return string|nil project_root
function M:is_registered_project(filepath)
  if not filepath or filepath == '' then
    return nil
  end

  local dir = vim.fn.fnamemodify(filepath, ':h')

  -- Walk up looking for .cassandra.json
  local cassandra_root = vim.fn.findfile('.cassandra.json', dir .. ';')
  if cassandra_root ~= '' then
    local root = vim.fn.fnamemodify(cassandra_root, ':h')
    return root
  end

  -- Check if filepath is under any known project root from plugin config
  local projects = conf.projects or {}
  for root, _ in pairs(projects) do
    if vim.startswith(filepath, root .. '/') then
      return root
    end
  end

  -- Check if filepath is under any known project root from global JSON config
  local global_json = global_projects_json or {}
  for root, _ in pairs(global_json) do
    if vim.startswith(filepath, root .. '/') then
      return root
    end
  end

  return nil
end

--- Get fully resolved config for a file's project.
--- Resolution order: defaults+setup < ~/.config/cassandra.json[root] < projects[root] < .cassandra.json
--- @param filepath string Absolute file path
--- @return table effective config (full plugin config with project overrides applied)
function M:effective(filepath)
  local root = self:get_project_root(filepath)
  if not root then
    return conf
  end

  if effective_cache[root] then
    return effective_cache[root]
  end

  local logger = require('cassandra_ai.logger')

  -- Start with global conf (defaults + setup params already merged)
  local merged = vim.deepcopy(conf)

  -- Layer 1: ~/.config/cassandra.json[root]
  local global_json = global_projects_json or {}
  local global_overrides = global_json[root]
  if global_overrides then
    logger.trace('config:effective() -> applying global JSON overrides for ' .. root)
    merged = vim.tbl_deep_extend('force', merged, global_overrides)
  end

  -- Layer 2: setup().projects[root]
  local project_overrides = conf.projects[root]
  if project_overrides then
    logger.trace('config:effective() -> applying setup() project overrides for ' .. root)
    merged = vim.tbl_deep_extend('force', merged, project_overrides)
  end

  -- Layer 3: .cassandra.json in project root (highest priority)
  local local_json = read_json_file(root .. '/.cassandra.json')
  if local_json then
    logger.trace('config:effective() -> applying .cassandra.json overrides from ' .. root)
    merged = vim.tbl_deep_extend('force', merged, local_json)
  end

  effective_cache[root] = merged
  return merged
end

--- Clear cached config for a project root
--- @param project_root string|nil If nil, clears all caches
function M:invalidate(project_root)
  local logger = require('cassandra_ai.logger')
  if project_root then
    effective_cache[project_root] = nil
    -- Also clear root cache entries that point to this root
    for dir, root in pairs(root_cache) do
      if root == project_root then
        root_cache[dir] = nil
      end
    end
    logger.debug('config: invalidated caches for ' .. project_root)
  else
    effective_cache = {}
    root_cache = {}
    -- Re-read global projects config
    global_projects_json = read_global_projects_config()
    logger.debug('config: invalidated all caches')
  end
end

function M:setup(params)
  params = params or {}

  -- Store the old provider name if it exists
  local old_provider_name = nil
  if type(conf.provider) == 'table' and conf.provider.name then
    old_provider_name = conf.provider.name
  end

  conf = vim.tbl_deep_extend('force', conf, params)

  -- Initialize logger first so other setup steps can log
  local logger = require('cassandra_ai.logger')
  logger.init({
    log_file = conf.logging.file,
    log_level = conf.logging.level,
  })

  logger.trace('config:setup()')

  -- Read global per-project config file
  global_projects_json = read_global_projects_config()

  require('cassandra_ai.suggest').setup(conf.suggest)

  -- Determine the new provider name
  local new_provider_name = type(conf.provider) == 'string' and conf.provider or conf.provider.name

  -- Only reinitialize if the provider changed or if it's not initialized yet
  if type(conf.provider) == 'string' or (old_provider_name and old_provider_name ~= new_provider_name) then
    local provider_name = type(conf.provider) == 'string' and conf.provider:lower() or conf.provider.name:lower()
    logger.trace('config:setup() -> loading adapter: ' .. provider_name)
    local status, provider = pcall(require, 'cassandra_ai.adapters.' .. provider_name)
    if status then
      conf.provider = provider:new(conf.provider_options)
      conf.provider.name = provider_name
      logger.debug('provider loaded: ' .. provider_name)

      if old_provider_name and old_provider_name:lower() ~= provider_name then
        logger.info('switched provider from ' .. old_provider_name .. ' to ' .. provider_name)
      end
    else
      logger.error('failed to load provider: ' .. provider_name .. ' — ' .. tostring(provider))
    end
  end

  if conf.provider_options and conf.provider_options.model_configs then
    local formatters = require('cassandra_ai.prompt_formatters')
    for _, model_params in pairs(conf.provider_options.model_configs) do
      if model_params.formatter and type(model_params.formatter) == 'string' then
        if formatters[model_params.formatter] == nil then
          logger.error('Unknown formatter: ' .. model_params.formatter)
        else
          model_params.formatter = formatters[model_params.formatter]
        end
      end
    end
  end

  -- Initialize telemetry if data collection is enabled
  if conf.telemetry.enabled then
    logger.debug('telemetry enabled, data file: ' .. conf.telemetry.file)
    local telemetry = require('cassandra_ai.telemetry')
    telemetry:init({
      enabled = true,
      data_file = conf.telemetry.file,
      buffer_size = conf.telemetry.buffer_size,
    })
  end

  -- Initialize context providers if any are configured
  if conf.context_providers and conf.context_providers.providers and #conf.context_providers.providers > 0 then
    logger.debug('initializing context providers: ' .. #conf.context_providers.providers .. ' configured')
    local context_manager = require('cassandra_ai.context')
    context_manager.setup(conf.context_providers)
  end

  -- Auto-register fimcontextserver context provider if enabled
  if conf.fimcontextserver and conf.fimcontextserver.enabled then
    local context_manager = require('cassandra_ai.context')
    local has_it = false
    for _, p in ipairs(conf.context_providers.providers or {}) do
      if (type(p) == 'string' and p == 'fimcontextserver') or (type(p) == 'table' and p.name == 'fimcontextserver') then
        has_it = true
        break
      end
    end
    if not has_it then
      logger.debug('auto-registering fimcontextserver context provider')
      context_manager.register_provider({ name = 'fimcontextserver', opts = conf.fimcontextserver })
    end
    -- Auto-start fimcontextserver if current project is registered
    vim.schedule(function()
      local filepath = vim.api.nvim_buf_get_name(0)
      if filepath == '' then
        filepath = vim.fn.getcwd() .. '/.'
      end
      local root = self:is_registered_project(filepath)
      if root then
        local fcs = require('cassandra_ai.fimcontextserver')
        local project = require('cassandra_ai.fimcontextserver.project')
        local proj_conf = project.get_config(root)
        logger.info('fimcontextserver: auto-starting for registered project ' .. root)
        fcs.get_or_start(root, proj_conf, function(ok)
          if ok then
            logger.info('fimcontextserver: auto-start complete')
          else
            logger.warn('fimcontextserver: auto-start failed')
          end
        end)
      end
    end)
  end

  logger.debug('cassandra-ai setup complete')
end

function M:get(what)
  return conf[what]
end

function M:set(key, value)
  conf[key] = value
end

return M
