local M = {}

--- Strip lines from the edges of a completion that overlap with surrounding context.
--- Some models echo back parts of the before/after text in their response.
function M.strip_context_overlap(text, lines_before, lines_after)
  local lines = vim.split(text, '\n', { plain = true })
  if #lines == 0 then
    return text
  end

  local before_split = vim.split(lines_before, '\n', { plain = true })
  local after_split = vim.split(lines_after, '\n', { plain = true })

  local before_set = {}
  for _, line in ipairs(before_split) do
    local trimmed = vim.trim(line)
    if trimmed ~= '' then
      before_set[trimmed] = true
    end
  end

  local after_set = {}
  for _, line in ipairs(after_split) do
    local trimmed = vim.trim(line)
    if trimmed ~= '' then
      after_set[trimmed] = true
    end
  end

  -- Strip leading lines that appear in before context
  local start_strip = 0
  for i = 1, #lines do
    local trimmed = vim.trim(lines[i])
    if trimmed ~= '' and before_set[trimmed] then
      start_strip = i
    else
      break
    end
  end

  -- Strip trailing lines that appear in after context.
  -- Allow short trailing lines (e.g. }, ), ]) that aren't in after_set
  -- to be bridged over, since the after context may have been truncated.
  local tail_skip = 0
  for i = #lines, start_strip + 1, -1 do
    local trimmed = vim.trim(lines[i])
    if trimmed == '' or after_set[trimmed] then
      break
    elseif #trimmed <= 2 then
      tail_skip = tail_skip + 1
      if tail_skip > 2 then
        tail_skip = 0
        break
      end
    else
      tail_skip = 0
      break
    end
  end

  local end_strip = 0
  for i = #lines - tail_skip, start_strip + 1, -1 do
    local trimmed = vim.trim(lines[i])
    if trimmed == '' or after_set[trimmed] then
      end_strip = end_strip + 1
    else
      break
    end
  end

  -- Only count tail_skip if we found actual after-context matches
  if end_strip > 0 then
    end_strip = end_strip + tail_skip
  end

  if start_strip == 0 and end_strip == 0 then
    return text
  end

  local result = {}
  for i = start_strip + 1, #lines - end_strip do
    result[#result + 1] = lines[i]
  end

  -- Don't strip everything - return original if nothing would remain
  if #result == 0 then
    return text
  end

  return table.concat(result, '\n')
end

--- Strip markdown code fences some providers wrap responses in.
function M.strip_markdown_fences(text)
  local lines = vim.split(text, '\n', { plain = true })
  if #lines < 2 then
    return text
  end
  if lines[1]:match('^```') then
    table.remove(lines, 1)
    if #lines > 0 then
      lines[1] = lines[1]:gsub('^%s+', '')
    end
  end
  if #lines > 0 and lines[#lines]:match('^```') then
    table.remove(lines, #lines)
  end
  return table.concat(lines, '\n')
end

--- Post-process completion candidates: strip fences and context overlap.
function M.postprocess_completions(data, lines_before, lines_after)
  for i, item in ipairs(data) do
    data[i] = M.strip_context_overlap(M.strip_markdown_fences(item), lines_before, lines_after)
  end
  return data
end

return M
