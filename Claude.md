# scripy — Claude Code Project Declaration

## Project Overview

**scripy** is a local-first CLI agent for generating small, single-file scripts (Python, Bash, etc.) using locally hosted LLMs via Ollama or LM Studio. Invoked with a single command and prompt, it runs an agentic loop that generates, validates, self-corrects, and writes the final script to disk.

---

## Goals

- Minimal hardware requirements — optimized for small coding models (e.g. qwen2.5-coder:7b, deepseek-coder:6.7b)
- Single-command UX: `scripy -p "build me a script to rename all my jpegs by date"`
- Self-correcting agentic loop (generate → run → observe → revise)
- Optional TUI via Textual for visual feedback
- No cloud dependencies — fully local inference

---

## Tech Stack

- **Language:** Python 3.11+
- **CLI:** `click`
- **Model client:** `openai` SDK (OpenAI-compatible API for both Ollama and LM Studio)
- **TUI:** `textual`
- **Output formatting:** `rich`
- **Packaging:** `pyproject.toml` with `pipx`-installable entry point

---

## Project Structure

```
scripy/
├── scripy/
│   ├── __init__.py
│   ├── cli.py          # Entry point, click CLI definition
│   ├── agent.py        # Agentic loop, multi-turn conversation logic
│   ├── tools.py        # Tool definitions: read_file, run_script, write_file, list_directory
│   ├── prompts.py      # System prompt and prompt templates
│   ├── executor.py     # Sandboxed script runner (subprocess), syntax validation
│   ├── config.py       # Config loading (model URL, defaults, etc.)
│   └── tui/
│       ├── __init__.py
│       └── app.py      # Optional Textual TUI app
├── tests/
├── pyproject.toml
├── README.md
└── CLAUDE.md           # This file
```

---

## CLI Interface

```bash
# Basic usage
scripy -p "write a python script to find duplicate files in a directory"

# Specify output file
scripy -p "..." -o dedup.py

# Specify language explicitly
scripy -p "..." --lang bash

# Specify model
scripy -p "..." --model qwen2.5-coder:7b

# Launch TUI
scripy -p "..." --tui

# Modify an existing script
scripy -p "add error handling" --input myscript.py
```

---

## Agentic Loop

The agent runs a bounded multi-turn conversation with the model:

1. **Generate** — model writes the script based on the user prompt
2. **Validate** — syntax check (e.g. `py_compile`, `bash -n`) and optional sandboxed execution
3. **Self-correct** — if validation fails, feed stderr back to model (max 3 iterations)
4. **Finalize** — write output to disk or stdout

Hard cap: **3 correction iterations** max to prevent infinite loops on bad models.

---

## Tool Definitions

Tools follow OpenAI function-calling schema. One tool call per turn (small model safe).

| Tool | Description |
|---|---|
| `write_file(path, content)` | Write the final script to disk |
| `run_script(code, interpreter)` | Execute script in sandbox, return stdout/stderr |
| `read_file(path)` | Read an existing file (for modification tasks) |
| `list_directory(path)` | List directory contents |

---

## System Prompt Contract

- Output **only** valid, runnable code — no markdown fences, no prose explanation
- Single-file scripts only; no multi-file output
- Always include a shebang and a brief comment header
- Infer language from the prompt; default to Python
- Scripts must be self-contained unless user explicitly requests external dependencies
- When using tools, call **one tool at a time**
- Only call `run_script` to validate; do not use it to simulate output

---

## Model Configuration

Default config (overridable via `~/.config/scripy/config.toml` or CLI flags):

```toml
[model]
base_url = "http://localhost:11434/v1"  # Ollama default
model = "qwen2.5-coder:7b"
api_key = "ollama"                       # LM Studio uses "lm-studio"
temperature = 0.2
max_tokens = 2048

[agent]
max_iterations = 3
default_lang = "python"
sandbox_timeout = 10  # seconds
```

Switching to LM Studio: change `base_url` to `http://localhost:1234/v1` and `api_key` to `"lm-studio"`.

---

## Constraints & Non-Goals

- **No multi-file output** — scripy targets single-file scripts only
- **No persistent memory** — each invocation is stateless
- **No cloud LLM calls** — local inference only by design
- **No package installation** — the generated script runs with what's available; scripy itself does not install deps on behalf of the user

---

## Recommended Models (Ollama)

| Model | Size | Notes |
|---|---|---|
| `qwen2.5-coder:7b` | ~4GB | Best overall for the size |
| `deepseek-coder:6.7b` | ~4GB | Strong on Python |
| `codellama:7b` | ~4GB | Good Bash/shell support |
| `qwen2.5-coder:1.5b` | ~1GB | Ultra-low resource fallback |

---

## Design Spec

