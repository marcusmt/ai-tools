import sys
from pathlib import Path
from typing import Optional

from .config import Config, get_llm_config
from .llm import call_llm


_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def investigate_ticket(ticket_id: str, config: Config, model_override: Optional[str] = None) -> Path:
    llm_cfg = get_llm_config(config, "investigate", model_override)

    ticket_dir = Path(ticket_id)
    triage_path = ticket_dir / f"{ticket_id}-parsed.md"
    out_path = ticket_dir / f"{ticket_id}-investigation.md"

    if not triage_path.exists():
        raise SystemExit(
            f"Triage not found: {triage_path}\n"
            f"Run `task-builder analyze {ticket_id}` first."
        )

    triage = triage_path.read_text(encoding="utf-8")
    system_prompt = (_PROMPTS_DIR / "investigate.md").read_text(encoding="utf-8")

    full_prompt = (
        f"{system_prompt}\n\n"
        f"---\n\n"
        f"## Triage\n\n"
        f"{triage}"
    )

    print(f"==> Calling {llm_cfg.command} ({llm_cfg.model}) ...", file=sys.stderr)
    response = call_llm(full_prompt, llm_cfg)

    if not response.strip():
        print(f"Error: {llm_cfg.command} returned an empty response.", file=sys.stderr)
        sys.exit(1)

    out_path.write_text(response, encoding="utf-8")
    print(f"==> Written to {out_path}", file=sys.stderr)
    return out_path
