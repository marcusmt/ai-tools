import json
import sys
from pathlib import Path
from typing import Optional

from .config import Config, get_llm_config
from .llm import call_llm


_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def analyze_ticket(ticket_id: str, config: Config, model_override: Optional[str] = None) -> Path:
    llm_cfg = get_llm_config(config, "analyze", model_override)

    ticket_dir = Path(ticket_id)
    raw_json_path = ticket_dir / f"{ticket_id}-raw.json"
    out_path = ticket_dir / f"{ticket_id}-parsed.md"

    if not raw_json_path.exists():
        print(
            f"Error: {raw_json_path} not found.\n"
            f"Run 'task-builder fetch {ticket_id}' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("==> Building prompt ...", file=sys.stderr)
    system_prompt = (_PROMPTS_DIR / "analyze_ticket.md").read_text(encoding="utf-8")
    ticket_data = json.loads(raw_json_path.read_text(encoding="utf-8"))

    full_prompt = (
        f"{system_prompt}\n\n"
        f"---\n\n"
        f"## Ticket Data (JSON)\n\n"
        f"{json.dumps(ticket_data, indent=2)}"
    )

    print(f"==> Calling {llm_cfg.command} ({llm_cfg.model}) ...", file=sys.stderr)
    response = call_llm(full_prompt, llm_cfg)

    if not response.strip():
        print(f"Error: {llm_cfg.command} returned an empty response.", file=sys.stderr)
        sys.exit(1)

    out_path.write_text(response, encoding="utf-8")
    print(f"==> Written to {out_path}", file=sys.stderr)
    return out_path
