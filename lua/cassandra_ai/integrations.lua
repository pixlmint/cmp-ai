local conf = require('cassandra_ai.config')
local logger = require('cassandra_ai.logger')

local M = {}

local close_fns = {}
local visible_fns = {}
local trigger_fns = {}

local function is_enabled()
  local ic = conf:get('inline')
  return ic.cmp_integration ~= false
end

function M.setup()
  if not is_enabled() then
    logger.trace('integrations: cmp_integration disabled, skipping')
    return
  end

  vim.schedule(function()
    -- Detect nvim-cmp
    local has_cmp, cmp = pcall(require, 'cmp')
    if has_cmp then
      logger.debug('integrations: nvim-cmp detected')
      close_fns.cmp = function()
        pcall(function()
          if cmp.visible() then
            cmp.abort()
          end
        end)
      end
      visible_fns.cmp = function()
        local ok, vis = pcall(cmp.visible)
        return ok and vis
      end
      trigger_fns.cmp = function()
        pcall(cmp.complete)
      end
      -- When cmp menu opens, dismiss ghost text
      pcall(function()
        cmp.event:on('menu_opened', function()
          if is_enabled() then
            local inline = require('cassandra_ai.inline')
            if inline.is_visible() then
              logger.trace('integrations: cmp menu opened, dismissing ghost text')
              inline.dismiss()
            end
          end
        end)
      end)
    end

    -- Detect blink.cmp
    local has_blink, blink = pcall(require, 'blink.cmp')
    if has_blink then
      logger.debug('integrations: blink.cmp detected')
      close_fns.blink = function()
        pcall(function()
          if blink.is_visible and blink.is_visible() then
            blink.hide()
          end
        end)
      end
      visible_fns.blink = function()
        local ok, vis = pcall(function()
          return blink.is_visible and blink.is_visible()
        end)
        return ok and vis
      end
      trigger_fns.blink = function()
        pcall(blink.show)
      end
      -- When blink menu opens, dismiss ghost text
      pcall(function()
        vim.api.nvim_create_autocmd('User', {
          pattern = 'BlinkCmpCompletionMenuOpen',
          group = vim.api.nvim_create_augroup('cassandra_ai_blink', { clear = true }),
          callback = function()
            if is_enabled() then
              local inline = require('cassandra_ai.inline')
              if inline.is_visible() then
                logger.trace('integrations: blink menu opened, dismissing ghost text')
                inline.dismiss()
              end
            end
          end,
        })
      end)
    end

    if not has_cmp and not has_blink then
      logger.trace('integrations: no custom completion plugins detected, using native pum hooks')
    end

    -- Hook native pum (covers coq_nvim, mini.completion, compl.nvim, etc.)
    close_fns.pum = function()
      if vim.fn.pumvisible() == 1 then
        vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<C-e>', true, false, true), 'n', false)
      end
    end

    vim.api.nvim_create_autocmd('CompleteChanged', {
      group = vim.api.nvim_create_augroup('cassandra_ai_pum', { clear = true }),
      callback = function()
        if is_enabled() and vim.fn.pumvisible() == 1 then
          local inline = require('cassandra_ai.inline')
          if inline.is_visible() then
            logger.trace('integrations: native pum opened, dismissing ghost text')
            inline.dismiss()
          end
        end
      end,
    })
  end)
end

function M.trigger_completion_menu()
  if not is_enabled() then
    return
  end
  for _, fn in pairs(trigger_fns) do
    pcall(fn)
    return
  end
  -- Fallback: trigger native insert-mode completion
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes('<C-x><C-o>', true, false, true), 'n', false)
end

function M.close_completion_menus()
  if not is_enabled() then
    return
  end
  for _, fn in pairs(close_fns) do
    pcall(fn)
  end
end

function M.is_completion_menu_visible()
  if not is_enabled() then
    return false
  end
  for _, fn in pairs(visible_fns) do
    local ok, vis = pcall(fn)
    if ok and vis then
      return true
    end
  end
  return vim.fn.pumvisible() == 1
end

return M
