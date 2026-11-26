"""command_tool's execution: a program the operator listed, run without a shell, and nothing else.

AppCity's command_tool ran any shell command a model wrote. A model that can do that for a web visitor owns the
server, so this one is off until the operator names the programs in COMMAND_TOOL_ALLOWED (a comma list of program
names, e.g. "date,uname"); with an empty list every call is refused. When a program is listed:

- the command is split into words by shlex and run directly (no shell, so no pipes, redirects, `;`, `&&`, `$(...)`);
- the first word must be exactly a listed name, never a path (so `/bin/sh` or `./x` cannot be smuggled in);
- it runs in an empty temporary directory with an almost empty environment (no secrets, no PATH tricks);
- a short timeout kills it, and its output is cut at a small size.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

import logging
logger = logging.getLogger(__name__)

TIMEOUT_DEFAULT = 5
TIMEOUT_MAX = 10
OUTPUT_CHARS = 8000
COMMAND_MAX = 300
ARGS_MAX = 20
SAFE_PATH = "/usr/local/bin:/usr/bin:/bin"


class CommandError(ValueError):
    """The command is not allowed or could not run; the message goes back to the model."""


@dataclass(frozen=True)
class Ran:
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool


def allowed_programs() -> set[str]:
    try:
        return {p.strip() for p in os.environ.get("COMMAND_TOOL_ALLOWED", "").split(",") if p.strip()}
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("allowed_programs failed")
        raise


def parse(command: str | list[str]) -> list[str]:
    try:
        if isinstance(command, list):
            if not all(isinstance(word, str) for word in command):
                raise CommandError("A command list holds text only")
            words = [word for word in command]
        elif isinstance(command, str):
            if len(command) > COMMAND_MAX:
                raise CommandError(f"The command is longer than {COMMAND_MAX} characters")
            try:
                words = shlex.split(command)
            except ValueError:
                raise CommandError("The command could not be read (check the quotes)") from None
        else:
            raise CommandError("The command must be text or a list of words")
        if not words:
            raise CommandError("The command is empty")
        if len(words) > ARGS_MAX or any("\x00" in word or len(word) > COMMAND_MAX for word in words):
            raise CommandError("The command is too long or holds a bad character")
        return words
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("parse failed")
        raise


def run(command: str | list[str], timeout: int = TIMEOUT_DEFAULT) -> Ran:
    try:
        allowed = allowed_programs()
        if not allowed:
            raise CommandError("command_tool is not enabled on this server")
        words = parse(command)
        program = words[0]
        if program not in allowed:
            raise CommandError(f"That program is not allowed. Allowed: {', '.join(sorted(allowed))}")
        found = shutil.which(program, path=SAFE_PATH)
        if found is None:
            raise CommandError(f"{program} is not installed here")
        with tempfile.TemporaryDirectory(prefix="cmd-") as workdir:
            try:
                done = subprocess.run(  # noqa: S603 (no shell; the program is one the operator listed)
                    [found, *words[1:]],
                    cwd=workdir,
                    env={"PATH": SAFE_PATH, "LANG": "C.UTF-8", "HOME": workdir},
                    capture_output=True,
                    timeout=max(1, min(timeout, TIMEOUT_MAX)),
                    stdin=subprocess.DEVNULL,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise CommandError("The command took too long and was stopped") from None
            except OSError as error:
                raise CommandError(f"The command could not run ({type(error).__name__})") from None
        out = done.stdout.decode("utf-8", errors="replace")
        err = done.stderr.decode("utf-8", errors="replace")
        return Ran(done.returncode, out[:OUTPUT_CHARS], err[:OUTPUT_CHARS], len(out) > OUTPUT_CHARS or len(err) > OUTPUT_CHARS)
    except Exception as error:
        if getattr(error, "status_code", None) is None:
            logger.exception("run failed")
        raise
