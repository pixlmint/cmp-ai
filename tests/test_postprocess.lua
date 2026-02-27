local h = require('tests.helpers')

local new_set = MiniTest.new_set

local child = MiniTest.new_child_neovim()

T = new_set({
  hooks = {
    pre_case = function()
      h.child_start(child)
      child.lua('_G.pp = require("cassandra_ai.suggest.postprocess")')
    end,
    post_case = child.stop,
  },
})

T['Postprocess'] = new_set()
T['Postprocess']['strip_markdown_fences'] = new_set()
T['Postprocess']['strip_context_overlap'] = new_set()
T['Postprocess']['postprocess_completions'] = new_set()

-- strip_markdown_fences tests

T['Postprocess']['strip_markdown_fences']['no fences returns original'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("local x = 1\\nreturn x")')
  h.eq(result, 'local x = 1\nreturn x')
end

T['Postprocess']['strip_markdown_fences']['single line returns original'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("```lua")')
  h.eq(result, '```lua')
end

T['Postprocess']['strip_markdown_fences']['strips fences with language specifier'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("```lua\\nlocal x = 1\\nreturn x\\n```")')
  h.eq(result, 'local x = 1\nreturn x')
end

T['Postprocess']['strip_markdown_fences']['strips fences without language'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("```\\nlocal x = 1\\n```")')
  h.eq(result, 'local x = 1')
end

T['Postprocess']['strip_markdown_fences']['strips only opening fence when closing missing'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("```python\\ndef foo():\\n  pass")')
  h.eq(result, 'def foo():\n  pass')
end

T['Postprocess']['strip_markdown_fences']['strips leading whitespace after fence removal'] = function()
  local result = child.lua_get('_G.pp.strip_markdown_fences("```lua\\n  indented_line\\nsecond_line\\n```")')
  h.eq(result, 'indented_line\nsecond_line')
end

-- strip_context_overlap tests

T['Postprocess']['strip_context_overlap']['empty text returns original'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("", "before", "after")')
  h.eq(result, '')
end

T['Postprocess']['strip_context_overlap']['no overlap returns original'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("unique line", "before context", "after context")')
  h.eq(result, 'unique line')
end

T['Postprocess']['strip_context_overlap']['strips leading overlap'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("local x = 1\\nlocal y = 2", "local x = 1", "")')
  h.eq(result, 'local y = 2')
end

T['Postprocess']['strip_context_overlap']['strips trailing overlap'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("local y = 2\\nreturn y", "", "return y")')
  h.eq(result, 'local y = 2')
end

T['Postprocess']['strip_context_overlap']['strips both leading and trailing overlap'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("local x = 1\\nlocal y = 2\\nreturn y", "local x = 1", "return y")')
  h.eq(result, 'local y = 2')
end

T['Postprocess']['strip_context_overlap']['all lines overlap returns original'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("local x = 1", "local x = 1", "")')
  h.eq(result, 'local x = 1')
end

T['Postprocess']['strip_context_overlap']['bridges over short trailing lines'] = function()
  -- Short closing tokens (}) after after-context matches get stripped together
  local result = child.lua_get('_G.pp.strip_context_overlap("new code\\nreturn x\\n}", "", "return x")')
  h.eq(result, 'new code')
end

T['Postprocess']['strip_context_overlap']['whitespace insensitive matching'] = function()
  local result = child.lua_get('_G.pp.strip_context_overlap("  local x = 1  \\nnew line", "local x = 1", "")')
  h.eq(result, 'new line')
end

-- postprocess_completions tests

T['Postprocess']['postprocess_completions']['applies both transforms'] = function()
  child.lua('_G._result = _G.pp.postprocess_completions({"```lua\\nlocal x = 1\\nlocal y = 2\\nreturn y\\n```"}, "local x = 1", "return y")')
  local result = child.lua_get('_G._result')
  h.eq(result, { 'local y = 2' })
end

T['Postprocess']['postprocess_completions']['processes multiple items'] = function()
  child.lua('_G._result = _G.pp.postprocess_completions({"first completion", "second completion"}, "", "")')
  local result = child.lua_get('_G._result')
  h.eq(result, { 'first completion', 'second completion' })
end

return T
