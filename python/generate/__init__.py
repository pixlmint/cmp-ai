"""
fim_dataset_builder — Build a FIM (Fill-in-the-Middle) training dataset
from a PHP codebase for LoRA fine-tuning of code completion models.

APPROACH OVERVIEW
=================

The goal: teach a base code model (e.g. qwen2.5-coder) to produce idiomatic
completions for YOUR codebase — your frameworks, naming conventions, patterns.

There are three layers to this, in order of complexity and value:

  Layer 1: FILE-LEVEL FIM (this script)
    Split individual files into prefix/middle/suffix and train the model to
    reconstruct the middle.  This teaches syntax, patterns, and conventions.

  Layer 2: CROSS-FILE CONTEXT
    Prepend relevant context from other files (imports, class definitions,
    related interfaces) to the prefix.  This teaches framework usage patterns.
    Most of the quality gain for framework-specific completion comes from here.

  Layer 3: TEST-VALIDATED REJECTION SAMPLING (optional, advanced)
    Generate multiple completions with the fine-tuned model, run tests, keep
    only passing completions as training data for a second round.  This is
    essentially RLHF-lite for code.

This script implements Layers 1 and 2.

USAGE
=====
    # Basic: generate FIM dataset from a PHP project
    python -m generate /path/to/your/php/project \\
        --output dataset/ \\
        --base-model qwen2.5-coder

    # With cross-file context
    python -m generate /path/to/your/php/project \\
        --output dataset/ \\
        --cross-file-context \\
        --base-model qwen2.5-coder

    # Filter to only files that have corresponding tests
    python -m generate /path/to/your/php/project \\
        --output dataset/ \\
        --tested-only

    # Preview what would be generated (dry run)
    python -m generate /path/to/your/php/project --preview 5

TRAINING
========
    After generating the dataset, fine-tune with e.g. unsloth or axolotl:

    # unsloth (recommended for speed)
    # See: https://github.com/unslothai/unsloth

    # axolotl
    # See: https://github.com/OpenAccess-AI-Collective/axolotl

    The output JSONL is formatted for direct use with these tools.

Requirements:
    pip install tree-sitter tree-sitter-php  (for AST-aware splitting)
    # OR without tree-sitter: falls back to regex-based splitting
"""
