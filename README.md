# ▸ scripy

Generate small, single-file scripts using locally hosted (or cloud) LLMs. Ideal when presented with repetitive terminal tasks. 
Available in the command line when you need it.

```
scripy -p "rename all my jpegs by date taken"
```

scripy runs an agentic loop: generate, validate, self-correct, and write entirely locally via [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai).

---

## Install

Requires Python 3.11+ and a running Ollama or LM Studio instance.

```bash
pip install scripy-cli
```

Or for development:

```bash
pip install -e .
```

---

## Quick start

> **Note:** This assumes you're running Ollama on the same machine with `qwen2.5-coder:7b` installed. See [configuration](#configuration) below for more detailed configuration steps.

```bash
# Generate a Python script
scripy -p "find duplicate files in a directory"

# Specify output file
scripy -p "find duplicate files in a directory" -o dedup.py

# Generate Bash
scripy -p "backup my home directory to /tmp" --lang bash

# Modify an existing script
scripy -p "add a --dry-run flag" --input dedup.py

# Skip all confirmation prompts (for scripting)
scripy -p "..." -y
```

---

## Confirmation gates

scripy prompts for user input before any side-effectful action.

**Before writing to disk:**
```
  ? write to disk as dedup.py? [y/n/v] ›
```

**Before sandboxed execution:**
```
  ? run script to validate? [y/n/e/v/a] ›
```
| Key | Action |
|-----|--------|
| `y` | Yes |
| `n` | No |
| `e` | Open in `$EDITOR` to manually edit |
| `v` | Print script to terminal, then re-prompt |
| `a` | Always yes - skip gate for all remaining iterations |

Use `-y` / `--yes` to bypass all gates non-interactively.

---

## Configuration

Default config works with a local Ollama instance. Override via `~/.config/scripy/config.toml` (defaults shown below):

```toml
[model]
  provider    = "local" # OpenAI for cloud models
  base_url    = "http://192.168.1.10:11434/v1"  # remote Ollama
  model       = "llama3.1:8b"
  api_key     = "ollama" # use "lm-studio" for LM Studio or an OpenAI key for cloud models
  temperature = 0.2
  max_tokens  = 4096

[agent]
  force_tools      = true
  max_iterations   = 3
  default_lang     = "python"
  sandbox_timeout  = 10

[theme]
  code_theme       = "dracula"
```

CLI flags override config for a single run:

```bash
scripy --model qwen2.5-coder:7b -p "..."
```

---

## Local model recommendations

scripy targets models that run on small consumer hardware (~4–8GB RAM) but will obviously
excel on more powerful machines. That being said, here are some recommendations for
small machines.

| Model | Size | Tool calling | Code quality | Notes |
|-------|------|-------------|-------------|-------|
| `llama3.1:8b` | ~4.7GB | Native | Good | **Recommended default** |
| `llama3.2:3b` | ~2.0GB | Native | Fair | Best ultra-low-resource option |
| `qwen2.5-coder:7b` | ~4.4GB | Inline only | Excellent | Best code quality; see note below |
| `deepseek-coder:6.7b` | ~4.0GB | Inline only | Excellent | Same trade-off as qwen-coder |

### Tool calling

scripy uses the OpenAI function-calling API to let the model invoke tools
(`write_file`, `run_script`, `read_file`, `list_directory`). Models generally fall into
two categories:

**Native tool calling** (`llama3.1`, `llama3.2`) - the model returns structured
`tool_calls` in the API response. The agentic loop runs cleanly; `run_script`
validation and multi-turn self-correction work as intended.

**Inline tool calling** (`qwen2.5-coder`, `deepseek-coder`) - these models sometimes
ignore the tool-calling API and instead append a JSON blob to their text
response. scripy tries to detect and strip these automatically, but the behavior is
less reliable and the self-correction loop may not fire. You may see:

```
  ~ inline tool call detected - model is not using structured tool calling
```

`--force-tools` (`tool_choice=required`) is **on by default**. This works well
with native tool-calling models and is generally the right choice. If you see
errors or garbled output, which can happen with certain qwen-coder or
deepseek-coder models on older Ollama versions, disable it via config:

```toml
# ~/.config/scripy/config.toml
[agent]
  force_tools = false
```

With `force_tools` off, scripy falls back to inline tool-call detection automatically.
I've personally had better results using LM Studio for smaller models on small hardware
(think M2 mac mini 8GB RAM). Sometimes using Ollama the model kept appending tool calls
to the script output.

---

## CLI reference

```
Usage: scripy [OPTIONS]

  scripy - generate scripts with local LLMs.

Options:
  -p, --prompt TEXT   What script to generate.
  -o, --output TEXT   Output file path.
  -l, --lang TEXT     Language override (python, bash, etc.).
  --provider TEXT     "local" or "openai"
  --model TEXT        Model name override.
  --input TEXT        Existing script to modify.
  --tui               Launch Textual TUI.
  -y, --yes           Skip all confirmation gates.
  --force-tools       Override config and set tool_choice=required for this run.
  --version           Show version and exit.
  --help              Show this message and exit.
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
```
