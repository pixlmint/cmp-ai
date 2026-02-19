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

-- "1+1": 1 word + 1 char of next word
-- "local function_name" -> after "local " (6 chars) + 1 char = 7
T['compute_overlap_threshold']['1+1 basic'] = function()
  h.eq(threshold('local function_name()', '1+1'), 7)
end

-- "2+3": 2 words + 3 chars of next word
-- "local function my_func()" -> after "local function " (15 chars) + 3 = 18
T['compute_overlap_threshold']['2+3 two words plus three chars'] = function()
  h.eq(threshold('local function my_func()', '2+3'), 18)
end

-- "1": 1 complete word including trailing space
-- "local function_name" -> "local " = 6, but we return position before next word = 6
T['compute_overlap_threshold']['1 one complete word'] = function()
  -- After "local " the next non-ws is at position 7, so threshold = 6
  h.eq(threshold('local function_name()', '1'), 6)
end

-- "+8": 8 total characters (no word requirement)
T['compute_overlap_threshold']['+8 total chars'] = function()
  h.eq(threshold('local function_name()', '+8'), 8)
end

-- "1+0.5": 1 word + 50% of next word
-- next word is "function_name()" (15 chars, no more whitespace), 50% = ceil(7.5) = 8
-- after "local " (6 chars) + 8 = 14
T['compute_overlap_threshold']['1+0.5 percentage of next word'] = function()
  h.eq(threshold('local function_name()', '1+0.5'), 14)
end

-- "2+1": 2 words + 1 char
-- "local function my_func()" -> after "local function " (15) + 1 = 16
T['compute_overlap_threshold']['2+1 two words plus one char'] = function()
  h.eq(threshold('local function my_func()', '2+1'), 16)
end

-- M exceeds next word length: cap at word length
-- "1+100": next word "b" has 1 char, capped to 1
-- "a b c" -> after "a " (pos 3) + 1 = 3
T['compute_overlap_threshold']['chars exceeding word length caps at word length'] = function()
  h.eq(threshold('a b c', '1+100'), 3)
end

-- Not enough words: returns nil
T['compute_overlap_threshold']['not enough words returns nil'] = function()
  local result = child.lua_get([[require('cassandra_ai.inline')._compute_overlap_threshold('hello', '2+1')]])
  h.eq(result, vim.NIL)
end

-- Single word with "1" (no trailing space) returns nil
T['compute_overlap_threshold']['single word no space with word requirement returns nil'] = function()
  local result = child.lua_get([[require('cassandra_ai.inline')._compute_overlap_threshold('hello', '1')]])
  h.eq(result, vim.NIL)
end

-- Percentage rounding: "1+0.5" with even-length next word
-- "ab cd" -> next word "cd" (2 chars), 50% = ceil(1) = 1
-- after "ab " (3) + 1 = 4
T['compute_overlap_threshold']['percentage rounds up'] = function()
  h.eq(threshold('ab cd', '1+0.5'), 4)
end

-- "1+0.5" with odd-length next word (3 chars)
-- "ab cde fg" -> next word "cde" (3 chars), 50% = ceil(1.5) = 2
-- after "ab " (3) + 2 = 5
T['compute_overlap_threshold']['percentage rounds up odd length'] = function()
  h.eq(threshold('ab cde fg', '1+0.5'), 5)
end

-- Default "1+1" matches old behavior (space_pos + 1)
-- Old code: first whitespace at pos 6 in "local x" + 1 = 7
-- New code: after "local " = pos 6, then +1 char of "x" = 7
T['compute_overlap_threshold']['default 1+1 matches old space_pos + 1 behavior'] = function()
  h.eq(threshold('local x = 1', '1+1'), 7)
end

-- "+0" means 0 total chars (immediate show)
T['compute_overlap_threshold']['+0 returns zero'] = function()
  h.eq(threshold('anything', '+0'), 0)
end

return T
