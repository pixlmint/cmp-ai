--- Base Language Handler
--- Defines the interface for language-specific context extraction

local M = {}

--- Extract imports/use statements for this language
--- @param bufnr number Buffer number
--- @param lines table Buffer lines
--- @return string Formatted imports
function M.extract_imports(bufnr, lines)
  return ''
end

--- Check if method/function is private based on language conventions
--- @param text string Function/method signature
--- @return boolean
function M.is_private(text)
  return false
end

--- Extract function/method signature for this language
--- @param lines table Buffer lines
--- @param start_line number Start line (0-indexed)
--- @param end_line number End line (0-indexed)
--- @return string Extracted signature
function M.extract_signature(lines, start_line, end_line)
  local signature_lines = {}
  local in_doc_comment = false
  local found_function = false
  local brace_count = 0

  for i = start_line + 1, end_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    -- Detect doc comments
    if line:match('^%s*//%s') or line:match('^%s*/%*%*') or line:match('^%s*#') then
      in_doc_comment = true
      table.insert(signature_lines, line)
    elseif in_doc_comment and (line:match('%*/') or not line:match('^%s*[/*#]')) then
      if line:match('%*/') then
        table.insert(signature_lines, line)
      end
      in_doc_comment = false
    elseif in_doc_comment then
      table.insert(signature_lines, line)
      -- Detect function/method declaration
    elseif line:match('function%s+') or line:match('def%s+') or
        line:match('fn%s+') or line:match('func%s+') or
        line:match('public%s+') or line:match('private%s+') or
        line:match('protected%s+') or line:match('static%s+') then
      found_function = true
      table.insert(signature_lines, line)

      -- Check for opening brace on same line
      for char in line:gmatch('.') do
        if char == '{' then
          brace_count = brace_count + 1
        elseif char == '}' then
          brace_count = brace_count - 1
        end
      end

      if brace_count > 0 or line:match('[{;]%s*$') then
        break
      end
    elseif found_function then
      table.insert(signature_lines, line)

      for char in line:gmatch('.') do
        if char == '{' then
          brace_count = brace_count + 1
        elseif char == '}' then
          brace_count = brace_count - 1
        end
      end

      if brace_count > 0 or line:match('[{;]%s*$') then
        break
      end
    end
  end

  return table.concat(signature_lines, '\n')
end

--- Extract class context including methods
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
  for i = class_start + 1, start_line + 1 do
    if i > #lines then break end
    local line = lines[i]

    if line:match('^%s*//%s') or line:match('^%s*/%*') or line:match('^%s*%*') or line:match('^%s*#') then
      table.insert(context_lines, line)
    elseif line:match('class%s+') or line:match('interface%s+') or line:match('trait%s+') then
      table.insert(context_lines, line)
      break
    end
  end

  table.insert(context_lines, '')

  -- Extract method signatures
  for i = start_line + 1, math.min(end_line + 1, #lines) do
    local line = lines[i]

    if line:match('function%s+') or line:match('def%s+') or
        line:match('public%s+function') or line:match('protected%s+function') or
        line:match('private%s+function') then
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

--- Should imports be included for this language?
--- @return boolean
function M.should_include_imports()
  return false
end

return M
