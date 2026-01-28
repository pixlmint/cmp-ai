--- Python Language Handler
local base = require('cmp_ai.context_providers.languages.base')
local M = vim.deepcopy(base)

--- Extract imports for Python
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @return string Formatted imports
function M.extract_imports(bufnr, lines)
  local imports = {}

  -- Check first 100 lines for imports
  for i = 1, math.min(100, #lines) do
    local line = lines[i]

    -- Match import statements
    if line:match('^import%s+') or line:match('^from%s+.*import') then
      table.insert(imports, line)

      -- Limit to 15 imports
      if #imports >= 15 then
        break
      end
    end

    -- Stop at first class/function definition
    if line:match('^class%s+') or line:match('^def%s+') then
      break
    end
  end

  if #imports > 0 then
    return '# Imports:\n' .. table.concat(imports, '\n') .. '\n\n'
  end

  return ''
end

--- Check if function is private in Python
--- @param text string Function signature
--- @return boolean
function M.is_private(text)
  -- In Python, methods starting with _ or __ are private
  return text:match('def%s+_') ~= nil
end

--- Extract Python function signature with decorator
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @return string Extracted signature
function M.extract_signature(lines, start_line, end_line)
  local signature_lines = {}
  local found_decorator = false
  local found_function = false

  for i = start_line + 1, end_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture decorators (@property, @classmethod, etc.)
    if line:match('^%s*@') then
      found_decorator = true
      table.insert(signature_lines, line)
      -- Capture docstrings
    elseif line:match('^%s*"""') or line:match('^%s*\'\'\'') then
      table.insert(signature_lines, line)
      -- Continue until closing docstring
      local quote = line:match('"""') and '"""' or "'''"
      if not line:match(quote .. '.-' .. quote) then
        for j = i + 1, math.min(i + 20, #lines) do
          table.insert(signature_lines, lines[j])
          if lines[j]:match(quote) then
            break
          end
        end
      end
      -- Capture function definition
    elseif line:match('def%s+') then
      found_function = true
      table.insert(signature_lines, line)

      -- Check if signature continues on next line
      if line:match('%(%s*$') or not line:match('%):') then
        for j = i + 1, math.min(i + 5, #lines) do
          table.insert(signature_lines, lines[j])
          if lines[j]:match('%):') then
            break
          end
        end
      end
      break
    elseif (found_decorator or found_function) and line:match('^%s*#') then
      -- Include comments between decorator and function
      table.insert(signature_lines, line)
    end
  end

  return table.concat(signature_lines, '\n')
end

--- Extract Python class with methods
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @param include_private boolean Include private methods
--- @return string Formatted class context
function M.extract_class_context(bufnr, lines, start_line, end_line, include_private)
  local context_lines = {}

  -- Get class declaration and docstring
  local class_start = math.max(0, start_line - 5)
  local in_docstring = false

  for i = class_start + 1, start_line + 10 do
    if i > #lines then break end
    local line = lines[i]

    -- Capture class definition
    if line:match('class%s+') then
      table.insert(context_lines, line)
      in_docstring = true
      -- Capture class docstring
    elseif in_docstring and (line:match('^%s*"""') or line:match('^%s*\'\'\'')) then
      table.insert(context_lines, line)
      local quote = line:match('"""') and '"""' or "'''"
      if not line:match(quote .. '.-' .. quote) then
        for j = i + 1, math.min(i + 15, #lines) do
          table.insert(context_lines, lines[j])
          if lines[j]:match(quote) then
            break
          end
        end
      end
      break
    end
  end

  table.insert(context_lines, '')

  -- Extract method signatures
  for i = start_line + 1, math.min(end_line + 1, #lines) do
    local line = lines[i]

    if line:match('%s+def%s+') then
      if include_private or not M.is_private(line) then
        local sig_start = math.max(start_line, i - 6)
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

--- Python should include imports
--- @return boolean
function M.should_include_imports()
  return true
end

return M
