# task-builder

CLI for Jira ticket triage and codebase investigation.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini` on PATH)

## Install

```bash
uv tool install -e /path/to/task-builder
task-builder install
```

`task-builder install` creates `~/.config/task-builder/config.toml` from the example template. Edit it and replace all placeholder values before running other commands.

The `-e` flag is an editable install — `uv` does not copy your files. It creates a shim in `~/.local/bin/task-builder` that points back to the source directory. Changes to `.py` or prompt files take effect immediately. Rerun `uv tool install -e` only when you change `pyproject.toml` (new dependency, new entry point, or package rename).

## Config

`~/.config/task-builder/config.toml`:

```toml
[jira]
url = "https://your-org.atlassian.net"
user = "you@example.com"
token = "your-jira-token-here"

[llm]
command = "gemini"
model = "gemini-2.5-pro"
env = { GOOGLE_CLOUD_PROJECT = "your-gcp-project" }

[llm.analyze]
# Optional per-stage overrides. Example: use a cheaper model for triage.
# model = "gemini-2.5-flash"
```

Per-stage sections (`[llm.analyze]`, `[llm.investigate]`, `[llm.plan]`) are optional and inherit from `[llm]`. The `env` field is replaced, not merged, when overridden.

## Pipeline

The four stages run in order:

```
fetch → analyze → investigate → plan
```

Use `task-builder run JIRA-123` to run all four. Use the individual commands to run a single stage or to manually intervene between stages.

## Commands

### `fetch` — pull ticket data from Jira

```bash
task-builder fetch JIRA-123
```

- Fetches the ticket and its comments from Jira
- Downloads non-image/video attachments to `./JIRA-123/attachments/`
- Decompresses archives to `./JIRA-123/attachments/extracted/`
- Inlines text content from attachments (truncated to 50 KB per file)
- Writes `./JIRA-123/JIRA-123-raw.json`

No LLM call. Safe to re-run — overwrites the raw JSON.

### `analyze` — LLM triage of the raw ticket data

```bash
task-builder analyze JIRA-123 [--model MODEL]
```

- Reads `./JIRA-123/JIRA-123-raw.json` (run `fetch` first)
- Calls the LLM to produce a triage summary
- Writes `./JIRA-123/JIRA-123-parsed.md`

If `raw.json` is missing, the command errors with instructions to run `fetch` first.

### `investigate` — compare triage against the codebase

Run from inside a workspace folder containing the relevant repos.

```bash
task-builder investigate JIRA-123 [--model MODEL]
```

- Reads `./JIRA-123/JIRA-123-parsed.md` (run `analyze` first)
- Calls the LLM with file access to the current workspace
- Writes `./JIRA-123/JIRA-123-investigation.md`

### `plan` — decompose investigation into tasks

```bash
task-builder plan JIRA-123 [--model MODEL]
```

- Reads `./JIRA-123/JIRA-123-investigation.md` (run `investigate` first)
- Requires verdict `**Code bug**` in the investigation report
- Optionally reads `./JIRA-123/JIRA-123-approach.md` for a user-provided fix approach
- Writes `./JIRA-123/JIRA-123-plan.md` and `./JIRA-123/tasks/task-NNN.md`

### `run` — full pipeline

```bash
task-builder run JIRA-123 [--force] [--from STAGE] [--model MODEL]
```

Runs all four stages in order. Skips any stage whose output already exists.

```
[fetch]       done (./JIRA-123/JIRA-123-raw.json, 4 attachment(s))
[analyze]     done (./JIRA-123/JIRA-123-parsed.md)
[investigate] done (./JIRA-123/JIRA-123-investigation.md)
[plan]        done (./JIRA-123/JIRA-123-plan.md, 3 tasks)

Pipeline complete. Plan: ./JIRA-123/JIRA-123-plan.md
```

## Options

| Flag | Commands | Description |
|------|----------|-------------|
| `--model`, `-m` | `analyze`, `investigate`, `plan`, `run` | Override the LLM model for this run |
| `--force` | `run` | Re-run all stages, including fetch (re-hits Jira) |
| `--from STAGE` | `run` | Re-run starting at `fetch`, `analyze`, `investigate`, or `plan` |

`--force` and `--from` are mutually exclusive.

`--from analyze` reuses the existing `raw.json` without re-fetching. Useful after manually editing the raw data or when you want to re-run only the LLM stages.
