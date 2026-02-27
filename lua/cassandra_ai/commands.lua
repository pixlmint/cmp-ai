--- User commands for cassandra-ai
local M = {}
local util = require('cassandra_ai.util')

--- Creates an autocompletion function for a command tree
--- @param commands table The command tree structure
--- @return function Autocompletion function compatible with nvim_create_user_command
function create_completer(commands)
  return function(arglead, cmdline, _)
    local words = vim.split(cmdline, ' ')
    local current = commands
    local last_word = words[#words - 1]

    -- Traverse the command tree following subcommands
    for i = 2, #words do
      if current[words[i]] then
        if current[words[i]].subcommands then
          current = current[words[i]].subcommands
        else
          last_word = words[i]
          break
        end
      else
        break
      end
    end

    -- Handle options completion (flags starting with -)
    if current[last_word] and current[last_word].options and words[#words]:sub(1, 1) == '-' then
      local option_names = {}
      for opt, _ in pairs(current[last_word].options) do
        table.insert(option_names, opt)
      end
      return util.filter_completions(option_names, words[#words])
    end

    -- Use custom completion function if available
    if current[last_word] and current[last_word].complete then
      return current[last_word].complete(arglead)
    end

    -- Complete available commands at this level
    local cmds = {}
    for cmd in pairs(current) do
      table.insert(cmds, cmd)
    end
    return util.filter_completions(cmds, arglead)
  end
end

--- Creates a command dispatcher for a command tree
--- @param commands table The command tree structure
--- @return function Dispatcher function that executes commands
function create_dispatcher(commands)
  return function(args)
    local current = commands

    -- Traverse command tree to find the execute function
    for i = 1, #args do
      if current[args[i]] and current[args[i]].subcommands then
        -- Move deeper into subcommands
        current = current[args[i]].subcommands
      elseif current[args[i]] and current[args[i]].execute then
        -- Found executable command, run it with remaining args
        current[args[i]].execute(vim.list_slice(args, i + 1))
        return
      else
        vim.notify('Unknown command: ' .. args[i], vim.log.levels.ERROR)
        return
      end
    end

    vim.notify('Incomplete command. Please specify a subcommand.', vim.log.levels.WARN)
  end
end

--- Registers a user command with the given command tree
--- @param name string The command name (e.g., "Docker")
--- @param commands table The command tree structure
--- @param opts table|nil Optional configuration (e.g., { nargs = "*" })
local function register_command(name, commands, opts)
  opts = opts or {}

  local dispatcher = create_dispatcher(commands)
  local completer = create_completer(commands)

  vim.api.nvim_create_user_command(
    name,
    function(cmd_opts)
      local args = vim.split(cmd_opts.args, ' ', { trimempty = true })
      dispatcher(args)
    end,
    vim.tbl_extend('force', {
      nargs = '*',
      complete = completer,
    }, opts)
  )
end

--- Show context from a specific provider in a popup
--- @param provider_name string The name of the provider to test
local function show_context(provider_name)
  local context_manager = require('cassandra_ai.context')

  if not context_manager.is_enabled() then
    vim.notify("Context providers are not configured. Add providers to context_providers.providers in your config.\nExample: context_providers = { providers = {'lsp', 'treesitter'} }", vim.log.levels.WARN)
    return
  end

  -- Get current buffer info
  local bufnr = vim.api.nvim_get_current_buf()
  local cursor = vim.api.nvim_win_get_cursor(0)
  local cursor_pos = { line = cursor[1] - 1, col = cursor[2] }
  local filetype = vim.bo.filetype

  -- Get context lines
  local conf = require('cassandra_ai.config')
  local max_lines = conf:get('max_lines') or 50

  local cur_line = vim.api.nvim_get_current_line()
  local cur_line_before = vim.fn.strpart(cur_line, 0, math.max(cursor_pos.col, 0), true)
  local cur_line_after = vim.fn.strpart(cur_line, math.max(cursor_pos.col, 0), vim.fn.strdisplaywidth(cur_line), true)

  local lines_before = vim.api.nvim_buf_get_lines(bufnr, math.max(0, cursor_pos.line - max_lines), cursor_pos.line, false)
  table.insert(lines_before, cur_line_before)
  local before = table.concat(lines_before, '\n')

  local lines_after = vim.api.nvim_buf_get_lines(bufnr, cursor_pos.line + 1, cursor_pos.line + max_lines, false)
  table.insert(lines_after, 1, cur_line_after)
  local after = table.concat(lines_after, '\n')

  -- Prepare context parameters
  local params = {
    bufnr = bufnr,
    cursor_pos = cursor_pos,
    lines_before = before,
    lines_after = after,
    filetype = filetype,
  }

  -- Find the requested provider
  local providers = context_manager.get_providers()
  local target_provider = nil

  for _, provider_data in ipairs(providers) do
    if provider_data.name == provider_name then
      target_provider = provider_data
      break
    end
  end

  if not target_provider then
    local available = {}
    for _, p in ipairs(providers) do
      table.insert(available, p.name)
    end

    vim.notify(string.format('Provider "%s" not found or not enabled.\nAvailable providers: %s', provider_name, table.concat(available, ', ')), vim.log.levels.ERROR)
    return
  end

  -- Show loading message
  vim.notify('Gathering context from "' .. provider_name .. '"...', vim.log.levels.INFO)

  -- Get context from provider
  local success, err = pcall(function()
    target_provider.instance:get_context(params, function(result)
      -- Format content
      local lines = {
        '# Context from provider: ' .. provider_name,
        '',
        '## Metadata',
      }

      -- Add metadata lines
      local metadata_str = vim.inspect(result.metadata)
      local metadata_lines = vim.split(metadata_str, '\n', { plain = true })
      for _, line in ipairs(metadata_lines) do
        table.insert(lines, line)
      end

      table.insert(lines, '')
      table.insert(lines, '## Content')
      table.insert(lines, '')

      -- Add content lines
      if result.content and result.content ~= '' then
        local content_lines = vim.split(result.content, '\n', { plain = true })
        for _, line in ipairs(content_lines) do
          table.insert(lines, line)
        end
      else
        table.insert(lines, '(no content)')
      end

      table.insert(lines, '')
      table.insert(lines, '---')
      table.insert(lines, 'Press q to close')

      util.create_popup(lines, 'Context: ' .. provider_name)
      vim.notify('Context retrieved successfully', vim.log.levels.INFO)
    end)
  end)

  if not success then
    vim.notify('Error getting context from provider "' .. provider_name .. '": ' .. tostring(err), vim.log.levels.ERROR)
  end
end

--- Setup user commands
function M.setup()
  local commands = {
    context = {
      description = 'Show context from a specific context provider',
      complete = function(arglead)
        local context_manager = require('cassandra_ai.context')

        if not context_manager.is_enabled() then
          return {}
        end

        local providers = context_manager.get_providers()
        local names = {}
        for _, provider_data in ipairs(providers) do
          table.insert(names, provider_data.name)
        end
        return util.filter_completions(names, arglead)
      end,
      execute = function(opts)
        local provider_name = opts[1]

        if not provider_name or provider_name == '' then
          vim.notify('Usage: :CassandraAiContext <provider_name>\nExample: :CassandraAiContext lsp', vim.log.levels.ERROR)
          return
        end

        show_context(provider_name)
      end,
    },
    log = {
      description = 'Open the cassandra-ai log file',
      execute = function(_)
        local logger = require('cassandra_ai.logger')
        local log_file = logger.get_log_file()

        if not log_file then
          vim.notify('No log file configured', vim.log.levels.WARN)
          return
        end

        if vim.fn.filereadable(log_file) == 0 then
          vim.notify('Log file does not exist yet: ' .. log_file, vim.log.levels.INFO)
          return
        end

        vim.cmd('tabnew | edit ' .. vim.fn.fnameescape(log_file))
      end,
    },
    config = {
      description = 'Change configuration at runtime',
      subcommands = {
        auto_trigger = util.create_toggle_command('auto_trigger', function()
          local conf = require('cassandra_ai.config')
          return conf:get('suggest').auto_trigger
        end, function(enabled)
          local conf = require('cassandra_ai.config')
          conf:get('suggest').auto_trigger = enabled
        end),
        telemetry = util.create_toggle_command('telemetry', function()
          local telemetry = require('cassandra_ai.telemetry')
          return telemetry:is_enabled()
        end, function(enabled)
          local conf = require('cassandra_ai.config')
          local telemetry = require('cassandra_ai.telemetry')
          telemetry:set_enabled(enabled)
          conf:set('collect_data', enabled)
        end),
        log_level = {
          description = 'Set the log level',
          complete = function(arglead)
            return util.filter_completions({ 'TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR' }, arglead:upper())
          end,
          execute = function(opts)
            local level = opts[1]
            if not level then
              vim.notify('Usage: :Cassy config log_level TRACE|DEBUG|INFO|WARN|ERROR', vim.log.levels.ERROR)
              return
            end

            local logger = require('cassandra_ai.logger')
            local levels = logger.get_levels()
            if not levels[level:upper()] then
              vim.notify('Invalid log level: ' .. level .. '. Use TRACE, DEBUG, INFO, WARN, or ERROR', vim.log.levels.ERROR)
              return
            end

            logger.set_log_level(level)
            vim.notify('log_level: ' .. level:upper(), vim.log.levels.INFO)
          end,
        },
        model = {
          description = 'Set the Ollama model override',
          complete = function(arglead)
            local conf = require('cassandra_ai.config')
            local provider = conf:get('provider')
            local candidates = { 'auto' }

            if provider and provider.params and provider.params.model_configs then
              for name, _ in pairs(provider.params.model_configs) do
                table.insert(candidates, name)
              end
            end

            return util.filter_completions(candidates, arglead)
          end,
          execute = function(opts)
            local model_name = opts[1]
            if not model_name then
              vim.notify('Usage: :Cassy config model <model_name|auto>', vim.log.levels.ERROR)
              return
            end

            local conf = require('cassandra_ai.config')
            local provider = conf:get('provider')

            if not provider or not provider.set_model_override then
              vim.notify('Model override is only supported for the Ollama backend', vim.log.levels.ERROR)
              return
            end

            provider:set_model_override(model_name)
            if model_name == 'auto' then
              vim.notify('model: automatic selection', vim.log.levels.INFO)
            else
              vim.notify('model: ' .. model_name, vim.log.levels.INFO)
            end
          end,
        },
        print = {
          description = 'Show resolved configuration in a popup',
          execute = function()
            local conf = require('cassandra_ai.config')
            local filepath = vim.api.nvim_buf_get_name(0)
            local effective = conf:effective(filepath)
            local sanitized = util.safe_serialize_config(effective)
            local text = vim.inspect(sanitized)
            local lines = vim.split(text, '\n', { trimempty = true })
            util.create_popup(lines, 'Cassy Config', { filetype = 'lua' })
          end,
        },
      },
    },
    fimcontextserver = {
      description = 'Manage the FIM context server',
      subcommands = {
        setup = {
          description = 'Set up the Python environment for fimcontextserver',
          execute = function(_)
            local python_env = require('cassandra_ai.fimcontextserver.python_env')
            vim.notify('Setting up Python environment...', vim.log.levels.INFO)
            python_env.ensure(function(ok, python_path)
              if ok then
                vim.notify('Python environment ready: ' .. (python_path or '?'), vim.log.levels.INFO)
              else
                vim.notify('Python environment setup failed. Check :Cassy log for details.', vim.log.levels.ERROR)
              end
            end)
          end,
        },
        status = {
          description = 'Show fimcontextserver status for the current project',
          execute = function(_)
            local fcs = require('cassandra_ai.fimcontextserver')
            local status = fcs.get_status()
            local parts = { 'fimcontextserver: ' .. status.status }
            if status.project_root then
              table.insert(parts, 'project: ' .. status.project_root)
            end
            if status.file_count then
              table.insert(parts, 'files: ' .. status.file_count)
            end
            if status.bm25_chunks then
              table.insert(parts, 'BM25 chunks: ' .. status.bm25_chunks)
            end
            if status.restart_count > 0 then
              table.insert(parts, 'restarts: ' .. status.restart_count)
            end
            vim.notify(table.concat(parts, '\n'), vim.log.levels.INFO)
          end,
        },
        restart = {
          description = 'Restart fimcontextserver for the current project',
          execute = function(_)
            local fcs = require('cassandra_ai.fimcontextserver')
            local project = require('cassandra_ai.fimcontextserver.project')
            fcs.shutdown()
            local filepath = vim.api.nvim_buf_get_name(0)
            local root = project.get_project_root(filepath)
            if root then
              local proj_conf = project.get_config(root)
              vim.notify('Restarting fimcontextserver...', vim.log.levels.INFO)
              fcs.get_or_start(root, proj_conf, function(ok)
                if ok then
                  vim.notify('fimcontextserver restarted', vim.log.levels.INFO)
                else
                  vim.notify('fimcontextserver restart failed', vim.log.levels.ERROR)
                end
              end)
            else
              vim.notify('No project root found for current file', vim.log.levels.WARN)
            end
          end,
        },
        debug = {
          description = 'Show project root, config, server status, and context for current cursor',
          execute = function(_)
            local project = require('cassandra_ai.fimcontextserver.project')
            local fcs = require('cassandra_ai.fimcontextserver')

            local bufnr = vim.api.nvim_get_current_buf()
            local filepath = vim.api.nvim_buf_get_name(bufnr)
            local root = project.get_project_root(filepath)
            local status = fcs.get_status()

            local conf = require('cassandra_ai.config')

            local lines = {
              '# fimcontextserver debug',
              '',
              '## Project',
              'filepath: ' .. (filepath ~= '' and filepath or '(unnamed buffer)'),
              'project_root: ' .. (root or '(none)'),
              '',
              '## fimcontextserver Config',
            }

            if root then
              local fcs_conf = project.get_config(root)
              for _, line in ipairs(vim.split(vim.inspect(fcs_conf), '\n', { plain = true })) do
                table.insert(lines, line)
              end

              table.insert(lines, '')
              table.insert(lines, '## Effective Config (all overrides merged)')
              local effective = conf:effective(filepath)
              for _, line in ipairs(vim.split(vim.inspect(effective), '\n', { plain = true })) do
                table.insert(lines, line)
              end
            else
              table.insert(lines, '(no project root — cannot resolve config)')
            end

            table.insert(lines, '')
            table.insert(lines, '## Server Status')
            table.insert(lines, 'status: ' .. status.status)
            table.insert(lines, 'server project_root: ' .. (status.project_root or '(none)'))
            table.insert(lines, 'file_count: ' .. (status.file_count or '?'))
            table.insert(lines, 'bm25_chunks: ' .. (status.bm25_chunks or '?'))
            table.insert(lines, 'restart_count: ' .. (status.restart_count or 0))

            -- If no root or server not ready, show what we have
            if not root or status.status ~= 'ready' then
              table.insert(lines, '')
              table.insert(lines, '## Context')
              table.insert(lines, '(server not ready — cannot fetch context)')
              table.insert(lines, '')
              table.insert(lines, '---')
              table.insert(lines, 'Press q to close')
              util.create_popup(lines, 'fimcontextserver debug')
              return
            end

            -- Fetch actual context
            local cursor = vim.api.nvim_win_get_cursor(0)
            local cursor_line = cursor[1] - 1
            local cursor_col = cursor[2]
            local all_lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
            local content = table.concat(all_lines, '\n')

            local byte_offset = 0
            for i = 1, cursor_line do
              byte_offset = byte_offset + #all_lines[i] + 1
            end
            byte_offset = byte_offset + cursor_col

            table.insert(lines, '')
            table.insert(lines, '## Context Request')
            table.insert(lines, 'cursor: line ' .. (cursor_line + 1) .. ', col ' .. cursor_col)
            table.insert(lines, 'byte_offset: ' .. byte_offset)
            table.insert(lines, 'content_length: ' .. #content)

            fcs.request('getContext', {
              filepath = filepath,
              content = content,
              cursor_offset = byte_offset,
              debug = true,
            }, function(result, err)
              vim.schedule(function()
                table.insert(lines, '')
                table.insert(lines, '## Context Result')

                if err then
                  table.insert(lines, 'ERROR: ' .. (err.message or vim.inspect(err)))
                elseif result and result.context and result.context ~= '' then
                  table.insert(lines, 'length: ' .. #result.context .. ' chars')
                  table.insert(lines, '')
                  for _, line in ipairs(vim.split(result.context, '\n', { plain = true })) do
                    table.insert(lines, line)
                  end
                else
                  table.insert(lines, '(empty context)')
                end

                table.insert(lines, '')
                table.insert(lines, '---')
                table.insert(lines, 'Press q to close')
                util.create_popup(lines, 'fimcontextserver debug')
              end)
            end)
          end,
        },
        reload = {
          description = 'Re-read config files for the current project',
          execute = function(_)
            local conf = require('cassandra_ai.config')
            local project = require('cassandra_ai.fimcontextserver.project')
            local filepath = vim.api.nvim_buf_get_name(0)
            local root = project.get_project_root(filepath)
            if root then
              conf:invalidate(root)
              local new_conf = project.get_config(root)
              vim.notify('Reloaded config for ' .. root .. '\n' .. vim.inspect(new_conf), vim.log.levels.INFO)
            else
              vim.notify('No project root found for current file', vim.log.levels.WARN)
            end
          end,
        },
      },
    },
  }

  register_command('Cassy', commands)
end

return M
