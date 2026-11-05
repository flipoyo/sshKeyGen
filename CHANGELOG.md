# Changelog

Versions follow [Semantic Versioning](https://semver.org). The version is written in
`pyproject.toml`, `pixi.toml` and `src/gk/keygen.py`; a test keeps the three equal.

## 0.2.0

The Bash script becomes the Python package `gk`.

- One class, `KeyGen`, and a thin `gk` command. `./genkey.sh` stays as a shim for one release.
- Identity is atCGS's, byte for byte: Argon2id, same salt, same costs. A shared
  `tests/vectors.toml` and a GLYPH that opens in both tools keep the two in step.
- Private keys live in the GLYPH. `~/.ssh/<key>` is an export, encrypted with a
  passphrase derived from your password (HKDF), not a bare `sha256`.
- `gk load` puts keys in the ssh-agent through stdin, with nothing written to disk.
- Password policy: 16 characters or more for the master password; 8 or more, typed twice,
  never empty, for a passphrase you choose for a key file.
- Codeberg now gets a config snippet and registration link.
- The password is read with `getpass` or `--password-fd`; never an argument, and never an
  environment value (stricter than the ticket's first draft, which allowed one).

## 0.1.0

`genkey.sh` with a README.
