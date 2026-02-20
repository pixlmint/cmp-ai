--- Per-project configuration for fimcontextserver
--- Resolves project root and merges config from plugin settings + .cassandra.json
local logger = require('cassandra_ai.logger')

local M = {}

-- Caches
local root_cache = {} -- dir -> project_root or false
local config_cache = {} -- project_root -> merged config

--- Default project configuration
local defaults = {
  include_paths = {},
  model = nil,
  bm25 = false,
}

--- Walk up from filepath looking for .cassandra.json, then check known project roots
--- @param filepath string Absolute file path
--- @return string|nil project_root
function M.get_project_root(filepath)
  if not filepath or filepath == '' then
    return nil
  end

  local dir = vim.fn.fnamemodify(filepath, ':h')
  if root_cache[dir] ~= nil then
    return root_cache[dir] or nil
  end

  -- Walk up looking for .cassandra.json first (project-specific config)
  local cassandra_root = vim.fn.findfile('.cassandra.json', dir .. ';')
  if cassandra_root ~= '' then
    local root = vim.fn.fnamemodify(cassandra_root, ':h')
    root_cache[dir] = root
    return root
  end

  -- Fall back to checking if filepath is under any known project root from plugin config
  local conf = require('cassandra_ai.config')
  local projects = conf:get('projects') or {}
  for root, _ in pairs(projects) do
    if vim.startswith(filepath, root .. '/') then
      root_cache[dir] = root
      return root
    end
  end

  -- Fall back to common project root markers
  local root = vim.fs.root(filepath, { '.git', 'package.json', 'Cargo.toml', 'go.mod', 'pyproject.toml', 'Makefile', '.hg', 'flake.nix' })
  if root then
    root_cache[dir] = root
    logger.trace('project: detected project root via filesystem markers: ' .. root)
    return root
  end

  root_cache[dir] = false
  return nil
end

--- Read and parse .cassandra.json from a project root
--- @param project_root string
--- @return table|nil parsed config
local function read_local_config(project_root)
  local config_path = project_root .. '/.cassandra.json'
  local f = io.open(config_path, 'r')
  if not f then
    return nil
  end

  local content = f:read('*a')
  f:close()

  local ok, parsed = pcall(vim.json.decode, content)
  if not ok then
    logger.warn('project: failed to parse .cassandra.json at ' .. config_path .. ': ' .. tostring(parsed))
    return nil
  end

  logger.debug('project: loaded .cassandra.json from ' .. config_path)
  return parsed
end

--- Get merged config for a project root
--- Merge order: defaults < plugin config (projects[root]) < .cassandra.json
--- @param project_root string
--- @return table merged config
function M.get_config(project_root)
  if config_cache[project_root] then
    return config_cache[project_root]
  end

  local conf = require('cassandra_ai.config')

  -- Start with defaults
  local merged = vim.deepcopy(defaults)

  -- Layer plugin-level project config
  local projects = conf:get('projects') or {}
  local plugin_project = projects[project_root]
  if plugin_project then
    merged = vim.tbl_deep_extend('force', merged, plugin_project)
  end

  -- Layer .cassandra.json (highest priority)
  local local_config = read_local_config(project_root)
  if local_config then
    merged = vim.tbl_deep_extend('force', merged, local_config)
  end

  config_cache[project_root] = merged
  return merged
end

--- Clear cached config for a project root (for :Cassy fimcontextserver reload)
--- @param project_root string|nil If nil, clears all caches
function M.invalidate(project_root)
  if project_root then
    config_cache[project_root] = nil
    -- Also clear root cache entries that point to this root
    for dir, root in pairs(root_cache) do
      if root == project_root then
        root_cache[dir] = nil
      end
    end
    logger.debug('project: invalidated config for ' .. project_root)
  else
    config_cache = {}
    root_cache = {}
    logger.debug('project: invalidated all cached configs')
  end
end

return M
