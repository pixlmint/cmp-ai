local M = {}

-- Helper function to check if file has any non-comment code
local function has_code(bufnr)
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  local parser = vim.treesitter.get_parser(bufnr)
  if not parser then
    -- Fallback: check for non-empty, non-whitespace lines
    for _, line in ipairs(lines) do
      if line:match('^%s*$') == nil then
        return true
      end
    end
    return false
  end

  local tree = parser:parse()[1]
  local root = tree:root()

  -- If there are any non-comment nodes, we have code
  for node in root:iter_children() do
    if node:type() ~= 'comment' then
      return true
    end
  end

  return false
end

-- Helper function to check if we're at a class/function declaration line
local function is_declaration_line(line, filetype)
  -- Remove leading/trailing whitespace for matching
  local trimmed = line:match('^%s*(.-)%s*$')

  -- Language-specific patterns for incomplete declarations
  local patterns = {
    python = {
      class_pattern = '^class%s+%w*',
      func_pattern = '^def%s+%w*',
    },
    lua = {
      class_pattern = nil, -- Lua doesn't have native classes
      func_pattern = '^function%s+%w*',
    },
    javascript = {
      class_pattern = '^class%s+%w*',
      func_pattern = '^function%s+%w*',
    },
    typescript = {
      class_pattern = '^class%s+%w*',
      func_pattern = '^function%s+%w*',
    },
    php = {
      class_pattern = '^class%s+%w*',
      -- PHP functions can have visibility modifiers (public/private/protected), static, etc.
      func_pattern = '^[%w%s]*function%s*%w*',
    },
    java = {
      class_pattern = '^class%s+%w*',
      func_pattern = '^%w+%s+%w+%s*%(', -- return_type function_name(
    },
  }

  local lang_patterns = patterns[filetype]
  if not lang_patterns then
    -- Generic patterns
    lang_patterns = {
      class_pattern = '^class%s+%w*',
      func_pattern = '^function%s+%w*',
    }
  end

  if lang_patterns.class_pattern and trimmed:match(lang_patterns.class_pattern) then
    return 'class'
  end

  if lang_patterns.func_pattern and trimmed:match(lang_patterns.func_pattern) then
    return 'func'
  end

  return nil
end

-- Helper function to check if a line is empty or whitespace-only
local function is_empty_line(line)
  return line:match('^%s*$') ~= nil
end

-- Detect the current suggestion context
function M.detect_suggestion_context(bufnr, pos)
  bufnr = bufnr or vim.api.nvim_get_current_buf()
  pos = pos or vim.api.nvim_win_get_cursor(0)

  local filetype = vim.bo[bufnr].filetype
  local current_line = vim.api.nvim_buf_get_lines(bufnr, pos[1] - 1, pos[1], false)[1] or ''

  -- Check if we have any code in the file
  if not has_code(bufnr) then
    return 'init'
  end

  -- Load treesitter textobjects if available
  local ok, textobjects = pcall(require, 'nvim-treesitter-textobjects.shared')
  if not ok then
    return nil
  end

  -- Check if we're in a comment
  local comment_match = textobjects.textobject_at_point('@comment.inner', 'textobjects')

  if comment_match and #comment_match >= 4 then
    -- We're in a comment, check if it's a class or function comment
    local comment_end_line = comment_match[4]
    local next_line_pos = { comment_end_line + 1, 0 }

    -- Check for class after comment
    local class_match = textobjects.textobject_at_point('@class.outer', 'textobjects', next_line_pos)
    if class_match and #class_match >= 4 then
      local class_start_line = class_match[1]
      if class_start_line == comment_end_line + 1 then
        return 'comment_class'
      end
    end

    -- Check for function after comment
    local func_match = textobjects.textobject_at_point('@function.outer', 'textobjects', next_line_pos)
    if func_match and #func_match >= 4 then
      local func_start_line = func_match[1]
      if func_start_line == comment_end_line + 1 then
        return 'comment_func'
      end
    end

    -- Generic comment (not a doc comment)
    return 'impl'
  end

  -- Check if we're writing a class or function declaration
  local decl_type = is_declaration_line(current_line, filetype)
  if decl_type then
    return decl_type
  end

  -- Check if we're in a function body
  local func_match = textobjects.textobject_at_point('@function.inner', 'textobjects')

  if func_match and #func_match >= 4 then
    -- We matched a function.inner, but we need to verify this isn't a false positive
    -- where we're declaring a new function above an existing one
    local func_start_line = func_match[1]
    local func_end_line = func_match[4]
    local current_pos_line = pos[1] - 1 -- Convert to 0-indexed

    -- Edge case: Check if we're actually declaring a new function above an existing one
    -- by verifying if there's no function body content between cursor and the matched function
    if current_pos_line < func_start_line then
      -- Cursor is before the function start, we're definitely not in it
      return 'impl'
    end

    -- Get the line at the function start to check if it's where we are
    local func_start_line_content = vim.api.nvim_buf_get_lines(bufnr, func_start_line, func_start_line + 1, false)[1] or
    ''

    -- If we're on a line that looks like a function declaration and it's not the actual
    -- matched function's declaration line, we're declaring a new function
    if is_declaration_line(current_line, filetype) then
      -- Check if current line is different from the matched function's start
      if current_pos_line ~= func_start_line then
        -- We're on a declaration line that's not the matched function's start
        -- This means we're declaring a new function above an existing one
        return 'func'
      end
    end

    -- If cursor is at or very close to the function start and the line is a declaration,
    -- check if there's actual function body content below
    if current_pos_line <= func_start_line + 2 and is_declaration_line(current_line, filetype) then
      -- Check if the next few lines are empty (no body yet)
      local lines_below = vim.api.nvim_buf_get_lines(bufnr, current_pos_line + 1,
        math.min(current_pos_line + 3, func_end_line), false)
      local has_body_content = false
      for _, line in ipairs(lines_below) do
        if not is_empty_line(line) then
          has_body_content = true
          break
        end
      end

      if not has_body_content then
        return 'func'
      end
    end

    return 'impl'
  end

  -- Default to implementation context
  return 'impl'
end

-- LSP function discovery
-- Copied from https://github.com/oribarilan/lensline.nvim/blob/main/lua/lensline/lens_explorer.lua on 2026-01-31
local function_cache = {}
local buffer_changedtick = {}
local cache_access_order = {} -- Track access order for LRU eviction
local MAX_CACHE_SIZE = 50     -- Limit cache to 50 buffers maximum


-- LRU cache management functions
local function update_access_order(bufnr)
  -- Remove bufnr from current position if it exists
  for i, cached_bufnr in ipairs(cache_access_order) do
    if cached_bufnr == bufnr then
      table.remove(cache_access_order, i)
      break
    end
  end
  -- Add to end (most recently used)
  table.insert(cache_access_order, bufnr)
end

local function evict_lru_if_needed()
  while #cache_access_order > MAX_CACHE_SIZE do
    local lru_bufnr = table.remove(cache_access_order, 1) -- Remove least recently used
    function_cache[lru_bufnr] = nil
    buffer_changedtick[lru_bufnr] = nil
  end
end

-- Recursively extract function/method symbols from LSP response
-- Helper function to identify legitimately named functions (not anonymous)
local function is_named_function(symbol)
  -- Only check Functions, not Methods or Constructors
  if symbol.kind ~= vim.lsp.protocol.SymbolKind.Function then
    return false
  end

  -- Must have a name
  if not symbol.name then
    return false
  end

  -- Name must not be empty/whitespace
  if not symbol.name:match("%S") then
    return false
  end

  -- Skip generic names that indicate anonymous functions
  local lower_name = symbol.name:lower()
  if lower_name == "function" or
      lower_name == "lambda" or
      lower_name == "anonymous" or
      symbol.name:match("^function%(") or -- Lua-style "function(" pattern
      symbol.name:match("^vim%.") or      -- Skip Neovim API wrappers
      symbol.name:match("^%[%d+%]$") then -- LSP array-style anonymous functions "[1]", "[2]", required for lua_ls
    return false
  end

  return true
end

-- Helper to get lsp clients (works with newer and older nvim versions)
function M.get_lsp_clients(bufnr)
  if vim.lsp.get_clients then
    return vim.lsp.get_clients({ bufnr = bufnr })
  else
    return vim.lsp.get_active_clients({ bufnr = bufnr })
  end
end

-- Check if any LSP client supports a specific method for the buffer
function M.has_lsp_capability(bufnr, method)
  local clients = M.get_lsp_clients(bufnr)
  if not clients or #clients == 0 then
    return false
  end

  for _, client in ipairs(clients) do
    -- Check if client supports the method
    if client.server_capabilities then
      -- Only check the methods we actually use in this plugin
      -- Note: lens_explorer.lua only handles core capabilities for function discovery.
      -- Additional LSP capabilities (textDocument/definition, textDocument/implementation)
      -- are handled in utils.lua for provider-specific features like the usages provider.
      local capability_map = {
        ["textDocument/references"] = "referencesProvider",
        ["textDocument/documentSymbol"] = "documentSymbolProvider",
      }

      local capability_key = capability_map[method]
      if capability_key and client.server_capabilities[capability_key] then
        return true
      end
    end
  end

  return false
end

function M.extract_symbols_recursive(symbols, functions, start_line, end_line)
  for _, symbol in ipairs(symbols) do
    -- Identify symbol kinds we care about (function / method / constructor)
    local symbol_kinds = {
      [vim.lsp.protocol.SymbolKind.Function] = true,
      [vim.lsp.protocol.SymbolKind.Method] = true,
      [vim.lsp.protocol.SymbolKind.Constructor] = true,
    }

    if symbol_kinds[symbol.kind] then
      local include = true
      -- Only add plain Functions if they are "named" per our heuristic
      if symbol.kind == vim.lsp.protocol.SymbolKind.Function and not is_named_function(symbol) then
        include = false -- (previously used Lua 5.2 goto to "continue"; rewritten for 5.1 portability)
      end

      if include then
        local line_num
        local end_line_num
        local character

        -- Handle both DocumentSymbol and SymbolInformation formats
        if symbol.range then
          -- DocumentSymbol format
          line_num = symbol.range.start.line + 1      -- Convert to 1-indexed
          end_line_num = symbol.range["end"].line + 1 -- Convert to 1-indexed
          character = symbol.range.start.character
        elseif symbol.location then
          -- SymbolInformation format
          line_num = symbol.location.range.start.line + 1
          end_line_num = symbol.location.range["end"].line + 1
          character = symbol.location.range.start.character
        end

        if line_num and line_num >= start_line and line_num <= end_line then
          table.insert(functions, {
            line = line_num,
            end_line = end_line_num,
            character = character,
            name = symbol.name,
            kind = symbol.kind
          })
        end
      end
    end
    -- Recursively process children if they exist
    if symbol.children then
      M.extract_symbols_recursive(symbol.children, functions, start_line, end_line)
    end
  end
end

-- Use LSP document symbols to find functions (async version - eliminates UI hang)
function M.find_functions_via_lsp_async(bufnr, start_line, end_line, callback)
  local clients = M.get_lsp_clients(bufnr)
  if not clients or #clients == 0 then
    callback({})
    return
  end

  -- Check if any LSP client supports document symbols
  if not M.has_lsp_capability(bufnr, "textDocument/documentSymbol") then
    callback({})
    return
  end

  -- Check cache validity using buffer's changedtick
  local current_changedtick = vim.api.nvim_buf_get_changedtick(bufnr)
  local cache_key = bufnr

  if function_cache[cache_key] and buffer_changedtick[cache_key] == current_changedtick then
    -- Cache hit - update LRU order and filter functions for requested range
    update_access_order(cache_key)
    local cached_functions = function_cache[cache_key]
    local filtered_functions = {}
    for _, func in ipairs(cached_functions) do
      if func.line >= start_line and func.line <= end_line then
        table.insert(filtered_functions, func)
      end
    end
    callback(filtered_functions)
    return
  end

  local params = {
    textDocument = vim.lsp.util.make_text_document_params(bufnr)
  }

  -- Add timing logs around the async LSP call
  -- local start_time = vim.loop.hrtime()

  vim.lsp.buf_request(bufnr, "textDocument/documentSymbol", params, function(err, results)
    -- local end_time = vim.loop.hrtime()
    -- local duration_ms = (end_time - start_time) / 1000000 -- Convert to milliseconds

    if err or not results then
      callback({})
      return
    end

    local functions = {}

    -- Process async results - different format than sync version
    -- In async callback, 'results' is the direct LSP response, not wrapped in client responses
    if results and type(results) == "table" then
      M.extract_symbols_recursive(results, functions, 1, math.huge)
    end

    -- Cache the complete function list for this buffer with LRU management
    -- NOTE: Race condition possible here - if rapid saves occur, an older
    -- request might overwrite newer cache data. This causes temporary stale
    -- lenses until next edit. Can add changedtick validation if needed:
    -- if vim.api.nvim_buf_get_changedtick(bufnr) == current_changedtick then
    function_cache[cache_key] = functions
    buffer_changedtick[cache_key] = current_changedtick
    update_access_order(cache_key)
    evict_lru_if_needed()

    -- Return filtered results for the requested range
    local filtered_functions = {}
    for _, func in ipairs(functions) do
      if func.line >= start_line and func.line <= end_line then
        table.insert(filtered_functions, func)
      end
    end

    callback(filtered_functions)
  end)
end

return M
