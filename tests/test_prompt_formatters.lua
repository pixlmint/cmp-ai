local h = require('tests.helpers')

local new_set = MiniTest.new_set

local child = MiniTest.new_child_neovim()

T = new_set({
  hooks = {
    pre_case = function()
      h.child_start(child)
    end,
    post_case = child.stop,
  },
})

T['PromptFormatters'] = new_set()

T['PromptFormatters']['chat() returns PromptData with mode chat'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("local x = ", "\\nreturn x", { filetype = "lua" })')

  h.eq(child.lua_get('_G._pd.mode'), 'chat')
  h.eq(child.lua_get('#_G._pd.messages'), 2)
  h.eq(child.lua_get('_G._pd.messages[1].role'), 'system')
  h.eq(child.lua_get('_G._pd.messages[2].role'), 'user')
end

T['PromptFormatters']['chat() includes filetype in system prompt'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("code", "more code", { filetype = "python" })')

  local system = child.lua_get('_G._pd.messages[1].content')
  h.contains(system, 'python')
end

T['PromptFormatters']['chat() includes additional_context in system prompt'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("code", "more code", { filetype = "lua" }, "function definitions here")')

  local system = child.lua_get('_G._pd.messages[1].content')
  h.contains(system, 'function definitions here')
end

T['PromptFormatters']['chat() user message has code prefix and suffix tags'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("before_cursor", "after_cursor", { filetype = "lua" })')

  local user_msg = child.lua_get('_G._pd.messages[2].content')
  h.contains(user_msg, '<code_prefix>before_cursor</code_prefix>')
  h.contains(user_msg, '<code_suffix>after_cursor</code_suffix>')
  h.contains(user_msg, '<code_middle>')
end

T['PromptFormatters']['fim() returns PromptData with mode fim'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").fim("prefix text", "suffix text")')

  h.eq(child.lua_get('_G._pd.mode'), 'fim')
  h.eq(child.lua_get('_G._pd.prefix'), 'prefix text')
  h.eq(child.lua_get('_G._pd.suffix'), 'suffix text')
end

T['PromptFormatters']['formatters table has chat and fim'] = function()
  child.lua('_G._pf = require("cassandra_ai.prompt_formatters")')

  h.eq(child.lua_get('type(_G._pf.formatters.chat)'), 'function')
  h.eq(child.lua_get('type(_G._pf.formatters.fim)'), 'function')
end

T['PromptFormatters']['deprecated general_ai alias returns a function'] = function()
  child.lua('_G._pf = require("cassandra_ai.prompt_formatters")')

  h.eq(child.lua_get('type(_G._pf.formatters.general_ai)'), 'function')
end

T['PromptFormatters']['deprecated aliases produce valid PromptData'] = function()
  child.lua('_G._fn = require("cassandra_ai.prompt_formatters").formatters.general_ai')
  child.lua('_G._pd = _G._fn("before", "after", { filetype = "lua" })')

  h.eq(child.lua_get('_G._pd.mode'), 'chat')
end

T['PromptFormatters']['chat() includes rejected completions as conversation history'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("before", "after", { filetype = "lua", rejected_completions = { "bad1", "bad2" } })')

  h.eq(child.lua_get('#_G._pd.messages'), 6)
  h.eq(child.lua_get('_G._pd.messages[3].role'), 'assistant')
  h.eq(child.lua_get('_G._pd.messages[3].content'), 'bad1')
  h.eq(child.lua_get('_G._pd.messages[4].role'), 'user')
  h.eq(child.lua_get('_G._pd.messages[5].role'), 'assistant')
  h.eq(child.lua_get('_G._pd.messages[5].content'), 'bad2')
  h.eq(child.lua_get('_G._pd.messages[6].role'), 'user')
end

T['PromptFormatters']['chat() with empty rejected_completions has only base messages'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").chat("before", "after", { filetype = "lua", rejected_completions = {} })')

  h.eq(child.lua_get('#_G._pd.messages'), 2)
end

T['PromptFormatters']['fim() prepends additional_context to prefix'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").fim("prefix text", "suffix text", {}, "extra context")')

  h.eq(child.lua_get('_G._pd.prefix'), 'extra context\nprefix text')
  h.eq(child.lua_get('_G._pd.suffix'), 'suffix text')
end

T['PromptFormatters']['fim() without additional_context uses prefix directly'] = function()
  child.lua('_G._pd = require("cassandra_ai.prompt_formatters").fim("prefix text", "suffix text")')

  h.eq(child.lua_get('_G._pd.prefix'), 'prefix text')
end

return T
