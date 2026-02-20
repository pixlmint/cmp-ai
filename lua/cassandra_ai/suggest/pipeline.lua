local conf = require('cassandra_ai.config')
local logger = require('cassandra_ai.logger')
local state = require('cassandra_ai.suggest.state')
local renderer = require('cassandra_ai.suggest.renderer')
local postprocess = require('cassandra_ai.suggest.postprocess')
local validation = require('cassandra_ai.suggest.validation')
local util = require('cassandra_ai.util')

local M = {}

--- Resolve the prompt formatter from model info and config.
local function resolve_formatter(model_info)
  local formatters = require('cassandra_ai.prompt_formatters')
  local fmt = (model_info and model_info.formatter) or conf:get('formatter') or formatters.fim
  if type(fmt) == 'string' then
    if formatters[fmt] then
      fmt = formatters[fmt]
    else
      logger.warn('config: unknown formatter "' .. fmt .. '", falling back to fim')
      fmt = formatters.fim
    end
  end
  return fmt
end

--- Handle a completion response from the provider.
local function handle_completion_response(req, data)
  state.current_job = nil
  local elapsed_ms = (os.clock() - req.start_time) * 1000
  local telemetry = require('cassandra_ai.telemetry')
  telemetry:log_response(req.request_id, {
    response_raw = data,
    response_time_ms = elapsed_ms,
  })

  if req.gen ~= state.generation then
    logger.trace('on_complete() -> discarding: stale generation')
    return
  end
  if not vim.api.nvim_buf_is_valid(state.bufnr) then
    logger.trace('on_complete() -> discarding: buffer invalid')
    validation.clear_validation_state()
    return
  end
  if vim.fn.mode() ~= 'i' then
    logger.trace('on_complete() -> discarding: left insert mode')
    validation.clear_validation_state()
    return
  end

  local cur = vim.api.nvim_win_get_cursor(0)
  local sc = conf:get('suggest')
  local use_deferred = state.auto_triggered and sc.deferred_validation

  if use_deferred then
    if cur[1] ~= state.cursor_pos[1] then
      logger.trace('on_complete() -> discarding: cursor moved to different line')
      validation.clear_validation_state()
      return
    end
  else
    if cur[1] ~= state.cursor_pos[1] or cur[2] ~= state.cursor_pos[2] then
      logger.trace('on_complete() -> discarding: cursor moved')
      return
    end
  end

  vim.api.nvim_exec_autocmds({ 'User' }, {
    pattern = 'CassandraAiRequestComplete',
  })

  if not data or #data == 0 then
    logger.trace('on_complete() -> no completions returned')
    validation.clear_validation_state()
    return
  end

  postprocess.postprocess_completions(data, req.before, req.after)

  logger.info(string.format('completion received: %d item(s) in %.0fms', #data, elapsed_ms))

  if use_deferred then
    state.pending_validation = {
      completions = data,
      trigger_pos = state.cursor_pos,
      trigger_bufnr = state.bufnr,
      trigger_line_text = vim.api.nvim_buf_get_lines(state.bufnr, state.cursor_pos[1] - 1, state.cursor_pos[1], false)[1] or '',
      request_id = state.current_request_id,
    }
    logger.trace('on_complete() -> deferred: stored ' .. #data .. ' completion(s) for validation')
    validation.validate_or_defer()
  else
    state.completions = data
    state.current_index = 1
    renderer.render(state.completions[state.current_index])
  end
end

--- Build prompt and send the completion request.
local function dispatch_request(req, service, fmt, model_info, additional_context)
  if req.gen ~= state.generation then
    return
  end
  req.start_time = os.clock()
  local prompt_data = fmt(req.before, req.after, { filetype = req.ft, rejected_completions = req.rejected }, additional_context)

  local provider = conf:get('provider')
  require('cassandra_ai.telemetry'):log_request(req.request_id, {
    cwd = vim.fn.getcwd(),
    filename = vim.api.nvim_buf_get_name(0),
    filetype = req.ft,
    cursor = { line = state.cursor_pos[1], col = state.cursor_pos[2] },
    lines_before = req.before,
    lines_after = req.after,
    provider = provider.name,
    provider_config = util.safe_serialize_config(provider.params),
    model = model_info and model_info.model,
    prompt_data = prompt_data,
    additional_context = additional_context,
  })

  state.current_job = service:complete(prompt_data, function(data)
    handle_completion_response(req, data)
  end, model_info or {})
end

--- Gather additional context (if enabled) and dispatch the request.
function M.gather_and_dispatch(req, service, fmt, model_info)
  local context_manager = require('cassandra_ai.context')
  local supports_context = require('cassandra_ai.prompt_formatters').supports_context[fmt]

  if context_manager.is_enabled() and supports_context then
    logger.trace('gather_and_dispatch() -> collecting context')
    local params = {
      bufnr = state.bufnr,
      cursor_pos = { line = state.cursor_pos[1] - 1, col = state.cursor_pos[2] },
      lines_before = req.before,
      lines_after = req.after,
      filetype = req.ft,
    }
    context_manager.gather_context(params, function(additional_context)
      dispatch_request(req, service, fmt, model_info, additional_context)
    end)
  else
    dispatch_request(req, service, fmt, model_info, nil)
  end
end

--- Extract surrounding context using the configured strategy.
function M.extract_surround(req, callback)
  local surround_extractor = require('cassandra_ai.context.surround_extractor')
  local ctx = {
    cursor = { line = state.cursor_pos[1], col = state.cursor_pos[2] },
    bufnr = state.bufnr,
  }
  local strategy = conf:get('surround_extractor_strategy')
  if strategy == 'smart' then
    require('cassandra_ai.context.utils').detect_suggestion_context(state.bufnr, state.cursor_pos, function(current_context)
      if req.gen ~= state.generation then
        return
      end
      ctx.current_context = current_context
      callback(surround_extractor.smart_extractor(ctx))
    end)
  else
    callback(surround_extractor.simple_extractor(ctx))
  end
end

M.resolve_formatter = resolve_formatter

return M
