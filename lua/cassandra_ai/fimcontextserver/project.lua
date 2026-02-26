--- Per-project configuration for fimcontextserver
--- Delegates project root detection and config resolution to config.lua,
--- then extracts the fimcontextserver sub-table with defaults applied.
local logger = require('cassandra_ai.logger')

local M = {}

--- Default fimcontextserver project configuration
local defaults = {
  include_paths = {},
  model = nil,
  bm25 = false,
}

--- Walk up from filepath to find the project root
--- @param filepath string Absolute file path
--- @return string|nil project_root
function M.get_project_root(filepath)
  local conf = require('cassandra_ai.config')
  return conf:get_project_root(filepath)
end

--- Check if filepath belongs to a registered project (has .cassandra.json or is in config)
--- @param filepath string Absolute file path
--- @return string|nil project_root
function M.is_registered_project(filepath)
  local conf = require('cassandra_ai.config')
  return conf:is_registered_project(filepath)
end

--- Get merged fimcontextserver config for a project root
--- Resolves full effective config via config:effective(), then extracts the
--- fimcontextserver sub-table and applies fimcontextserver-specific defaults.
--- @param project_root string
--- @return table merged fimcontextserver config
function M.get_config(project_root)
  local conf = require('cassandra_ai.config')

  -- Use a synthetic filepath to resolve effective config for this root
  local effective = conf:effective(project_root .. '/.')

  -- Extract fimcontextserver sub-table and apply defaults
  local fcs_conf = effective.fimcontextserver or {}
  local merged = vim.tbl_deep_extend('force', vim.deepcopy(defaults), fcs_conf)

  return merged
end

--- Clear cached config for a project root
--- @param project_root string|nil If nil, clears all caches
function M.invalidate(project_root)
  local conf = require('cassandra_ai.config')
  conf:invalidate(project_root)
end

return M
