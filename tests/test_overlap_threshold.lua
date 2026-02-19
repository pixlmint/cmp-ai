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

T['compute_overlap_threshold'] = new_set()

-- Helper: call compute_overlap_threshold in the child process
local function threshold(text, overlap)
  return child.lua_get(string.format([[require('cassandra_ai.inline')._compute_overlap_threshold(%q, %q)]], text, overlap))
end

-- Words use vim's iskeyword, so "local " is 1 word,
-- "this.call(" has 4 words: this, ., call, (

-- "1+1": 1 vim-word + 1 char of next word
-- "local function_name" -> word1="local", next word starts at 7, +1 = 7
T['compute_overlap_threshold']['1+1 basic keyword words'] = function()
  h.eq(threshold('local function_name()', '1+1'), 7)
end

-- "1+1" with punctuation: "this.call()" -> words: this, ., call, (, )
-- 1 word = "this", next word = "." starts at 5, +1 char = 5
T['compute_overlap_threshold']['1+1 punctuation boundary'] = function()
  h.eq(threshold('this.call()', '1+1'), 5)
end

-- "3+1": 3 vim-words of "this.call(arg)"
-- words: this(1-4), .(5), call(6-9), ((10), arg(11-13), )(14)
-- 3 words = this . call, next word "(" starts at 10, +1 = 10
T['compute_overlap_threshold']['3+1 mixed keyword and punctuation'] = function()
  h.eq(threshold('this.call(arg)', '3+1'), 10)
end

-- "2+3": 2 words + 3 chars of next word
-- "local function my_func()" -> words: local, function, my_func, (, )
-- 2 words done, next = "my_func" starts at 16, +3 = 18
T['compute_overlap_threshold']['2+3 two words plus three chars'] = function()
  h.eq(threshold('local function my_func()', '2+3'), 18)
end

-- "1": 1 complete word including gap to next word
-- "local function_name()" -> word1="local", next word at 7, threshold=6
T['compute_overlap_threshold']['1 one complete word'] = function()
  h.eq(threshold('local function_name()', '1'), 6)
end

-- "1" with adjacent punctuation (no whitespace gap)
-- "this.call" -> word1="this", next word "." at 5, threshold=4
T['compute_overlap_threshold']['1 word with adjacent punctuation'] = function()
  h.eq(threshold('this.call', '1'), 4)
end

-- "+8": 8 total characters (no word requirement)
T['compute_overlap_threshold']['+8 total chars'] = function()
  h.eq(threshold('local function_name()', '+8'), 8)
end

-- "1+0.5": 1 word + 50% of next vim-word
-- "local function_name()" -> word1="local", next="function_name" (13 chars)
-- ceil(0.5 * 13) = 7, starts at 7, so 6 + 7 = 13
T['compute_overlap_threshold']['1+0.5 percentage of next word'] = function()
  h.eq(threshold('local function_name()', '1+0.5'), 13)
end

-- "2+1": 2 words + 1 char
-- "local function my_func()" -> 2 words = local, function; next="my_func" at 16, +1 = 16
T['compute_overlap_threshold']['2+1 two words plus one char'] = function()
  h.eq(threshold('local function my_func()', '2+1'), 16)
end

-- M exceeds next word length: cap at word length
-- "a b c" -> word1="a", next="b" (1 char), capped to 1; b starts at 3, result=3
T['compute_overlap_threshold']['chars exceeding word length caps at word length'] = function()
  h.eq(threshold('a b c', '1+100'), 3)
end

-- Not enough words: returns nil
T['compute_overlap_threshold']['not enough words returns nil'] = function()
  local result = child.lua_get([[require('cassandra_ai.inline')._compute_overlap_threshold('hello', '2+1')]])
  h.eq(result, vim.NIL)
end

-- Single word with "1" (no trailing content) returns nil
T['compute_overlap_threshold']['single word no boundary returns nil'] = function()
  local result = child.lua_get([[require('cassandra_ai.inline')._compute_overlap_threshold('hello', '1')]])
  h.eq(result, vim.NIL)
end

-- Percentage rounding: "1+0.5" with even-length next word
-- "ab cd" -> next word "cd" (2 chars), 50% = ceil(1) = 1, starts at 4, result=4
T['compute_overlap_threshold']['percentage rounds up'] = function()
  h.eq(threshold('ab cd', '1+0.5'), 4)
end

-- "1+0.5" with odd-length next word (3 chars)
-- "ab cde fg" -> next word "cde" (3 chars), 50% = ceil(1.5) = 2, starts at 4, result=5
T['compute_overlap_threshold']['percentage rounds up odd length'] = function()
  h.eq(threshold('ab cde fg', '1+0.5'), 5)
end

-- Default "1+1" matches old behavior for simple keyword words
-- "local x = 1" -> word1="local", next="x" at 7, +1=7
T['compute_overlap_threshold']['default 1+1 matches old space_pos + 1 behavior'] = function()
  h.eq(threshold('local x = 1', '1+1'), 7)
end

-- "+0" means 0 total chars (immediate show)
T['compute_overlap_threshold']['+0 returns zero'] = function()
  h.eq(threshold('anything', '+0'), 0)
end

-- Punctuation-only: "==" has 1 word (punctuation class)
-- "== true" -> word1="==", next="true" at 4, "1+1" = 4
T['compute_overlap_threshold']['punctuation as word'] = function()
  h.eq(threshold('== true', '1+1'), 4)
end

-- "5+1" on "this.call(arg)" -> 5 words: this . call ( arg, next=")" at 14, +1=14
T['compute_overlap_threshold']['5+1 many vim-words in dotted call'] = function()
  h.eq(threshold('this.call(arg)', '5+1'), 14)
end

return T
