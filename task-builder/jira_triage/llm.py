import os
import subprocess
import sys

from .config import LLMConfig


def call_llm(prompt: str, llm: LLMConfig) -> str:
    result = subprocess.run(
        [llm.command, "-m", llm.model, "-p", prompt],
        capture_output=True,
        text=True,
        env={**os.environ, **llm.env},
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"{llm.command} CLI exited with code {result.returncode}")
    return result.stdout
