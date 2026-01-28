--- PHP Language Handler
local base = require('cmp_ai.context_providers.languages.base')
local M = vim.deepcopy(base)

--- Extract imports for PHP (usually not needed due to autoloading)
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @return string Formatted imports
function M.extract_imports(bufnr, lines)
  -- PHP uses autoloading, so imports are less critical
  -- But we can extract them if needed
  local imports = {}

  for i = 1, math.min(50, #lines) do
    local line = lines[i]

    if line:match('^use%s+') then
      table.insert(imports, line)

      if #imports >= 10 then
        break
      end
    end

    -- Stop at first class/function
    if line:match('^class%s+') or line:match('^function%s+') then
      break
    end
  end

  if #imports > 0 then
    return '// Use statements:\n' .. table.concat(imports, '\n') .. '\n\n'
  end

  return ''
end

--- Check if method is private in PHP
--- @param text string Method signature
--- @return boolean
function M.is_private(text)
  return text:match('%sprivate%s') or text:match('^private%s') or text:match('private%s+function')
end

--- Extract PHP method signature with PHPDoc
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @return string Extracted signature
function M.extract_signature(lines, start_line, end_line)
  local signature_lines = {}
  local in_phpdoc = false
  local found_function = false

  for i = start_line + 1, end_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture PHPDoc comments
    if line:match('^%s*/%*%*') then
      in_phpdoc = true
      table.insert(signature_lines, line)
    elseif in_phpdoc then
      table.insert(signature_lines, line)
      if line:match('%*/') then
        in_phpdoc = false
      end
      -- Capture function/method definition
    elseif line:match('function%s+') or
        line:match('public%s+function') or
        line:match('protected%s+function') or
        line:match('private%s+function') or
        line:match('public%s+static%s+function') then
      found_function = true
      table.insert(signature_lines, line)

      -- Check for opening brace
      if line:match('{%s*$') or line:match(';%s*$') then
        break
      end
    elseif found_function then
      table.insert(signature_lines, line)
      if line:match('{%s*$') or line:match(';%s*$') then
        break
      end
    end
  end

  return table.concat(signature_lines, '\n')
end

--- Extract PHP class with methods
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @param include_private boolean Include private methods
--- @return string Formatted class context
function M.extract_class_context(bufnr, lines, start_line, end_line, include_private)
  local context_lines = {}

  -- Get class declaration and docblock
  local class_start = math.max(0, start_line - 15)
  local in_docblock = false

  for i = class_start + 1, start_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture docblock
    if line:match('^%s*/%*%*') then
      in_docblock = true
      table.insert(context_lines, line)
    elseif in_docblock then
      table.insert(context_lines, line)
      if line:match('%*/') then
        in_docblock = false
      end
      -- Capture class definition
    elseif line:match('class%s+') or line:match('interface%s+') or line:match('trait%s+') then
      table.insert(context_lines, line)
      break
    end
  end

  table.insert(context_lines, '{')
  table.insert(context_lines, '')

  -- Extract method signatures (public/protected only by default)
  for i = start_line + 1, math.min(end_line + 1, #lines) do
    local line = lines[i]

    if line:match('function%s+') or
        line:match('public%s+function') or
        line:match('protected%s+function') or
        line:match('private%s+function') then
      if include_private or not M.is_private(line) then
        local sig_start = math.max(start_line, i - 10)
        local signature = M.extract_signature(lines, sig_start, i - 1)

        if signature ~= '' then
          -- Indent methods
          for sig_line in signature:gmatch('[^\n]+') do
            table.insert(context_lines, '    ' .. sig_line)
          end
          table.insert(context_lines, '')
        end
      end
    end
  end

  table.insert(context_lines, '}')

  return table.concat(context_lines, '\n')
end

--- PHP doesn't need imports by default (autoloading)
--- @return boolean
function M.should_include_imports()
  return false
end

return M
