# FIM Dataset Generator & Context Server

Generate Fill-in-the-Middle training data from PHP codebases for LoRA fine-tuning, and serve cross-file context to editor plugins over JSON-RPC.

## Setup

```bash
python -m venv venv
venv/bin/pip install tqdm tree-sitter tree-sitter-php rank-bm25
```

`tree-sitter` and `rank-bm25` are optional — the tool falls back to regex-based spans and skips BM25 retrieval if they're missing.

## Generating a Dataset

```bash
# Basic FIM dataset
venv/bin/python -m generate /path/to/php/project --output dataset/

# Preview examples without writing files
venv/bin/python -m generate /path/to/php/project --preview 5

# All features: cross-file context, BM25 retrieval, quality filtering
venv/bin/python -m generate /path/to/php/project \
    --output dataset/ \
    --cross-file-context \
    --bm25-context \
    --quality-filter

# Include extra directories for cross-file context (e.g. shared libraries)
venv/bin/python -m generate /path/to/php/project \
    --output dataset/ \
    --cross-file-context \
    --include-path /path/to/shared/lib \
    --include-path /path/to/another/lib
```

Output goes to the `--output` directory:
- `train.jsonl` / `val.jsonl` — training examples (90/10 split) with a `text` field formatted for the target model
- `metadata.json` — dataset statistics and configuration

### Options

| Flag | Default | Description |
|---|---|---|
| `--base-model` | `qwen2.5-coder` | Model family (`qwen2.5-coder`, `granite-code`, `codellama`, `starcoder`) — determines FIM special tokens |
| `--cross-file-context` | off | Prepend dependency signatures to the prefix |
| `--bm25-context` | off | Add BM25-retrieved code chunks as context |
| `--quality-filter` | off | Filter out repetitive, low-entropy, or comment-only examples |
| `--include-path DIR` | — | Extra directories to search for cross-file context (repeatable) |
| `--max-middle-lines` | 30 | Maximum lines in the middle (masked) section |
| `--max-total-chars` | 8192 | Maximum total characters per example |
| `--tested-only` | off | Only include files that have corresponding test files |
| `--curriculum` | off | Sort examples by complexity (descending) |
| `--preview N` | — | Print N random examples and exit without writing |

## Context Server

The context server provides cross-file context to editor plugins. It runs as a long-lived process communicating over stdin/stdout using JSON-RPC 2.0 (one JSON object per line).

```bash
venv/bin/python -m fimserver
```

### Protocol

**Initialize** — call once when opening a project:

```json
→ {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"project_root":"/path/to/project","include_paths":["/path/to/lib"],"bm25":true}}
← {"jsonrpc":"2.0","id":1,"result":{"file_count":142,"bm25_chunks":3500}}
```

Discovers PHP files, builds the BM25 index, and caches everything in memory. `include_paths` and `bm25` are optional.

**Get context** — call per completion request:

```json
→ {"jsonrpc":"2.0","id":2,"method":"getContext","params":{"filepath":"/path/to/src/Foo.php","content":"<?php\n...","cursor_offset":1234}}
← {"jsonrpc":"2.0","id":2,"result":{"context":"// --- Bar.php ---\nnamespace App\\Services;\n..."}}
```

Returns a context string containing dependency signatures and BM25 chunks. Pass the current buffer content in `content` (handles unsaved files). `cursor_offset` is used as the center of the BM25 query window — defaults to the middle of the file if omitted.

**Shutdown** — clean exit:

```json
→ {"jsonrpc":"2.0","id":3,"method":"shutdown"}
← {"jsonrpc":"2.0","id":3,"result":null}
```

### Error responses

```json
← {"jsonrpc":"2.0","id":2,"error":{"code":-1,"message":"not initialized"}}
```

### Plugin integration

Spawn the server as a subprocess and communicate over its stdin/stdout.

**Node.js:**

```javascript
const { spawn } = require("child_process");
const server = spawn("python", ["-m", "fimserver"], { cwd: "/path/to/fim-dataset-generator" });

function send(request) {
  server.stdin.write(JSON.stringify(request) + "\n");
}

let buffer = "";
server.stdout.on("data", (data) => {
  buffer += data.toString();
  const lines = buffer.split("\n");
  buffer = lines.pop();
  for (const line of lines) {
    if (line.trim()) console.log(JSON.parse(line));
  }
});

send({ jsonrpc: "2.0", id: 1, method: "initialize", params: { project_root: "/path/to/project", bm25: true } });
```

**Neovim (Lua):**

```lua
local server = nil
local request_id = 0

local function start_server()
  server = vim.system(
    { "python", "-m", "fimserver" },
    { cwd = "/path/to/fim-dataset-generator", stdin = true, stdout = function(_, data)
      if not data then return end
      for line in data:gmatch("[^\n]+") do
        local ok, response = pcall(vim.json.decode, line)
        if ok then
          vim.schedule(function()
            vim.print(response)
          end)
        end
      end
    end }
  )
end

local function send(method, params)
  request_id = request_id + 1
  local msg = vim.json.encode({ jsonrpc = "2.0", id = request_id, method = method, params = params })
  server:write(msg .. "\n")
  return request_id
end

-- Usage:
start_server()
send("initialize", { project_root = vim.fn.getcwd(), bm25 = true })

-- In a completion callback:
local bufnr = vim.api.nvim_get_current_buf()
local content = table.concat(vim.api.nvim_buf_get_lines(bufnr, 0, -1, false), "\n")
local pos = vim.api.nvim_win_get_cursor(0)  -- {1-indexed line, 0-indexed col}
local cursor = vim.fn.line2byte(pos[1]) + pos[2] - 1
-- alternative:
-- local cursor = vim.fn.line2byte(vim.fn.line(".")) + vim.fn.col(".") - 2
send("getContext", { filepath = vim.api.nvim_buf_get_name(bufnr), content = content, cursor_offset = cursor })
```
