#!/usr/bin/env python3
"""PreToolUse hook — an unattended run may not publish.

    REPO-LOCAL. Not a cascadia-standards template. Do not propagate.

WHY THIS IS NOT IN THE TEMPLATE

`no_blanket_add_or_force_push.py` carries estate-wide invariants: blanket
staging and force pushing are wrong in every repo, always, by anyone. This
rule is not that shape. It is a property of repos that have a scheduled
task, and it distinguishes by WHO is running rather than by WHAT is run --
Aaron pushing this repo interactively is normal and expected work, and a
rule in the shared template that refused it would fight every other repo in
the estate. So it lives here, beside the template rather than inside it.

WHAT CHANGED TO MAKE THIS NECESSARY

The scheduled live-edge run stalled 3h44m on a permission prompt for a
diagnostic command nobody could have allowlisted in advance, so the desktop
surface for this repo was moved to bypassPermissions. That mode skips the
permission layer, which is where `Bash(git push*)` sat in the "ask" list.
PreToolUse hooks are run by Claude Code itself and bind regardless of mode,
so the rule moves here or it does not exist.

The scheduled task's own brief says, in as many words, that committing the
run record is Aaron's decision and not a scheduled task's. This makes that
structural rather than remembered.

HOW "UNATTENDED" IS DETERMINED

The payload carries `transcript_path`. A scheduled run's first user message
is the task envelope, which opens with a `<scheduled-task` tag. Nothing an
interactive session does produces that, and it is present before the first
tool call, so it is readable by the time any push could be attempted.

FAIL DIRECTIONS, WHICH ARE DELIBERATELY NOT THE SAME FOR BOTH RULES

  push    fails CLOSED. If the transcript is missing or unreadable we
          cannot prove a human is present, and a push is outward-facing and
          seen by the site and by every clone. Refusing costs one command;
          the escape hatch below is one flag.
  commit  fails OPEN. A commit is local and revocable, and denying every
          commit in a session where detection merely broke would be a
          worse failure than the one being prevented.

THE ESCAPE HATCH

    git -c cascadia.deliberate=true push origin main

`git -c` takes arbitrary config, so this is inert to git and visible in the
command string, which is all this hook can see. It cannot be set by accident
and it cannot be inherited from the environment -- it has to be typed into
the command being run, which is the definition of a deliberate act. That is
PRINCIPLES rule 1's shape: refreshing, and publishing, are deliberate acts
and never side effects.
"""

import json
import os
import re
import sys

# A leading `git` may carry its own options (-C <path>, -c k=v) before the
# subcommand. Same shape as the sibling hook, for the same reason.
_GIT = r"\bgit\s+(?:-[cC]\s+\S+\s+|--\S+\s+)*"

PUSH = re.compile(_GIT + r"push\b")
COMMIT = re.compile(_GIT + r"commit\b")
DELIBERATE = re.compile(r"-c\s+cascadia\.deliberate=true\b")

SEGMENT = re.compile(r"&&|\|\||;|\||\n")

# How many transcript lines to read before giving up. The envelope is the
# first user message; 40 is generous and bounds the read on a transcript
# that is tens of megabytes by the end of a long session.
ENVELOPE_LINES = 40

HATCH = ("If you mean it, say so in the command:\n"
         "    git -c cascadia.deliberate=true push origin main")


def is_scheduled(transcript_path):
    """True if this session was launched by a scheduled task.

    Returns None -- not False -- when it cannot be determined, so the two
    rules can fail in different directions.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for _ in range(ENVELOPE_LINES):
                line = fh.readline()
                if not line:
                    break
                if "<scheduled-task" in line:
                    return True
    except OSError:
        return None
    return False


def deny(reason):
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(2)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    if "git" not in cmd:
        return 0

    scheduled = is_scheduled(payload.get("transcript_path"))

    for segment in SEGMENT.split(cmd):
        if DELIBERATE.search(segment):
            continue
        if PUSH.search(segment) and scheduled is not False:
            deny(
                "Refused: an unattended run does not publish.\n\n"
                f"    {segment.strip()}\n\n"
                + ("This session was launched by a scheduled task."
                   if scheduled else
                   "This session could not be shown to be interactive, and a "
                   "push fails closed.")
                + "\n\nPushing this repo is a deliberate act (CLAUDE.md, "
                  "PRINCIPLES rule 1). A scheduled run reports; a human "
                  f"publishes.\n\n{HATCH}"
            )
        if COMMIT.search(segment) and scheduled is True:
            deny(
                "Refused: a scheduled run does not commit its own record.\n\n"
                f"    {segment.strip()}\n\n"
                "The live-edge task writes data/live/, governance/health.json "
                "and governance/reconciliation.md. Committing that record is "
                "Aaron's decision, not a scheduled task's -- the task brief "
                "says so explicitly. Report what moved and leave it in the "
                "working tree."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
