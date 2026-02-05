local inline = require('cmp_ai.inline')
local commands = require('cmp_ai.commands')

local M = {}

M.setup = function(opts)
  inline.setup(opts)
  commands.setup()
end

return M
