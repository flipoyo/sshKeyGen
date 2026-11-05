# KeyGenPackage — `gk`, one class that makes a user's ssh keys on any machine, and that atCGS can use

*Created: 2026-11-05*

*Revised: 2026-11-05 — made compatible with atCGS 1.7.1-alpha*

*Branch: 1-gk*

*Source: GitHub issue [flipoyo/sshKeyGen#1](https://github.com/flipoyo/sshKeyGen/issues/1) — "ergonomy and security - KeyGen Python Package"*

## Abstract — read this first

**The one-line version.** Replace `genkey.sh` with one Python class, shipped as
the package `gk`, that turns *one login and one password* into the same
identity on any machine — and let [atCGS](https://github.com/flipoyo/atCGS)
use that same class instead of keeping its own copy.

**What this document is.** A ticket. Nothing here has been built.

**Why it exists.** The issue asks for a UX target (README of 100 lines at most)
and a security target (the private key is protected by a passphrase derived from
a declared secret). Reading atCGS changes the question. atCGS already derives a
user's identity from login and password (Argon2id, Ed25519), stores nothing,
and keeps each user's ssh keys in an encrypted GLYPH. If `gk` invents a second
derivation, one person ends up with two identities that never match. So `gk`
reuses atCGS's derivation byte for byte, and becomes the one place where it lives.

**What you will find.** §1 what exists on both sides. §2 the compatibility
contract. §3 the target class. §4 decisions. §5 work packages. §6 acceptance.
§7 what is left to atCGS.

**Who it is for.** Whoever implements it, and the owner, who answers §4.

**What you need to do with it.** Answer §4, then work §5 in order.

```mermaid
graph TD
    SH["genkey.sh<br/>today"] -->|rewritten as| GK["gk — KeyGen class<br/>YOU ARE HERE"]
    GK -->|"gk command"| USER["one user, any machine<br/>keys in ~/.ssh"]
    GK -->|"class API, in memory"| AT["atCGS<br/>identity, GLYPH, session"]
    AT -.->|"later: imports gk,<br/>drops its copy"| GK

    classDef here fill:#1565C0,color:#fff,stroke:#111,stroke-width:2px;
    class GK here;
```

---

## Security reminder — read this before you write any code

**This section is shown as a confirmation pop-up the first time Claude Code
edits `src/gk/`, `tests/` or `pyproject.toml` in a session** (hook:
`.claude/hooks/gk-security-reminder.py`). It only fires for Claude Code; if you
edit by hand, this section is the reminder.

**The issue.** `gk` turns a password into key material. Whoever can *test* a
password guess against something they hold can try billions of guesses offline.
Every design choice below is about what that "something" is, and who can see it.

| Where a guess can be tested | Who can see it | Verdict |
|---|---|---|
| The ssh **public** key (derive mode) | Everyone: it is on GitHub | Worst. Public data checks the password |
| `sha256(password)` as the key passphrase | Whoever steals `~/.ssh/<key>` | Weak: fast, unsalted |
| The **GLYPH** (authenticated encryption) | Whoever steals one private file | Acceptable: slow Argon2id, private file, per-login salt |

**Why the GLYPH is the right answer, and what it does not solve.** The GLYPH
moves the thing that checks the password from a public place (the public key) to
a private file, and makes each guess cost Argon2id (256 MiB, 3 passes). It is
the right default. It does **not**:

- fix a weak password: a stolen GLYPH is still attackable offline, only slower;
- protect a machine that is compromised while the GLYPH is open or the keys are in the agent;
- hide that you own a GLYPH, nor survive its loss (it is one file: keep a copy);
- hold more than about fifteen keys (8 192 bytes).

**The strategy.** Nine rules, each checked in §6.

| # | Rule | How |
|---|---|---|
| S1 | The GLYPH is the source of truth; `~/.ssh/<key>` is an optional export | `gk` generates into the GLYPH first. A key file is written only on request |
| S2 | No derive mode in 0.2.0 | A derived key's public half would be a public check on the password. Deferred, not cancelled (D3) |
| S3 | Password policy | At least 16 characters, refuse the 10 000 most common, `real` profile only. The `test` profile needs an explicit env var and prints a warning |
| S4 | Nothing on disk on a machine you do not own | `gk load` reads the GLYPH, pipes keys to a private ssh-agent and never writes them (`ssh-add -` from stdin; confirm in the WP-K4 spike), with `ssh-add -t` as a time limit |
| S5 | GLYPH hygiene | Directory 0700, file 0600, atomic write, never in a git repository (`*.glyph` in `.gitignore` and a refusal to write inside a work tree), one backup copy |
| S6 | The secret never leaks | `getpass` or a file descriptor only; never argv, env value, log or exception text |
| S7 | A lost GLYPH is a revocation procedure | The public keys on each platform are the list. `gk` prints it and the removal URLs |
| S8 | Attacker tests | A flipped bit is refused; a wrong password is refused; no private key appears in the GLYPH bytes; two GLYPHs of the same user differ (fresh nonce) |
| S9 | The classic passphrase prompt is forced | Wherever a person types a passphrase for a key file (`gk` creating or exporting a `~/.ssh` key, as `ssh-keygen` does today), it must be **at least 8 characters** and asked twice. Empty is refused, where `ssh-keygen` accepts it. This is the floor for a *key-file* passphrase; the GLYPH's master password stays at 16 (S3) |

**Before you merge.** You can answer yes to S1 to S9, and to this: *if my GLYPH
file were stolen tomorrow, would the password hold?* If not, change the password,
not the code.

## Implementation status — 2026-11-05

Implemented on `1-gk` as `gk 0.2.0`. `pixi run lint` and `pixi run test` pass (43 tests, Linux, Python 3.11).
Checked against atCGS's own code (`identity.derive`, `glyph.open_glyph`, `glyph.seal`): same IDSEED and UID for
`tests/vectors.toml`, a GLYPH written by `gk` opens in atCGS, and one written by atCGS opens in `gk`.

| WP | State |
|---|---|
| K1 decisions | D1 HKDF passphrase, D2 in Python, D3 no derive mode, D4 `gk` owns the derivation, D5 pip/pipx plus Pixi, D6 shim kept. D7 (classic `~/.ssh` result **and** `gk passphrase`) taken as the recommendation; not confirmed by the owner |
| K2–K8, K10 | Done |
| K9 | README (83 lines), `CHANGELOG.md` done |
| K11 | `.github/workflows/ci.yml` written for Linux and macOS; **not run yet**. Windows is not claimed: the tests use POSIX modes and `pass_fds` |

**Deviations from this ticket**

- **S3, common-password list.** A short built-in list of 16+ character entries, not 10 000. At this length, the length rule is the real defence.
- **S6 over WP-K7.** The password is read from `getpass` or `--password-fd` only; the env-var option in WP-K7 was dropped because S6 forbids an environment value.
- **S4 spike.** `ssh-add -` reads a key from stdin with `-t`, confirmed on OpenSSH 10.2 (Linux). macOS and Windows are not confirmed.
- **Windows.** File modes (S5) have no meaning there; the package is untested on it.
- **The edit-time reminder** did not fire while this was implemented: Claude Code loads hooks at session start, so the hook added in the same session was inactive.

**Still open:** run the CI once on GitHub; register the signing key; open the atCGS ticket (§7); decide whether to archive this ticket.

---

## 1. What exists

### sshKeyGen (this repository)

| Item | State |
|---|---|
| `genkey.sh EMAIL [PLATFORM] [HOSTNAME] [PROFILE]` | Makes `~/.ssh/id_ed25519[_platform][_host][_profile]`, loads it into ssh-agent, prints the public key and a config snippet. Version `0.1.0` |
| Platforms | `github`, `gitlab`, `codeberg` accepted; only the first two get a config snippet and URL |
| Passphrase | None set; `ssh-keygen` prompts, and an empty answer is accepted |
| Packaging, tests, CI | None. Bash and OpenSSH only, so no Windows |

### atCGS 1.7.1-alpha (what `gk` must fit)

| Item | State |
|---|---|
| Identity | `IDSEED = Argon2id(password, salt = "atCGS/id/v1/" + profile + "/" + login)`, 32 bytes, login and password NFC-normalised. Ed25519 key from the seed; `UID = sha256(public key)`. Nothing is stored |
| KDF profiles | `real`: 256 MiB, 3 passes. `test`: 8 MiB, 1 pass, for CI. Env `ATCGS_KDF_PROFILE` |
| ssh keys | `SshKey(repo, role, private)`: an unencrypted OpenSSH Ed25519 key, in memory only, generated at random |
| GLYPH | 8 192 bytes at `~/.cgs/.glyph/<UID>.glyph`; holds the user's private ssh keys, sealed with `HKDF(IDSEED)` |
| Session | Loads the keys into a private ssh-agent and offers each repo its own key, never `~/.ssh` (`-F /dev/null`) |
| Stack | Python 3.11, `cryptography>=44`, Pixi (linux-64, win-64, osx-arm64), ruff, pytest. Version is SemVer 2.0.0 and must equal `atcgs.__version__` |

## 2. The compatibility contract

Six rules. A change to any of them is a major version of `gk` and of atCGS together.

| # | Rule | Why |
|---|---|---|
| C1 | `gk.derive(login, password, profile)` returns the same IDSEED as atCGS: same salt string (`atCGS/id/v1/<profile>/<login>`), same Argon2id parameters, same NFC normalisation | One person, one UID, in both tools |
| C2 | The profile names are `real` and `test`, with atCGS's costs, and `ATCGS_KDF_PROFILE` is honoured | atCGS's test suite and `gk`'s can share one setting |
| C3 | Every other secret `gk` needs is `HKDF(IDSEED, info = "gk/<purpose>/v1/…")`. The purposes are `passphrase` and `ssh`. Different info strings, so no derived value can stand in for another | A leaked ssh key must not reveal the IDSEED or the passphrase |
| C4 | `gk` has an in-memory sink: `KeyGen` can return its keys as objects with `repo`, `role`, `private`, `public` — the shape of atCGS's `SshKey` — and touch no file | atCGS never writes to `~/.ssh` |
| C5 | `gk` imports nothing from atCGS. atCGS imports `gk` later | The dependency has one direction |
| C6 | A shared test-vector file (login, password, profile `test` → IDSEED, UID) is checked by both repositories | The only way two copies of a derivation stay identical |

`gk` adds one dependency over atCGS's list, `bcrypt`, and only if the
passphrase-protected key file is written by Python (see D2).

## 3. The target class

One module, one class, so it can be vendored whole.

```python
from gk import KeyGen

kg = KeyGen(login="me@x.org", password=secret, profile="real")   # derives once
kg.uid                                                          # str, same as atCGS
key = kg.ssh_key("github", "laptop", "pro")                     # SshKey-shaped, in memory
kg.write(key, ssh_dir="~/.ssh")                                 # file + permissions + config snippet
kg.load_into_agent(key)                                         # no file needed
kg.glyph_add(key)                                               # seal into the GLYPH (the primary store)
```

| Mode | What happens | Needs on a new machine |
|---|---|---|
| **GLYPH** (the only mode in 0.2.0) | A fresh random Ed25519 key, sealed in the GLYPH. `gk load` puts it in a private ssh-agent with nothing on disk; `gk export` writes `~/.ssh/<key>` encrypted with the passphrase `HKDF(IDSEED, "gk/passphrase/v1")` | login, password and the GLYPH file (8 KB, copy it) |
| **derive** (deferred, see D3) | The key *is* `HKDF(IDSEED, "gk/ssh/v1/<platform>/<host>/<profile>/<n>")` | login and password only |

Key naming, the platform table (with the missing codeberg snippet and URL),
the overwrite guard and permissions (700/600/644) carry over from `genkey.sh`.
The `gk` command is a thin parser over the class and holds no logic.

**UX contract.** `README.md` is at most 100 lines: install, one command,
register the key, test it. The Git/SSH tutorial already lives in
`docs/ssh-git-guide.md`.

## 4. Decisions — your call

### D1. What is the passphrase?

The issue says `sha256(password)`. That is a fast, unsalted hash: anyone who
holds the key file can test guesses at billions per second, and the same
password gives the same passphrase everywhere.

| Option | What happens |
|---|---|
| **`HKDF(IDSEED, "gk/passphrase/v1")`** (recommended) | The declared secret goes through atCGS's Argon2id, so a guess costs 256 MiB and about a second. Same UX: the user types one password. Meets the issue's intent, not its letter |
| `sha256(password)` as written | Meets the issue literally; document the weakness in the README |

### D2. How is the encrypted key file written?

Never by putting the passphrase on the `ssh-keygen` command line (visible in `ps`).

| Option | What happens |
|---|---|
| **In Python** (recommended) | `cryptography` writes the OpenSSH key, encrypted. Adds `bcrypt` as a dependency; confirm in WP-K4 that the installed `cryptography` version needs it. Also the only route that works the same on Windows |
| `ssh-keygen` through `SSH_ASKPASS` | Keeps OpenSSH as the only crypto, but needs a helper script and breaks on Windows |

### D3. Is *derive* mode allowed?

**Decided on 2026-11-05: no, not in 0.2.0. The GLYPH is the default and only mode.**
In derive mode the ssh public key, which is public on GitHub, is also a check on
the password: anyone can test guesses against it offline. atCGS accepts that for
its identity (the UID sits in a journal); for ssh keys on a public platform it is
a worse trade. Reopen only with the S3 password policy enforced and your explicit
sign-off, and a note here saying why.

### D4. Where does the derivation live?

C1 needs one source. Recommendation: `gk` owns it, atCGS imports it later
(§7). Until then both hold a copy, guarded by C6. Confirm you want atCGS to
depend on `gk` rather than the reverse.

### D5. Install path on a machine you do not own

atCGS runs "under Pixi only". A random machine usually has Python and not Pixi.
Recommendation: `gk` is one file plus `cryptography`, runnable with
`pipx run gk` or `pip install gk`, and Pixi remains the contributor
environment, the same split as ComplexGitSync's UserInstallPath ticket.

### D6. Fate of `genkey.sh`, and the PyPI name

Keep a one-line shim for one release, then delete it. Check that `gk` is free on
PyPI before promising `pipx install gk`; if not, publish under another name and
keep the command `gk`.

## 5. Work packages

| WP | Depends on | Touches | Deliverable |
|---|---|---|---|
| **WP-K1** | — | this ticket | D1–D6 recorded |
| **WP-K2** | — | `pixi.toml`, `pyproject.toml`, `ruff.toml`, `src/gk/` | Skeleton to the atCGS standard: Python 3.11, `cryptography>=44`, platforms linux-64/win-64/osx-arm64, `pixi run test` and `pixi run lint`. Version `0.2.0`, in one place, equal to `gk.__version__` |
| **WP-K3** | WP-K2 | `src/gk/keygen.py` | `KeyGen`: naming, platform table (with codeberg), overwrite guard, permissions, config snippet |
| **WP-K4** | WP-K1, WP-K3 | `src/gk/keygen.py` | `derive` (C1, C2), HKDF purposes (C3), password policy (S3), encrypted key export (D2), `load_into_agent`. Spike first: confirm `ssh-add -` reads a key from stdin on the three platforms (S4) |
| **WP-K5** | WP-K4 | `src/gk/keygen.py`, `tests/vectors.toml` | `SshKey`-shaped output (C4) and the shared test-vector file (C6) |
| **WP-K6** | WP-K4 | `src/gk/keygen.py` | The GLYPH as the primary store (S1, S5): seal, open, add, `gk load`, `gk export`. Needs only the `CGSG` layout from atCGS's README § 6 |
| **WP-K7** | WP-K3 | `src/gk/cli.py` | Thin `gk` command; the secret comes from `getpass`, an env var or a file descriptor, never an argument; empty is an error; a key-file passphrase typed by a person is asked twice and refused below 8 characters (S9) |
| **WP-K8** | WP-K4 to WP-K7 | `tests/` | In a temporary `$HOME` and a private ssh-agent, so the suite never touches the real one: naming, no overwrite, modes, key is encrypted, same vector gives the same UID, the S8 attacker cases, the secret is in no argv |
| **WP-K9** | WP-K7 | `README.md`, `docs/`, `CHANGELOG.md` | README ≤ 100 lines, a "new machine" tutorial, a short compatibility note linking atCGS |
| **WP-K10** | WP-K7, D6 | `genkey.sh` | The shim or its removal |
| **WP-K11** | WP-K8 | `.github/workflows/` | CI on the three Pixi platforms |

## 6. Acceptance

- `gk me@x.org github laptop pro` makes `~/.ssh/id_ed25519_github_laptop_pro`
  and `.pub` as `genkey.sh` did, and refuses to overwrite.
- The private key file is encrypted: `ssh-keygen -y -f <key>` fails without the
  passphrase and succeeds with the derived one.
- The same login and password give the same UID in `gk` and in atCGS, checked
  against `tests/vectors.toml` in both repositories.
- A GLYPH written by `gk` opens in atCGS (`atcgs.glyph.open_glyph`) and the keys
  match; a GLYPH written by atCGS opens in `gk`.
- `gk load` leaves no private key on disk (checked by listing `$HOME` before and
  after) and the agent holds the key.
- Security rules S1 to S9 each have a test or a documented check, and the
  question "if my GLYPH were stolen, would the password hold?" is answered in the PR.
- The secret appears in no process argument list and no log.
- `from gk import KeyGen` works in a clean environment, and every method in §3
  runs with no terminal.
- `wc -l README.md` ≤ 100; `gk --version` prints a SemVer string; `pixi run lint`
  and `pixi run test` pass on the three platforms.

## 7. What is left to atCGS (not in this ticket)

- Replace `atcgs/identity.py`'s `derive` and `SshKey.generate` with imports from
  `gk`, keeping C6's vectors as the guard.
- Add a row to `spec/contracts.toml` pinning the `gk` version it needs.
- Decide whether `request` should accept keys made by `gk` (random or derived)
  instead of generating its own.
- Open a ticket in atCGS referencing this one.

**Not in this ticket.** Key rotation and revocation, registering keys through
platform APIs (atCGS's `deploy-keys` covers GitHub), and any change to atCGS itself.
