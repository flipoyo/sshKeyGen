"""gk: one class that makes a user's ssh keys on any machine, and that atCGS can use.

One login and one password give the same identity everywhere. The derivation is
atCGS's, byte for byte (ticket rule C1): same salt, same Argon2id costs, same
NFC normalisation. Everything else is HKDF of that seed under a named purpose
(C3), so no derived value can stand in for another.

Where the secrets live (ticket, "Security reminder"):

* The GLYPH is the source of truth for private keys (S1). It is atCGS's file
  format, so atCGS opens what gk writes and the reverse.
* ``~/.ssh/<key>`` is an export, encrypted. Nothing leaves this module in an
  argument list, a log line or an exception text (S6).
* Python cannot promise that a secret is wiped from memory. The seed is kept in
  one object and never printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import unicodedata
import warnings
from base64 import b64decode, b64encode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_ssh_private_key,
)

__version__ = "0.2.0"  # SemVer 2.0.0; must equal pyproject.toml and pixi.toml

# --- the atCGS contract (C1, C2): changing any of these is a major version of both ---
KDF_PROFILES: Mapping[str, tuple[int, int, int]] = {
    "real": (256 * 1024, 3, 1),  # memory KiB, iterations, lanes
    "test": (8 * 1024, 1, 1),
}
PROFILE_ENV = "ATCGS_KDF_PROFILE"
ALLOW_TEST_ENV = "GK_ALLOW_TEST_PROFILE"
SALT_PREFIX = "atCGS/id/v1/"
GLYPH_INFO = b"atCGS/glyph/v1"
GLYPHS_ENV = "ATCGS_GLYPHS"

# --- gk's own purposes (C3) ---
PASSPHRASE_INFO = b"gk/passphrase/v1"

# --- GLYPH layout (atCGS README section 6) ---
GLYPH_BYTES = 8192
MAGIC, GLYPH_VERSION = b"CGSG", 1
NONCE, TAG = 12, 16
HEADER = len(MAGIC) + 1 + NONCE
PLAINTEXT = GLYPH_BYTES - HEADER - TAG
_LENGTH = struct.Struct(">I")

MIN_PASSWORD = 16  # S3: the GLYPH master password
MIN_KEY_PASSPHRASE = 8  # S9: a passphrase a person types for a key file

PLATFORMS: Mapping[str, tuple[str, str]] = {
    "github": ("github.com", "https://github.com/settings/keys"),
    "gitlab": ("gitlab.com", "https://gitlab.com/-/user_settings/ssh_keys"),
    "codeberg": ("codeberg.org", "https://codeberg.org/user/settings/keys"),
}

# Entries of 16 characters or more from public breach lists. Length is the real
# defence at this size; a full list is a follow-up (ticket, S3).
_COMMON = frozenset({
    "1234567890123456", "12345678901234567890", "passwordpassword", "password12345678", "password1234567890",
    "qwertyuiopasdfgh", "qwertyuiopasdfghjkl", "iloveyouiloveyou", "0123456789abcdef", "abcdefghijklmnop",
    "abcdefghijklmnopqrstuvwxyz", "1111111111111111", "0000000000000000", "letmeinletmein1234",
    "administrator1234", "changemechangeme1", "correcthorsebatterystaple",
})
_NAME_PART = re.compile(r"^[A-Za-z0-9._-]*$")


class GkError(ValueError):
    """Something gk refuses to do. The message never contains a secret."""


class PolicyError(GkError):
    """A password or passphrase is too weak."""


class GlyphError(GkError):
    """The GLYPH does not open, or the keys do not fit in it."""


def _normalise(text: str, what: str) -> bytes:
    if not text:
        raise GkError(f"empty {what}")
    return unicodedata.normalize("NFC", text).encode("utf-8")


def derive(login: str, password: str, profile: str = "real") -> bytes:
    """IDSEED = Argon2id(password, salt = "atCGS/id/v1/" + profile + "/" + login), 32 bytes (C1)."""
    if profile not in KDF_PROFILES:
        raise GkError(f"unknown KDF profile: {profile!r}")
    memory, iterations, lanes = KDF_PROFILES[profile]
    salt = SALT_PREFIX.encode() + profile.encode() + b"/" + _normalise(login, "login")
    return Argon2id(
        salt=salt, length=32, iterations=iterations, lanes=lanes, memory_cost=memory
    ).derive(_normalise(password, "password"))


def uid_of(public: bytes) -> str:
    """UID = sha256(IDPUB): the only name atCGS gives a user."""
    return hashlib.sha256(public).hexdigest()


def check_password(password: str, login: str = "") -> None:
    """S3: the GLYPH master password. Raises PolicyError; never echoes the password."""
    text = unicodedata.normalize("NFC", password)
    if len(text) < MIN_PASSWORD:
        raise PolicyError(f"the password must have at least {MIN_PASSWORD} characters")
    lowered = text.lower()
    if lowered in _COMMON:
        raise PolicyError("this password is on a list of common passwords")
    if len(set(text)) < 5:
        raise PolicyError("the password repeats too few distinct characters")
    local = login.split("@")[0].lower()
    if len(local) >= 4 and local in lowered:
        raise PolicyError("the password must not contain your login")


def check_key_passphrase(passphrase: str) -> None:
    """S9: a passphrase a person types for a key file. Where ssh-keygen accepts '' and 5 characters."""
    if not passphrase or not passphrase.strip():
        raise PolicyError("an empty key passphrase is refused")
    if len(passphrase) < MIN_KEY_PASSPHRASE:
        raise PolicyError(f"a key passphrase must have at least {MIN_KEY_PASSPHRASE} characters")


def _part(value: str, what: str) -> str:
    if not _NAME_PART.match(value):
        raise GkError(f"{what} may only contain letters, digits, '.', '_' and '-'")
    return value


def key_name(platform: str = "", hostname: str = "", profile: str = "") -> str:
    """id_ed25519[_platform][_hostname][_profile], as genkey.sh named it."""
    platform = platform.lower()
    if platform and platform not in PLATFORMS:
        raise GkError(f"unsupported platform {platform!r}; one of {', '.join(PLATFORMS)}")
    parts = [platform, _part(hostname, "hostname"), _part(profile, "profile")]
    return "_".join(["id_ed25519", *[p for p in parts if p]])


def _public_line(private_pem: str) -> str:
    key = load_ssh_private_key(private_pem.encode(), password=None)
    return key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()


def fingerprint(public_line: str) -> str:
    """The SHA256 fingerprint ssh prints, from an OpenSSH public key line."""
    digest = hashlib.sha256(b64decode(public_line.split()[1])).digest()
    return "SHA256:" + b64encode(digest).decode().rstrip("=")


@dataclass(frozen=True, slots=True, repr=False)
class SshKey:
    """One ssh key, in the shape of atCGS's SshKey (C4).

    ``repo`` carries the key name (``id_ed25519_github_laptop_pro``) and ``role``
    the profile, so a key keeps its file name through the GLYPH. The private half
    is an unencrypted OpenSSH key held in memory only.
    """

    repo: str
    role: str
    private: str

    @classmethod
    def generate(cls, name: str, role: str = "") -> SshKey:
        pem = Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption())
        return cls(name, role, pem.decode())

    @property
    def public(self) -> str:
        return _public_line(self.private)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.public)

    def __repr__(self) -> str:
        return f"SshKey(repo={self.repo!r}, role={self.role!r})"


def inside_git_worktree(path: Path) -> bool:
    """S5: a GLYPH must never be written where git could add it."""
    for parent in [path.resolve(), *path.resolve().parents]:
        if (parent / ".git").exists():
            return True
    return False


def _write_private(path: Path, data: bytes, *, replace: bool = False) -> None:
    """Write with mode 0600 from the first byte; atomically when replacing (S5)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = path.with_name(path.name + ".tmp") if replace else path
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(target, path)
    except BaseException:
        if replace and target.exists():
            target.unlink()
        raise


