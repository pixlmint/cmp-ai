--- JavaScript/TypeScript Language Handler
local base = require('cmp_ai.context_providers.languages.base')
local M = vim.deepcopy(base)

--- Extract imports for JavaScript/TypeScript
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @return string Formatted imports
function M.extract_imports(bufnr, lines)
  local imports = {}

  for i = 1, math.min(80, #lines) do
    local line = lines[i]

    -- Match import statements
    if line:match('^import%s+') or line:match('^import%s*{') or line:match('^import%s*type') then
      table.insert(imports, line)

      if #imports >= 15 then
        break
      end
    end

    -- Stop at first function/class
    if line:match('^function%s+') or line:match('^class%s+') or line:match('^const%s+') or line:match('^export') then
      if not line:match('import') then
        break
      end
    end
  end

  if #imports > 0 then
    return '// Imports:\n' .. table.concat(imports, '\n') .. '\n\n'
  end

  return ''
end

--- Check if method is private (TypeScript)
--- @param text string Method signature
--- @return boolean
function M.is_private(text)
  return text:match('%sprivate%s') or text:match('^%s*private%s') or text:match('#')
end

--- Extract JavaScript/TypeScript function signature with JSDoc
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @return string Extracted signature
function M.extract_signature(lines, start_line, end_line)
  local signature_lines = {}
  local in_jsdoc = false
  local found_function = false

  for i = start_line + 1, end_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture JSDoc comments
    if line:match('^%s*/%*%*') then
      in_jsdoc = true
      table.insert(signature_lines, line)
    elseif in_jsdoc then
      table.insert(signature_lines, line)
      if line:match('%*/') then
        in_jsdoc = false
      end
      -- Capture function definitions (various forms)
    elseif line:match('function%s+') or
        line:match('async%s+function') or
        line:match('const%s+%w+%s*=%s*%(') or
        line:match('const%s+%w+%s*=%s*async') or
        line:match('%s*%w+%s*%(') or    -- method definition
        line:match('public%s+') or line:match('private%s+') or line:match('protected%s+') then
      found_function = true
      table.insert(signature_lines, line)

      -- For arrow functions and regular functions
      if line:match('{%s*$') or line:match('=>%s*{') then
        break
      end
    elseif found_function then
      table.insert(signature_lines, line)
      if line:match('{%s*$') or line:match('=>%s*{') then
        break
      end
    end
  end

  return table.concat(signature_lines, '\n')
end

--- Extract JavaScript/TypeScript class with methods
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @param include_private boolean Include private methods
--- @return string Formatted class context
function M.extract_class_context(bufnr, lines, start_line, end_line, include_private)
  local context_lines = {}

  -- Get class declaration
  local class_start = math.max(0, start_line - 10)
  local in_jsdoc = false

  for i = class_start + 1, start_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture JSDoc
    if line:match('^%s*/%*%*') then
      in_jsdoc = true
      table.insert(context_lines, line)
    elseif in_jsdoc then
      table.insert(context_lines, line)
      if line:match('%*/') then
        in_jsdoc = false
      end
      -- Capture class definition (including extends/implements)
    elseif line:match('class%s+') or line:match('interface%s+') then
      table.insert(context_lines, line)
      -- Check if extends/implements continues on next line
      if not line:match('{') then
        for j = i + 1, math.min(i + 3, #lines) do
          table.insert(context_lines, lines[j])
          if lines[j]:match('{') then
            break
          end
        end
      end
      break
    end
  end

  table.insert(context_lines, '')

  -- Extract method/property signatures
  for i = start_line + 1, math.min(end_line + 1, #lines) do
    local line = lines[i]

    -- Match methods (including TypeScript modifiers)
    if line:match('%s*%w+%s*%(') or
        line:match('async%s+%w+') or
        line:match('public%s+') or line:match('private%s+') or line:match('protected%s+') or
        line:match('static%s+') or
        line:match('get%s+%w+') or line:match('set%s+%w+') then
      if include_private or not M.is_private(line) then
        local sig_start = math.max(start_line, i - 8)
        local signature = M.extract_signature(lines, sig_start, i - 1)

        if signature ~= '' then
          table.insert(context_lines, signature)
          table.insert(context_lines, '')
        end
      end
    end
  end

  return table.concat(context_lines, '\n')
end

--- JavaScript/TypeScript should include imports
--- @return boolean
function M.should_include_imports()
  return true
end

return M
