import json
import sys
from pathlib import Path
import shutil
from typing import Optional, Tuple

from .config import Config, get_llm_config
from .llm import call_llm

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def plan_ticket(ticket_id: str, config: Config, model_override: Optional[str] = None) -> Tuple[Path, int]:
    llm_cfg = get_llm_config(config, "plan", model_override)

    ticket_dir = Path(ticket_id)
    investigation_path = ticket_dir / f"{ticket_id}-investigation.md"
    approach_path = ticket_dir / f"{ticket_id}-approach.md"
    plan_out_path = ticket_dir / f"{ticket_id}-plan.md"
    tasks_dir = ticket_dir / "tasks"

    if not investigation_path.exists():
        print(
            f"Error: Investigation report not found: {investigation_path}\n"
            f"Run `task-builder investigate {ticket_id}` first.",
            file=sys.stderr,
        )
        sys.exit(1)

    investigation_content = investigation_path.read_text(encoding="utf-8")

    if "**Code bug**" not in investigation_content:
        print(
            "Error: Investigation verdict is not '**Code bug**'. Planning aborted.",
            file=sys.stderr,
        )
        sys.exit(1)

    approach_content = ""
    if approach_path.exists():
        print(f"==> Using user-provided approach from {approach_path}", file=sys.stderr)
        approach_content = approach_path.read_text(encoding="utf-8")
    else:
        print("==> No approach override found. Planner will derive fix from investigation.", file=sys.stderr)

    # --- Build prompt ---
    print("==> Building prompt ...", file=sys.stderr)
    system_prompt = (_PROMPTS_DIR / "plan.md").read_text(encoding="utf-8")

    full_prompt = system_prompt.replace("{{INVESTIGATION}}", investigation_content)
    full_prompt = full_prompt.replace("{{APPROACH}}", approach_content if approach_content else "None provided.")

    # --- Call LLM ---
    print(f"==> Calling {llm_cfg.command} ({llm_cfg.model}) ...", file=sys.stderr)
    response = call_llm(full_prompt, llm_cfg)

    if not response.strip():
        print(f"Error: {llm_cfg.command} returned an empty response.", file=sys.stderr)
        sys.exit(1)

    # --- Parse JSON ---
    raw_json = response.strip()
    if raw_json.startswith("```json"):
        raw_json = raw_json.removeprefix("```json")
    if raw_json.startswith("```"):
        raw_json = raw_json.removeprefix("```")
    if raw_json.endswith("```"):
        raw_json = raw_json.removesuffix("```")
    raw_json = raw_json.strip()

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON response: {e}", file=sys.stderr)
        print("Raw response:", file=sys.stderr)
        print(response, file=sys.stderr)
        sys.exit(1)

    plan_markdown = data.get("plan_markdown")
    tasks = data.get("tasks", [])

    if not plan_markdown:
        print("Error: Response missing 'plan_markdown'.", file=sys.stderr)
        sys.exit(1)

    # --- Write Plan ---
    plan_out_path.write_text(plan_markdown, encoding="utf-8")
    print(f"==> Written master plan to {plan_out_path}", file=sys.stderr)

    # --- Write Tasks ---
    # Clear tasks dir first
    if tasks_dir.exists():
        print(f"==> Clearing existing tasks in {tasks_dir} ...", file=sys.stderr)
        shutil.rmtree(tasks_dir)

    task_count = 0
    if tasks:
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            filename = task.get("filename")
            content = task.get("content")
            if filename and content:
                task_path = tasks_dir / filename
                task_path.write_text(content, encoding="utf-8")
                print(f"    Written task: {task_path}", file=sys.stderr)
                task_count += 1
    else:
        print("Warning: No tasks generated.", file=sys.stderr)

    return plan_out_path, task_count
