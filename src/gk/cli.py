"""The gk command: a thin parser over KeyGen. No logic lives here (ticket, section 3).

    gk EMAIL [PLATFORM] [HOSTNAME] [PROFILE]     make a key (classic result: ~/.ssh + agent + GLYPH)
    gk load EMAIL [NAME]                         put GLYPH keys in the agent, nothing on disk
    gk export EMAIL NAME                         write a GLYPH key to ~/.ssh
    gk passphrase EMAIL                          print the passphrase of exported key files
    gk list EMAIL                                list the GLYPH's keys

The password is read with getpass, or from a file descriptor with --password-fd.
It is never an argument and never an environment value (S6).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from gk.keygen import (
    GkError,
    KeyGen,
    __version__,
    check_key_passphrase,
)

COMMANDS = {"create", "load", "export", "passphrase", "list"}


def _secret(prompt: str, fd: int | None) -> str:
    if fd is not None:
        with os.fdopen(fd, "r", closefd=False) as handle:
            return handle.readline().rstrip("\r\n")
    return getpass.getpass(prompt)


def _new_secret(prompt: str, fd: int | None) -> str:
    first = _secret(prompt, fd)
    if fd is None and getpass.getpass("Again: ") != first:
        raise GkError("the two entries differ")
    return first


def _own_passphrase() -> str:
    """S9: typed twice, at least 8 characters, never empty."""
    first = getpass.getpass("Key file passphrase (8+ characters): ")
    check_key_passphrase(first)
    if getpass.getpass("Again: ") != first:
        raise GkError("the two entries differ")
    return first


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"gk {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--password-fd", type=int, metavar="N", help="read the password from file descriptor N")
        sp.add_argument("--ssh-dir", metavar="DIR", help="default: ~/.ssh")

    c = sub.add_parser("create", help="make a key (the default when no command is given)")
    c.add_argument("email")
    c.add_argument("platform", nargs="?", default="")
    c.add_argument("hostname", nargs="?", default="")
    c.add_argument("profile", nargs="?", default="")
    c.add_argument("--no-export", action="store_true", help="GLYPH only; write nothing to ~/.ssh")
    c.add_argument("--no-agent", action="store_true")
    c.add_argument("--own-passphrase", action="store_true", help="type the key file passphrase yourself (8+ characters)")
    common(c)
    ld = sub.add_parser("load", help="load GLYPH keys into the ssh-agent; nothing is written to disk")
    ld.add_argument("email")
    ld.add_argument("name", nargs="?")
    ld.add_argument("--lifetime", type=int, default=3600, metavar="SECONDS", help="agent lifetime (default 3600)")
    common(ld)
    ex = sub.add_parser("export", help="write a GLYPH key to ~/.ssh")
    ex.add_argument("email")
    ex.add_argument("name")
    ex.add_argument("--own-passphrase", action="store_true")
    common(ex)
    ps = sub.add_parser("passphrase", help="print the passphrase of exported key files (it is a secret)")
    ps.add_argument("email")
    common(ps)
    ls = sub.add_parser("list", help="list the GLYPH's keys")
    ls.add_argument("email")
    common(ls)
    return p


def _run(args: argparse.Namespace) -> int:
    password = (_new_secret if args.command == "create" else _secret)("Password: ", args.password_fd)
    kg = KeyGen(args.email, password)
    if args.command == "passphrase":
        print("Anyone with this passphrase and your key file can use the key.", file=sys.stderr)
        print(kg.passphrase())
        return 0
    if args.command == "list":
        for key in kg.glyph_keys():
            print(f"{key.repo}\t{key.fingerprint}")
        return 0
    if args.command == "load":
        keys = kg.find(args.name)
        if not keys:
            raise GkError("no matching key in the GLYPH")
        for key in keys:
            kg.load_into_agent(key, lifetime=args.lifetime)
            print(f"loaded {key.repo} for {args.lifetime}s")
        return 0
    if args.command == "export":
        found = kg.find(args.name)
        if not found:
            raise GkError("no such key in the GLYPH")
        path = kg.write(found[0], args.ssh_dir, passphrase=_own_passphrase() if args.own_passphrase else None)
        print(f"exported {path}")
        return 0

    # create
    key = kg.ssh_key(args.platform, args.hostname, args.profile)
    own = _own_passphrase() if args.own_passphrase and not args.no_export else None
    ssh_dir = Path(args.ssh_dir).expanduser() if args.ssh_dir else Path.home() / ".ssh"
    if not args.no_export and (ssh_dir / key.repo).exists():
        raise GkError(f"an ssh key already exists: {ssh_dir / key.repo}")
    glyph = kg.glyph_add(key)
    print(f"GLYPH   : {glyph}")
    path = None
    if not args.no_export:
        path = kg.write(key, ssh_dir, passphrase=own)
        print(f"KEY PATH: {path}")
    if not args.no_agent and os.environ.get("SSH_AUTH_SOCK"):
        kg.load_into_agent(key)
        print("agent   : loaded")
    print(f"\nPUBLIC KEY\n{key.public} {args.email}\n")
    print(f"SSH CONFIG\n{kg.ssh_config(args.platform, path or key.repo)}")
    if args.platform:
        print(f"Register the public key on: {kg.register_url(args.platform)}")
        print(f"Test command: {kg.test_command(args.platform)}")
    if path and own is None:
        print("The key file's passphrase is derived from your password: use  gk load  or  gk passphrase.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "create")  # classic form: gk EMAIL [PLATFORM] [HOSTNAME] [PROFILE]
    try:
        return _run(_parser().parse_args(argv))
    except GkError as error:
        print(f"gk: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