class KeyGen:
    """A user's identity and everything made from it.

    >>> kg = KeyGen("me@x.org", password)          # derives once; nothing is stored
    >>> key = kg.ssh_key("github", "laptop", "pro")
    >>> kg.glyph_add(key); kg.write(key); kg.load_into_agent(key)
    """

    def __init__(self, login: str, password: str, profile: str | None = None, *,
                 env: Mapping[str, str] | None = None) -> None:
        self._env = os.environ if env is None else env
        profile = profile or self._env.get(PROFILE_ENV, "real")
        if profile not in KDF_PROFILES:
            raise GkError(f"{PROFILE_ENV} must be one of {sorted(KDF_PROFILES)}")
        if profile == "test":
            if self._env.get(ALLOW_TEST_ENV) != "1":
                raise GkError(f"the 'test' profile is for CI only; set {ALLOW_TEST_ENV}=1 to use it")
            warnings.warn("gk: the 'test' KDF profile is weak; never use it for real keys", RuntimeWarning, stacklevel=2)
        check_password(password, login)
        self.login, self.profile = login, profile
        self._seed = derive(login, password, profile)
        self._public = Ed25519PrivateKey.from_private_bytes(self._seed).public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw)

    # --- identity -------------------------------------------------------------

    @property
    def uid(self) -> str:
        return uid_of(self._public)

    @property
    def seed(self) -> bytes:
        """The IDSEED, for the shared test vectors (C6) and for atCGS. Treat as the password."""
        return self._seed

    def _hkdf(self, info: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(self._seed)

    def passphrase(self) -> str:
        """The passphrase of an exported key file: HKDF(IDSEED, "gk/passphrase/v1"), hex. Not the password (D1)."""
        return self._hkdf(PASSPHRASE_INFO).hex()

    def glyph_key(self) -> bytes:
        return self._hkdf(GLYPH_INFO)

    def __repr__(self) -> str:
        return f"KeyGen(uid={self.uid})"

    # --- keys -------------------------------------------------------------------

    def ssh_key(self, platform: str = "", hostname: str = "", profile: str = "") -> SshKey:
        return SshKey.generate(key_name(platform, hostname, profile), profile)

    @staticmethod
    def register_url(platform: str) -> str | None:
        return PLATFORMS[platform.lower()][1] if platform else None

    @staticmethod
    def test_command(platform: str) -> str | None:
        return f"ssh -T git@{PLATFORMS[platform.lower()][0]}" if platform else None

    @staticmethod
    def ssh_config(platform: str, key_path: str | Path) -> str:
        host = PLATFORMS[platform.lower()][0] if platform else "myserver"
        head = "" if platform else "# Generic SSH configuration example\n"
        hostname = host if platform else "example.org"
        user = "git" if platform else "myuser"
        return (f"{head}Host {host}\n    HostName {hostname}\n    User {user}\n"
                f"    IdentityFile {key_path}\n    IdentitiesOnly yes\n")

    # --- the ~/.ssh export (S1: optional; S9: a typed passphrase is checked) ---------

    def write(self, key: SshKey, ssh_dir: str | Path | None = None, *,
              passphrase: str | None = None, comment: str | None = None) -> Path:
        """Export ``key`` to ``ssh_dir`` (700), encrypted (600) with a public half (644). Never overwrites."""
        if passphrase is None:
            passphrase = self.passphrase()
        else:
            check_key_passphrase(passphrase)
        directory = Path(ssh_dir).expanduser() if ssh_dir else Path.home() / ".ssh"
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        path = directory / _part(key.repo, "key name")
        pub_path = path.with_name(path.name + ".pub")
        if path.exists() or pub_path.exists():
            raise GkError(f"an ssh key already exists: {path}")
        private = load_ssh_private_key(key.private.encode(), password=None).private_bytes(
            Encoding.PEM, PrivateFormat.OpenSSH, BestAvailableEncryption(passphrase.encode()))
        _write_private(path, private)
        pub_path.write_text(f"{key.public} {comment or self.login}\n", encoding="utf-8")
        os.chmod(pub_path, 0o644)
        return path

    # --- the agent (S4: nothing on disk) ----------------------------------------------

    def load_into_agent(self, key: SshKey, *, lifetime: int | None = None) -> None:
        """Pipe the key to ssh-agent through stdin. ``lifetime`` is ssh-add -t, in seconds."""
        sock = self._env.get("SSH_AUTH_SOCK")
        if not sock:
            raise GkError("no ssh-agent: run  eval \"$(ssh-agent -s)\"  first")
        if not shutil.which("ssh-add"):
            raise GkError("ssh-add was not found on PATH")
        command = ["ssh-add"] + (["-t", str(int(lifetime))] if lifetime else []) + ["-"]
        result = subprocess.run(command, input=key.private.encode(), capture_output=True,
                                env={**os.environ, "SSH_AUTH_SOCK": sock}, check=False)
        if result.returncode != 0:
            raise GkError("ssh-add refused the key: " + result.stderr.decode(errors="replace").strip()[:200])

    # --- the GLYPH (S1, S5) ------------------------------------------------------------

    def glyph_path(self) -> Path:
        base = self._env.get(GLYPHS_ENV)
        return (Path(base) if base else Path.home() / ".cgs" / ".glyph") / f"{self.uid}.glyph"

    def glyph_seal(self, keys: Sequence[SshKey]) -> bytes:
        """Seal ssh keys into an 8 192-byte GLYPH that atCGS opens; a fresh nonce each time."""
        payload = json.dumps([{"repo": k.repo, "role": k.role, "private": k.private} for k in keys]).encode()
        if _LENGTH.size + len(payload) > PLAINTEXT:
            raise GlyphError(f"{len(keys)} ssh keys do not fit in one GLYPH ({PLAINTEXT} bytes)")
        plaintext = _LENGTH.pack(len(payload)) + payload
        plaintext += bytes(PLAINTEXT - len(plaintext))
        nonce = os.urandom(NONCE)
        header = MAGIC + bytes([GLYPH_VERSION]) + nonce
        glyph = header + ChaCha20Poly1305(self.glyph_key()).encrypt(nonce, plaintext, header)
        assert len(glyph) == GLYPH_BYTES
        return glyph

    def glyph_open(self, glyph: bytes) -> list[SshKey]:
        """Open a GLYPH; a wrong password or a single changed bit is refused."""
        if len(glyph) != GLYPH_BYTES or glyph[:4] != MAGIC or glyph[4] != GLYPH_VERSION:
            raise GlyphError("not a GLYPH: wrong size, magic or version")
        header, nonce = glyph[:HEADER], glyph[5:HEADER]
        try:
            plaintext = ChaCha20Poly1305(self.glyph_key()).decrypt(nonce, glyph[HEADER:], header)
        except InvalidTag:
            raise GlyphError("the GLYPH does not open: wrong login/password, or the GLYPH was altered") from None
        (length,) = _LENGTH.unpack_from(plaintext)
        return [SshKey(e["repo"], e["role"], e["private"]) for e in json.loads(plaintext[4:4 + length])]

    def glyph_keys(self, path: str | Path | None = None) -> list[SshKey]:
        target = Path(path) if path else self.glyph_path()
        return self.glyph_open(target.read_bytes()) if target.exists() else []

    def glyph_add(self, key: SshKey, path: str | Path | None = None) -> Path:
        """Add ``key`` to this user's GLYPH, keeping one backup of the previous file (S5, S1)."""
        target = Path(path) if path else self.glyph_path()
        if inside_git_worktree(target.parent):
            raise GkError(f"refusing to write a GLYPH inside a git work tree: {target.parent}")
        existing = self.glyph_keys(target)
        if any(k.repo == key.repo for k in existing):
            raise GkError(f"the GLYPH already holds a key named {key.repo}")
        sealed = self.glyph_seal([*existing, key])
        if target.exists():
            backup = target.with_name(target.name + ".bak")
            shutil.copyfile(target, backup)
            os.chmod(backup, 0o600)
        _write_private(target, sealed, replace=True)
        return target

    def find(self, name: str | None = None, path: str | Path | None = None) -> list[SshKey]:
        keys = self.glyph_keys(path)
        return [k for k in keys if name is None or k.repo == name]