scripy should feel like a premium, intentional tool — not a weekend hack. Every detail matters.

### Visual Identity

- **Theme:** Dark, high-contrast terminal aesthetic — true black background, not softened
- **Accent color:** Amber (`#F59E0B`) — used sparingly for brand moments and key highlights only
- **Secondary:** Muted slate for borders, dividers, and secondary text
- **Status colors:** Desaturated green/red for success/error — never neon
- **Wordmark:** Shown once on launch, then gone:
  ```
    ▸ scripy v0.1.0
  ```

### Glyph Language

Use a consistent set of prefix glyphs everywhere — headless and TUI:

| Glyph | Meaning |
|---|---|
| `▸` | In progress / working |
| `✓` | Success |
| `✗` | Failed |
| `~` | Warning / note |
| `?` | Awaiting user input |

Never mix in emoji or other unicode symbols.

### Headless (`rich`) Presentation

- **Spinner:** Custom sequence during inference — not the `rich` default dots. Use `▸ ▸▸ ▸▸▸` or similar
- **Script display:** Rendered in a `rich` syntax-highlighted panel with a subtle `box.MINIMAL` border; language label pinned to top-right corner of panel
- **Status lines:** Left-aligned, glyph-prefixed, single line per event — no multi-line prose
- **Completion line:** Always show elapsed time and file size:
  ```
  ✓ wrote dedup.py  892B  1.4s
  ```
- **Avoid `rich` defaults** — override panel borders, colors, and spinner to match the scripy palette

### TUI (`textual`) Layout

Single-screen, high information density — no wasted chrome:

```
┌─ scripy ──────────────────────────────────────────────────────┐
│  Log / conversation          │  Script preview (live)         │
│                              │                                │
│  ▸ generating...             │  #!/usr/bin/env python3        │
│  ✓ syntax valid              │  # dedup.py — find duplicate   │
│  ▸ running sandbox...        │  ...                           │
│                              │                                │
├──────────────────────────────┴────────────────────────────────┤
│  iteration 2/3   [y] run  [n] skip  [e] edit  [v] view  [a] always  │
└───────────────────────────────────────────────────────────────┘
```

- Left pane: agent log / conversation events
- Right pane: live syntax-highlighted script preview, updates on each iteration
- Footer: persistent keybind bar — shows only contextually relevant keys at each gate
- Iteration counter always visible when in correction loop
- Confirmation gates render as animated footer prompt, never a modal

### Diff View on Revision

When the model revises a script after a failed run, display a unified diff between iterations so the user can see exactly what changed — don't just silently replace the preview.

### `--version` Output

```
scripy 0.1.0
model  qwen2.5-coder:7b @ localhost:11434
```

Always show the currently configured model, not just the scripy version.

### Implementation Notes for Claude Code

- Use `rich.console`, `rich.panel`, `rich.syntax`, `rich.box` — customize everything, do not use defaults
- TUI built with `textual` — layout via `compose()`, footer via `Footer` widget with custom bindings
- All styling centralized in `scripy/theme.py` — single source of truth for colors, glyphs, box styles
- Headless and TUI share glyph/color constants from `theme.py`

---

## User Confirmation Gates

scripy prompts the user before any side-effectful action. Two distinct gates:

### 1. Run Gate (before `run_script`)

Displayed before sandboxed execution during the self-correction loop:

```
Run script to validate? [y/n/e/v/a] ›
```

| Key | Action |
|---|---|
| `y` | Run it |
| `n` | Skip execution; model continues without stdout/stderr feedback |
| `e` | Open script in `$EDITOR` before running |
| `v` | Print script to terminal, then re-prompt |
| `a` | Always yes — skip run gate for all remaining iterations this session |

The `a` option is important UX — the self-correction loop may call `run_script` up to 3 times, so users shouldn't have to confirm every iteration.

### 2. Write Gate (before `write_file`)

Displayed once when the agent is ready to finalize output:

```
Write to disk as dedup.py? [y/n] ›
```

| Key | Action |
|---|---|
| `y` | Write file |
| `n` | Abort write; print script to stdout instead |

### TUI Mode

In `--tui` mode, both gates render as a footer action bar with the same key bindings rather than stdin prompts. Core logic in `executor.py` must be gate-agnostic — the TUI and headless modes both call the same confirmation interface, just with different renderers.

### Non-interactive Mode

A `--yes` / `-y` flag bypasses all gates (equivalent to `a` on run, `y` on write). Intended for scripting scripy itself.

---

## Development Notes

- Keep tool execution sandboxed — use `subprocess` with `timeout`, never `exec()`
- Validate interpreter exists before invoking (`shutil.which`)
- TUI is fully optional — all core logic must work headlessly
- Prefer `rich.console` for non-TUI output so it degrades gracefully
