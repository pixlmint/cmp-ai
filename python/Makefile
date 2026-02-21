PYTHON = venv/bin/python

test:
	$(PYTHON) -m pytest tests/ -v

serve:
	$(PYTHON) -m fimcontextserver


self:
	$(PYTHON) -m generate \
		--output .dataset \
		--language python \
		--base-model qwen2.5-coder \
		--cross-file-context \
		--ast-fim \
		--bm25-context \
		.
