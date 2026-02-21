# FIM Architecture Diagrams

Detailed Mermaid diagrams documenting the **FIM Context Server** (`fimcontextserver/`) and **Dataset Generator** (`generate/`), both built on the shared `fim/` library.

---

## Table of Contents

1. [Context Server State Diagram](#1-context-server-state-diagram)
2. [Dataset Generator State Diagram](#2-dataset-generator-state-diagram)
3. [Class Diagram](#3-class-diagram)
4. [Context Server Sequence Diagram](#4-context-server-sequence-diagram)
5. [Dataset Generation Pipeline](#5-dataset-generation-pipeline)
6. [Span Generator Flow](#6-span-generator-flow)
7. [Cross-File Context Flow](#7-cross-file-context-flow)
8. [Package Dependency Graph](#8-package-dependency-graph)

---

## 1. Context Server State Diagram

The FIM Context Server is a JSON-RPC 2.0 process that communicates over stdin/stdout. It transitions through three states based on incoming RPC methods.

```mermaid
stateDiagram-v2
    [*] --> Idle: Server.run() starts

    state Idle {
        [*] --> ReadingStdin
        ReadingStdin --> ReadingStdin: empty line (skip)
    }

    Idle --> Initialized: initialize request
    note right of Initialized
        ProjectState created:
        - source_files discovered
        - lang_config loaded
        - BM25 index built (optional)
    end note

    Initialized --> Initialized: getContext request
    note left of Initialized
        For each getContext:
        1. Build cross-file context
        2. Retrieve BM25 context (if index exists)
        3. Return combined context string
    end note

    Initialized --> Initialized: initialize request (re-init)

    Initialized --> Shutdown: shutdown request
    Idle --> Shutdown: shutdown request

    Shutdown --> [*]: Server.run() loop breaks

    state ErrorHandling {
        direction LR
        ParseError: JSON parse error (-32700)
        InvalidRequest: Missing method (-32600)
        MethodNotFound: Unknown method (-32601)
        InternalError: Handler exception (-32000)
    }

    note right of ErrorHandling
        Errors return JSON-RPC error response
        but do NOT change server state.
        Server continues reading stdin.
    end note
```

### Handler Internal State Transitions

```mermaid
stateDiagram-v2
    [*] --> Uninitialized: Handler.__init__()

    state Uninitialized {
        [*] --> WaitingForInit
        WaitingForInit: _state = None
        WaitingForInit: should_exit = False
    }

    state Initialized {
        [*] --> Ready
        Ready: _state = ProjectState(...)
        Ready: should_exit = False

        Ready --> ServingContext: getContext called
        ServingContext --> Ready: context returned

        state ServingContext {
            [*] --> BuildCrossFile
            BuildCrossFile --> BuildBM25: cross-file context built
            BuildBM25 --> CombineContext: BM25 context retrieved
            CombineContext --> [*]: return combined string
        }
    }

    Uninitialized --> Initialized: handle_initialize()
    Initialized --> Initialized: handle_initialize() (re-init)

    Uninitialized --> Terminated: handle_shutdown()
    Initialized --> Terminated: handle_shutdown()

    state Terminated {
        [*] --> Done
        Done: _state = None
        Done: should_exit = True
    }

    Terminated --> [*]
```

---

## 2. Dataset Generator State Diagram

The generator runs as a batch CLI process with sequential phases.

```mermaid
stateDiagram-v2
    [*] --> ParseArgs: python -m generate

    ParseArgs --> Discovery: args parsed, seed set
    note right of ParseArgs
        --language, --base-model,
        --cross-file-context, --bm25-context,
        --ast-fim, --quality-filter, --curriculum
    end note

    Discovery --> BM25Build: files discovered
    note right of Discovery
        find_files(root, lang_config)
        + include_path files → context_pool
    end note

    BM25Build --> Generation: index built (or skipped)

    state Generation {
        [*] --> NextFile
        NextFile --> ComputeComplexity: read source
        ComputeComplexity --> GenerateSpans: score assigned
        GenerateSpans --> CollectExamples: spans → FIMExamples
        CollectExamples --> NextFile: more files
        CollectExamples --> [*]: all files processed
    }

    Generation --> PostProcessing: all examples collected

    state PostProcessing {
        [*] --> QualityFilter
        QualityFilter --> CurriculumSort: filtered (if enabled)
        CurriculumSort --> [*]: sorted (if enabled)
    }

    PostProcessing --> PreviewCheck: post-processing done

    state PreviewDecision <<choice>>
    PreviewCheck --> PreviewDecision
    PreviewDecision --> Preview: --preview N
    PreviewDecision --> WriteOutput: no preview

    Preview --> [*]: display & exit

    WriteOutput --> [*]: train.jsonl + val.jsonl + metadata.json
    note right of WriteOutput
        Shuffle → 90/10 split
        (unless --curriculum)
    end note
```

---

## 3. Class Diagram

```mermaid
classDiagram
    direction TB

    class Server {
        -Handler _handler
        +run() void
        -_handle_line(line: str) dict|None
    }

    class Handler {
        -ProjectState|None _state
        +bool should_exit
        +handle_initialize(params: dict) dict
        +handle_get_context(params: dict) dict
        +handle_shutdown(params: dict) None
    }

    class ProjectState {
        +Path root
        +list~Path~ source_files
        +LanguageConfig lang_config
        +BM25Index|None bm25_index
        +dict sig_cache
    }

    class LanguageConfig {
        +str name
        +list~str~ extensions
        +str comment_prefix
        +set~str~ skip_dirs
        +list~str~ skip_patterns
        +Callable is_test_file
        +object|None ts_language
        +frozenset~str~ ast_eligible_types
        +set~str~ ast_bracket_types
        +set~str~ ast_ident_node_types
        +str ast_name_node_type
        +str regex_func_pattern
        +str regex_array_pattern
        +str regex_block_keywords
        +list~str~ trigger_tokens
        +Callable extract_imports
        +Callable extract_require_files
        +Callable extract_signature
        +Callable extract_referenced_symbols
    }

    class FIMConfig {
        +str prefix_tok
        +str suffix_tok
        +str middle_tok
        +str eot_tok
        +format_psm(prefix, middle, suffix) str
    }

    class CodeSpan {
        +str kind
        +int start_line
        +int end_line
        +str name
        +int indent
        +int start_byte
        +int end_byte
    }

    class FIMExample {
        +str filepath
        +str span_kind
        +str span_name
        +str prefix
        +str middle
        +str suffix
        +str cross_file_context
        +float complexity_score
        +int middle_lines
        +int total_lines
        +to_training_format(FIMConfig) dict
    }

    class BM25Index {
        +object bm25
        +list~str~ chunks
        +list~str~ chunk_files
    }

    %% Relationships
    Server "1" --> "1" Handler : owns
    Handler "1" --> "0..1" ProjectState : manages
    ProjectState "1" --> "1" LanguageConfig : uses
    ProjectState "1" --> "0..1" BM25Index : optional

    FIMExample ..> FIMConfig : formats with
    FIMExample ..> CodeSpan : created from

    %% Span generators
    class SpansAST {
        +extract_spans_ast(source, lang_config) list~CodeSpan~
        -_collect_eligible_nodes(node, types) list
        -_find_deepest_containing(node, start, end) Node
        -_aligned_span_from_random(src, tree, s, e) tuple
    }

    class SpansDevBehavior {
        +generate_incomplete_line_spans(source, tree, lc) list~CodeSpan~
        +generate_bracket_context_spans(source, tree, lc) list~CodeSpan~
        +generate_post_comment_spans(source, tree, lc) list~CodeSpan~
    }

    class SpansCharLevel {
        +generate_char_level_splits(source, num, min, max) list~CodeSpan~
    }

    class SpansRegex {
        +extract_spans_regex(source, lang_config) list~CodeSpan~
    }

    class FIMOrchestrator {
        +generate_fim_examples(filepath, source, ...) list~FIMExample~
        -_make_example_from_byte_span(...) FIMExample|None
        -_make_example_from_line_span(...) FIMExample|None
    }

    class Quality {
        +compute_complexity_score(source, lc) float
        +filter_low_quality_examples(examples) tuple
        +print_dataset_stats(examples, rejected) void
        -_char_entropy(text) float
    }

    class CLI {
        +main() void
        +build_argument_parser() ArgumentParser
        -discover_files(...) tuple
        -build_optional_bm25(...) BM25Index|None
        -generate_all_examples(...) tuple
        -apply_postprocessing(...) tuple
        -write_output(...) void
        -preview_examples(...) void
    }

    %% Generation relationships
    FIMOrchestrator ..> SpansAST : collects spans
    FIMOrchestrator ..> SpansDevBehavior : collects spans
    FIMOrchestrator ..> SpansCharLevel : collects spans
    FIMOrchestrator ..> SpansRegex : collects spans (fallback)
    FIMOrchestrator ..> CodeSpan : produces
    FIMOrchestrator ..> FIMExample : creates

    CLI --> FIMOrchestrator : calls per file
    CLI --> Quality : post-processing

    SpansAST ..> LanguageConfig : reads ast_eligible_types
    SpansDevBehavior ..> LanguageConfig : reads trigger_tokens, bracket_types
    SpansRegex ..> LanguageConfig : reads regex patterns

    %% Shared library functions
    class Discovery {
        +find_files(root, lang_config, tested_only) list~Path~
        +find_php_files(root, tested_only) list~Path~
    }

    class CrossFile {
        +build_cross_file_context(filepath, files, root, source, ...) str
        +find_related_files(filepath, files, root, source, lc) list~Path~
        +extract_file_signature(source, filepath, symbols, max_lines) str
        -_extract_referenced_symbols(source, lc) set~str~
    }

    class BM25Module {
        +build_bm25_index(files, root) BM25Index|None
        +retrieve_bm25_context(span, adj, index, path, ...) str
        -_tokenize_code(text) list~str~
    }

    Handler ..> Discovery : find_files()
    Handler ..> CrossFile : build_cross_file_context()
    Handler ..> BM25Module : build/retrieve
    FIMOrchestrator ..> CrossFile : build_cross_file_context()
    FIMOrchestrator ..> BM25Module : retrieve_bm25_context()
    CLI ..> Discovery : find_files()
    CLI ..> BM25Module : build_bm25_index()
```

---

## 4. Context Server Sequence Diagram

Shows the full lifecycle of a client session with the FIM Context Server.

```mermaid
sequenceDiagram
    participant Client as Client (Neovim)
    participant Server as Server (stdin/stdout)
    participant Handler
    participant Discovery as fim.discovery
    participant BM25 as fim.bm25
    participant CrossFile as fim.crossfile
    participant LangReg as fim.language

    Note over Client,LangReg: Phase 1: Initialization

    Client->>Server: {"method": "initialize", "params": {"project_root": "/app", "language": "php", "bm25": true}}
    Server->>Handler: handle_initialize(params)
    Handler->>LangReg: get_language("php")
    LangReg-->>Handler: LanguageConfig (PHP)
    Handler->>Discovery: find_files(root, lang_config)
    Discovery-->>Handler: [Path, Path, ...]
    Handler->>BM25: build_bm25_index(files, root)
    Note right of BM25: Chunk files on blank lines<br/>Tokenize chunks<br/>Build BM25Okapi
    BM25-->>Handler: BM25Index
    Handler-->>Handler: _state = ProjectState(...)
    Handler-->>Server: {"file_count": 487, "bm25_chunks": 3210}
    Server->>Client: {"jsonrpc": "2.0", "id": 1, "result": {...}}

    Note over Client,LangReg: Phase 2: Context Requests (repeated)

    Client->>Server: {"method": "getContext", "params": {"filepath": "src/Foo.php", "content": "<?php...", "cursor_offset": 420}}
    Server->>Handler: handle_get_context(params)

    Handler->>CrossFile: build_cross_file_context(filepath, files, root, content, lang_config)
    Note right of CrossFile: 1. Extract imports (use/require)<br/>2. Find related files (top 5)<br/>3. Extract signatures<br/>4. Filter to referenced symbols<br/>5. Budget: 4096 chars
    CrossFile-->>Handler: "// --- Bar.php ---\nclass Bar {...}\n..."

    Handler->>BM25: retrieve_bm25_context(cursor_window, "", index, path)
    Note right of BM25: Query = 1000 chars around cursor<br/>Score all chunks<br/>Deduplicate by file<br/>Top-5 from different files
    BM25-->>Handler: "// --- Baz.php ---\nfunction baz() {...}\n..."

    Handler-->>Server: {"context": "<combined cross-file + BM25>"}
    Server->>Client: {"jsonrpc": "2.0", "id": 2, "result": {"context": "..."}}

    Note over Client,LangReg: Phase 3: Shutdown

    Client->>Server: {"method": "shutdown", "params": {}}
    Server->>Handler: handle_shutdown(params)
    Handler-->>Handler: _state = None, should_exit = True
    Handler-->>Server: null
    Server->>Client: {"jsonrpc": "2.0", "id": 3, "result": null}
    Note over Server: run() loop breaks
```

---

## 5. Dataset Generation Pipeline

End-to-end flow of `python -m generate /path/to/project`.

```mermaid
flowchart TD
    CLI["CLI: python -m generate<br/>_cli.py::main()"] --> ParseArgs["Parse Arguments<br/>--language, --base-model,<br/>--cross-file-context, --bm25-context"]

    ParseArgs --> LoadConfig["Load FIM Config<br/>FIM_CONFIGS[base_model]<br/>e.g. Qwen2.5-Coder tokens"]

    LoadConfig --> Discover["Discover Files<br/>find_files(root, lang_config)<br/>+ include_path dirs"]

    Discover --> FileList["source_files: list[Path]<br/>context_pool: source + includes"]

    FileList --> BM25Check{--bm25-context?}
    BM25Check -->|Yes| BuildBM25["Build BM25 Index<br/>Chunk on blank lines (max 20)<br/>Tokenize → BM25Okapi"]
    BM25Check -->|No| SkipBM25["bm25_index = None"]

    BuildBM25 --> PerFile
    SkipBM25 --> PerFile

    subgraph PerFile["Per-File Processing Loop"]
        direction TB
        ReadFile["Read source file"] --> Complexity["Compute complexity score<br/>identifiers / bytes × 100"]
        Complexity --> GenFIM["generate_fim_examples()"]

        subgraph GenFIM_Detail["_fim.py Orchestration"]
            direction TB
            XFCtx["Build cross-file context<br/>(imports → related files → signatures)"]
            BM25Ctx["Retrieve BM25 context<br/>(cursor window query)"]
            ParseTree["Parse tree-sitter AST"]
            CollectSpans["Collect spans from generators"]
            ConvertExamples["Convert CodeSpan → FIMExample<br/>byte-span or line-span"]
        end

        GenFIM --> AssignScore["Assign complexity_score<br/>to each FIMExample"]
    end

    PerFile --> AllExamples["all_examples: list[FIMExample]"]

    AllExamples --> QualityCheck{--quality-filter?}
    QualityCheck -->|Yes| Filter["Filter Low Quality<br/>• Repetition (>50% dup lines)<br/>• Entropy (<2.0 bits)<br/>• Comment-only (>80%)<br/>• Length ratio (<3% or >80%)"]
    QualityCheck -->|No| SkipFilter[" "]

    Filter --> CurrCheck
    SkipFilter --> CurrCheck

    CurrCheck{--curriculum?}
    CurrCheck -->|Yes| Curriculum["Sort by complexity desc<br/>Trim to top N%"]
    CurrCheck -->|No| SkipCurr[" "]

    Curriculum --> Stats
    SkipCurr --> Stats

    Stats["Print Dataset Stats"] --> PreviewCheck{--preview N?}

    PreviewCheck -->|Yes| Preview["Display N examples<br/>formatted PSM"] --> Exit["Exit"]
    PreviewCheck -->|No| Split["Shuffle & Split<br/>90% train / 10% val"]

    Split --> WriteFiles["Write Output<br/>train.jsonl<br/>val.jsonl<br/>metadata.json"]
```

---

## 6. Span Generator Flow

How spans are collected and their approximate distribution.

```mermaid
flowchart TD
    Source["Source File (bytes)"] --> ASTCheck{tree-sitter<br/>available?}

    ASTCheck -->|Yes| ASTPath["AST Path"]
    ASTCheck -->|No| RegexPath["Regex Fallback Path"]

    subgraph ASTPath_Detail["AST + Dev-Behavior Generators"]
        direction TB

        AST["extract_spans_ast()<br/>~66% of spans"]
        AST --> SingleNode["ast_single_node (~33%)<br/>Weighted random AST node sampling<br/>Eligible types: function, method, class..."]
        AST --> AlignedSpan["ast_aligned_span (~33%)<br/>Random byte range → IoU-aligned<br/>to contiguous AST children"]

        DevBehavior["Dev-Behavior Generators<br/>~22% of spans"]
        DevBehavior --> IncompleteLine["dev_incomplete_line (~15%)<br/>Random intra-line cut OR<br/>syntax-aware trigger cut<br/>(=, (, ., ->, ::)"]
        DevBehavior --> BracketContent["dev_bracket_content (~5%)<br/>Inner content of brackets<br/>(arguments, arrays, params)"]
        DevBehavior --> PostComment["dev_post_comment (~3%)<br/>Statement following a comment<br/>(teach comment→code)"]
    end

    subgraph RegexPath_Detail["Regex Fallback"]
        direction TB
        Regex["extract_spans_regex()"]
        Regex --> FuncBody["function_body<br/>Regex match → brace-depth"]
        Regex --> Expression["expression<br/>Array/object initialization"]
        Regex --> Block["block<br/>if/for/while bodies"]
        Regex --> Lines["lines<br/>Random contiguous (2-8 lines)"]
    end

    CharLevel["generate_char_level_splits()<br/>~10% of spans<br/>Random byte offset + length<br/>(10-500 chars)"]

    ASTPath_Detail --> Merge["All CodeSpans"]
    RegexPath_Detail --> Merge
    CharLevel --> Merge
    Source --> CharLevel

    Merge --> ByteCheck{start_byte >= 0?}

    ByteCheck -->|Yes| ByteConvert["_make_example_from_byte_span()<br/>prefix = source[:start_byte]<br/>middle = source[start_byte:end_byte]<br/>suffix = source[end_byte:]"]

    ByteCheck -->|No| KindCheck{kind == char_random?}
    KindCheck -->|Yes| CharConvert["Reinterpret start_line/end_line<br/>as char offsets → byte span"]
    KindCheck -->|No| LineConvert["_make_example_from_line_span()<br/>prefix = lines[:start_line]<br/>middle = lines[start:end+1]<br/>suffix = lines[end+1:]"]

    CharConvert --> ByteConvert

    ByteConvert --> Validate
    LineConvert --> Validate

    Validate["Validate & Truncate<br/>• Non-empty middle<br/>• MIN_MIDDLE_WORDS check<br/>• Max total chars (8192)<br/>• Truncate prefix/suffix if needed"]

    Validate --> AppendCtx["Append cross-file + BM25 context"]
    AppendCtx --> FIMEx["FIMExample"]
```

---

## 7. Cross-File Context Flow

How cross-file context is built (shared by both server and generator).

```mermaid
flowchart TD
    Source["Target file source code"] --> ExtractImports["Extract imports<br/>lang_config.extract_imports()<br/>e.g. PHP: use App\\Models\\User"]

    Source --> ExtractRequires["Extract require/include<br/>lang_config.extract_require_files()<br/>e.g. require_once 'helpers.php'"]

    Source --> ExtractSymbols["Extract referenced symbols<br/>lang_config.extract_referenced_symbols()<br/>e.g. {User, Request, Response}"]

    ExtractImports --> MatchFiles["Match against all_files<br/>by filename stem"]
    ExtractRequires --> MatchFiles

    MatchFiles --> RelatedFiles["Top 5 related files"]

    RelatedFiles --> ForEachFile

    subgraph ForEachFile["For each related file"]
        direction TB
        ReadRelated["Read file content"]
        ReadRelated --> ExtractSig["Extract signature<br/>lang_config.extract_signature()<br/>Class/method/const declarations"]
        ExtractSig --> FilterSymbols["Filter to referenced symbols only<br/>(unless file is extended/implemented)"]
        FilterSymbols --> AddHeader["Prepend file header<br/>// --- path/to/File.php ---"]
    end

    ForEachFile --> Budget["Apply token budget<br/>1024 tokens ≈ 4096 chars<br/>Concatenate signatures"]

    ExtractSymbols --> FilterSymbols

    Budget --> DepContext["Dependency-based context string"]

    subgraph BM25Path["BM25 Retrieval (optional)"]
        direction TB
        CursorWindow["Extract cursor window<br/>±500 chars around cursor"]
        CursorWindow --> Tokenize["Tokenize query<br/>split → lowercase → filter"]
        Tokenize --> Score["Score all chunks<br/>BM25Okapi.get_scores()"]
        Score --> FilterChunks["Filter:<br/>• Exclude same-file<br/>• Exclude zero-score<br/>• Deduplicate by file"]
        FilterChunks --> TopK["Top-5 chunks<br/>from different files<br/>within 4096 char budget"]
    end

    DepContext --> Combine["Combine contexts"]
    TopK --> Combine

    Combine --> FinalContext["Final cross-file context string<br/>Prepended to FIMExample.cross_file_context"]
```

---

## 8. Package Dependency Graph

How the three packages relate and their external dependencies.

```mermaid
flowchart TB
    subgraph External["External Dependencies"]
        TS["tree-sitter<br/>(optional)"]
        TSLang["tree-sitter-php<br/>tree-sitter-python<br/>... (17 languages)"]
        RankBM25["rank-bm25<br/>(optional)"]
        TQDM["tqdm"]
    end

    subgraph FIM["fim/ (shared library)"]
        direction TB
        Types["types.py<br/>FIMConfig, CodeSpan,<br/>FIMExample, BM25Index"]
        Deps["deps.py<br/>HAS_TREE_SITTER,<br/>HAS_BM25"]
        Lang["language.py<br/>LanguageConfig,<br/>register(), get_language()"]
        Langs["languages/<br/>17 language modules<br/>_php, _python, _lua, ..."]
        Discovery["discovery.py<br/>find_files()"]
        CrossFile["crossfile.py<br/>build_cross_file_context()"]
        BM25Mod["bm25.py<br/>build_bm25_index(),<br/>retrieve_bm25_context()"]

        Langs --> Lang
        Discovery --> Lang
        CrossFile --> Lang
        BM25Mod --> Deps
        BM25Mod --> Types
    end

    subgraph Generate["generate/ (CLI dataset builder)"]
        direction TB
        GenCLI["_cli.py<br/>main(), argument parsing"]
        GenFIM["_fim.py<br/>generate_fim_examples()"]
        GenQuality["_quality.py<br/>filter, complexity, stats"]
        SpansAST["_spans_ast.py<br/>AST node/aligned spans"]
        SpansDB["_spans_devbehavior.py<br/>incomplete line, bracket, comment"]
        SpansChar["_spans_charlevel.py<br/>random char splits"]
        SpansRegex["_spans_regex.py<br/>regex fallback spans"]

        GenCLI --> GenFIM
        GenCLI --> GenQuality
        GenFIM --> SpansAST
        GenFIM --> SpansDB
        GenFIM --> SpansChar
        GenFIM --> SpansRegex
    end

    subgraph FIMServer["fimcontextserver/ (JSON-RPC server)"]
        direction TB
        Main["__main__.py<br/>CLI entry, logging setup"]
        Srv["_server.py<br/>Server: stdin/stdout loop"]
        Hdl["_handler.py<br/>Handler: dispatch + ProjectState"]

        Main --> Srv
        Srv --> Hdl
    end

    %% Cross-package dependencies
    GenFIM --> CrossFile
    GenFIM --> BM25Mod
    GenCLI --> Discovery
    GenCLI --> BM25Mod
    GenCLI --> Types
    SpansAST --> Lang
    SpansDB --> Lang
    SpansRegex --> Lang
    GenQuality --> Lang

    Hdl --> Discovery
    Hdl --> CrossFile
    Hdl --> BM25Mod
    Hdl --> Lang
    Hdl --> Deps
    Hdl --> Types

    %% External deps
    TS -.-> Deps
    TSLang -.-> Langs
    RankBM25 -.-> Deps
    TQDM -.-> GenCLI

    style External fill:#f5f5f5,stroke:#999
    style FIM fill:#e8f4f8,stroke:#4a9aba
    style Generate fill:#f0e8f4,stroke:#7a4aba
    style FIMServer fill:#e8f4e8,stroke:#4aba4a
```

---

## Span Type Summary

| Generator | Span Kind | Weight | Offset Type | Requires |
|-----------|-----------|--------|-------------|----------|
| `_spans_ast` | `ast_single_node` | ~33% | byte | tree-sitter |
| `_spans_ast` | `ast_aligned_span` | ~33% | byte | tree-sitter |
| `_spans_devbehavior` | `dev_incomplete_line` | ~15% | byte | tree-sitter (partial) |
| `_spans_devbehavior` | `dev_bracket_content` | ~5% | byte | tree-sitter |
| `_spans_devbehavior` | `dev_post_comment` | ~3% | byte | tree-sitter |
| `_spans_charlevel` | `char_random` | ~10% | char (in line fields) | none |
| `_spans_regex` | `function_body` | fallback | line | none |
| `_spans_regex` | `expression` | fallback | line | none |
| `_spans_regex` | `block` | fallback | line | none |
| `_spans_regex` | `lines` | fallback | line | none |

## Quality Filters

| Filter | Threshold | Catches |
|--------|-----------|---------|
| Repetition | >50% duplicate lines | Copy-paste, boilerplate |
| Entropy | <2.0 bits (Shannon) | Whitespace, repeated chars |
| Comment-only | >80% comment lines | Documentation blocks |
| Length ratio | <3% or >80% of total | Imbalanced examples |
