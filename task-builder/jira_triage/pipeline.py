import sys
from enum import Enum
from pathlib import Path
from typing import Optional

from .analyze import analyze_ticket
from .config import load_config
from .fetch import fetch_ticket
from .investigate import investigate_ticket
from .plan import plan_ticket


class Stage(str, Enum):
    FETCH = "fetch"
    ANALYZE = "analyze"
    INVESTIGATE = "investigate"
    PLAN = "plan"


def run_pipeline(
    ticket_id: str,
    force: bool = False,
    from_stage: Optional[Stage] = None,
    model_override: Optional[str] = None,
) -> None:
    config = load_config()

    ticket_dir = Path(ticket_id)
    fetch_out = ticket_dir / f"{ticket_id}-raw.json"
    analyze_out = ticket_dir / f"{ticket_id}-parsed.md"
    investigate_out = ticket_dir / f"{ticket_id}-investigation.md"
    plan_out = ticket_dir / f"{ticket_id}-plan.md"

    stage_outputs = {
        Stage.FETCH: fetch_out,
        Stage.ANALYZE: analyze_out,
        Stage.INVESTIGATE: investigate_out,
        Stage.PLAN: plan_out,
    }

    stages = [Stage.FETCH, Stage.ANALYZE, Stage.INVESTIGATE, Stage.PLAN]

    if from_stage:
        idx = stages.index(from_stage)
        for i in range(idx):
            prior_stage = stages[i]
            prior_out = stage_outputs[prior_stage]
            if not prior_out.exists():
                print(
                    f"Cannot run from {from_stage.value}: {prior_out} not found.\n"
                    f"Run 'task-builder {prior_stage.value} {ticket_id}' "
                    f"or 'task-builder run {ticket_id} --from {prior_stage.value}'.",
                    file=sys.stderr,
                )
                sys.exit(1)

    for stage in stages:
        out_file = stage_outputs[stage]

        if force or (from_stage and stages.index(stage) >= stages.index(from_stage)):
            should_run = True
        elif not force and not from_stage:
            if out_file.exists():
                print(f"[{stage.value}] skipped (output exists at {out_file})")
                should_run = False
            else:
                should_run = True
        else:
            print(f"[{stage.value}] skipped (output exists at {out_file})")
            continue

        if not should_run:
            continue

        print(f"[{stage.value}] running...")
        try:
            if stage == Stage.FETCH:
                _, att_count = fetch_ticket(ticket_id, config)
                print(f"[{stage.value}] done ({fetch_out}, {att_count} attachment(s))")
            elif stage == Stage.ANALYZE:
                analyze_ticket(ticket_id, config, model_override)
                print(f"[{stage.value}] done ({analyze_out})")
            elif stage == Stage.INVESTIGATE:
                investigate_ticket(ticket_id, config, model_override)
                print(f"[{stage.value}] done ({investigate_out})")
            elif stage == Stage.PLAN:
                p_out, t_count = plan_ticket(ticket_id, config, model_override)
                print(f"[{stage.value}] done ({p_out}, {t_count} tasks)")
        except KeyboardInterrupt:
            raise
        except BaseException as e:
            print(f"[{stage.value}] FAILED", file=sys.stderr)
            if isinstance(e, SystemExit):
                if e.code != 0:
                    raise
                return
            print(f"\nError: {stage.value} stage failed with: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"\nPipeline complete. Plan: {plan_out}")
