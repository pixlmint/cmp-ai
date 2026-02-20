local M = {}

--- Generate a UUID v4
function M.generate_uuid()
  local template = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'
  return string.gsub(template, '[xy]', function(c)
    local v = (c == 'x') and math.random(0, 0xf) or math.random(8, 0xb)
    return string.format('%x', v)
  end)
end

--- Safely serialize provider config for logging
--- Only logs provider.params (never api_key or headers)
--- Replaces functions with type metadata
function M.safe_serialize_config(params)
  if type(params) ~= 'table' then
    return params
  end

  local result = {}
  for key, value in pairs(params) do
    local value_type = type(value)
    if value_type == 'function' then
      result[key] = { __type = 'function' }
    elseif value_type == 'table' then
      result[key] = M.safe_serialize_config(value) -- Recursive
    elseif value_type == 'string' or value_type == 'number' or value_type == 'boolean' then
      result[key] = value
    else
      -- Thread, userdata, etc.
      result[key] = { __type = value_type }
    end
  end
  return result
end

return M
