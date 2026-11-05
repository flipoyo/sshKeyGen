#!/usr/bin/env python3
"""Ask for confirmation, once per session, before Claude Code edits gk code.

The prompt shows the security reminder from the KeyGenPackage ticket. It is a
permission prompt ("ask"), so it cannot be skipped by accident. It does not fire
for edits made by hand in an editor; the ticket section is the reminder there.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

WATCHED = re.compile(r"(^|/)(src/gk/|tests/|pyproject\.toml$|pixi\.toml$)")
TICKET = ".localSpec/DevTickets/openTickets/1-gk_1-1_KeyGenPackage_DevPlanTicket.md"

REMINDER = f"""GK SECURITY REMINDER (ticket {TICKET})

A password becomes key material here. Whoever can test a guess against
something they hold can try billions offline.

Worst: the ssh PUBLIC key (derive mode) - public data would check the password.
Weak:  sha256(password) as a passphrase - fast, unsalted.
Right: the GLYPH - Argon2id, a private file, per-login salt.

The GLYPH does NOT fix a weak password, a compromised machine, or a lost file.

S1 GLYPH is the source of truth, ~/.ssh is an export    S5 GLYPH 0700/0600, never in git
S2 no derive mode in 0.2.0                              S6 secret never in argv, env, logs
S3 password >= 16 chars, real KDF profile only          S7 lost GLYPH = revocation procedure
S4 random machine: private agent, nothing on disk       S8 attacker tests (bit flip, wrong pw)

Answer before merging: if my GLYPH file were stolen tomorrow, would the password hold?

Approve to continue editing."""


def main() -> int:
    data = json.load(sys.stdin)
    path = (data.get("tool_input") or {}).get("file_path", "")
    if not WATCHED.search(path):
        return 0
    marker = Path(tempfile.gettempdir()) / f"gk-reminder-{data.get('session_id', 'x')}"
    if marker.exists():
        return 0
    marker.touch()
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": REMINDER,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
