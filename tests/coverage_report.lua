-- Generate coverage report from luacov.stats.out
-- Prefers lcov format (for nvim-coverage), falls back to default text report
require('luacov.runner').load_config()

local ok, lcov = pcall(require, 'luacov.reporter.lcov')
if ok then
  lcov.report()
  print('lcov report: lcov.info')
else
  require('luacov.reporter.default').report()
  print('text report: luacov.report.out (install luacov-reporter-lcov for lcov format)')
end
