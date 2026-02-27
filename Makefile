all: format test

format:
	@echo Formatting...
	@stylua lua/ tests/ -f ./stylua.toml

test: deps
	@echo Testing...
	nvim --headless --noplugin -u ./tests/minimal_init.lua -c "lua MiniTest.run()"

test_file: deps
	@echo Testing File...
	nvim --headless --noplugin -u ./tests/minimal_init.lua -c "lua MiniTest.run_file('$(FILE)')"

LUACOV_LRPATH := $(shell lua -e "print(package.path)" 2>/dev/null || echo "/usr/share/lua/5.4/?.lua;/usr/share/lua/5.4/?/init.lua")
LUA_BIN := $(shell which lua5.4 lua 2>/dev/null | head -1)

coverage: deps
	@echo "Running tests with coverage..."
	@rm -f luacov.stats.out luacov.report.out lcov.info
	LUACOV=1 LUACOV_LRPATH="$(LUACOV_LRPATH)" \
		nvim --headless --noplugin -u ./tests/minimal_init.lua -c "lua MiniTest.run()"
	@echo "Generating coverage report..."
	@$(LUA_BIN) tests/coverage_report.lua

deps: tests/deps/plenary.nvim tests/deps/mini.nvim tests/deps/nvim-treesitter
	@echo Dependencies ready...

tests/deps/plenary.nvim:
	@mkdir -p tests/deps
	git clone --filter=blob:none https://github.com/nvim-lua/plenary.nvim.git $@

tests/deps/mini.nvim:
	@mkdir -p tests/deps
	git clone --filter=blob:none https://github.com/echasnovski/mini.nvim $@

tests/deps/nvim-treesitter:
	@mkdir -p tests/deps
	git clone --filter=blob:none https://github.com/nvim-treesitter/nvim-treesitter.git $@

