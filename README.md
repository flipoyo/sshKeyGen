# sshKeyGen v0.1.0

*Created: 2026-10-30*

One command makes a named SSH key for a Git platform, loads it into your agent,
and tells you where to register it.

```mermaid
flowchart LR
    A["./genkey.sh<br/>email platform host profile"] --> B["~/.ssh/id_ed25519_…<br/>key pair, agent-loaded"]
    B --> C["paste the public key<br/>on the platform"]
    C --> D["ssh -T git@…<br/>works"]
```

## 1. Make a key

Needs Bash and OpenSSH. Clone, then run from the repository root:

```bash
./genkey.sh EMAIL [PLATFORM] [HOSTNAME] [PROFILE]
```

| Argument | Meaning | Example |
|---|---|---|
| `EMAIL` | required; written in the key as its comment | `me@x.org` |
| `PLATFORM` | `github`, `gitlab` or `codeberg`; leave empty for a generic key | `github` |
| `HOSTNAME` | the machine this key lives on | `laptop` |
| `PROFILE` | which identity: `perso`, `pro`, `admin`… | `pro` |

The key name is built from what you give:

```text
./genkey.sh me@x.org github laptop pro   ->  ~/.ssh/id_ed25519_github_laptop_pro
./genkey.sh me@x.org                     ->  ~/.ssh/id_ed25519
```

Check the version with `./genkey.sh --version`. Versions follow
[Semantic Versioning](https://semver.org); the number lives in `genkey.sh` and the README title.

Choose a passphrase when `ssh-keygen` asks. The script never overwrites an
existing key; it stops instead.

## 2. Tutorial: first push to GitHub

1. Make the key: `./genkey.sh me@x.org github laptop pro`
2. Copy the public key the script prints (it is also in `~/.ssh/<key>.pub`).
3. Register it: GitHub → Settings → SSH and GPG keys → New SSH key.
4. Append the printed `Host github.com` block to `~/.ssh/config`.
5. Test: `ssh -T git@github.com` should answer `Hi <user>! You've successfully authenticated`.
6. Use SSH remotes: `git clone git@github.com:<account>/<repo>.git`

GitLab is the same, with `https://gitlab.com/-/user_settings/ssh_keys` and
`ssh -T git@gitlab.com`.

## 3. Good to know

- **Codeberg** is accepted, but the script prints a generic config block and no
  registration link. Use `Host codeberg.org` and register at Codeberg → Settings → SSH keys.
- **One key per platform, machine and profile.** `IdentitiesOnly yes` in the config
  stops the wrong key being offered.
- **Never share the private key** (the file without `.pub`).
- Wrong key or "repository not found": see the [troubleshooting guide](docs/ssh-git-guide.md#common-failures).

## 4. Where to go next

- [docs/ssh-git-guide.md](docs/ssh-git-guide.md) — config, agent, HTTPS → SSH, clone, push, failures.
- Planned: a Python package `gk` with a class API and a passphrase derived from a declared secret
  ([issue #1](https://github.com/flipoyo/sshKeyGen/issues/1)). Not implemented yet.

## Authorship

- AUTH: Nicolas Flipo

## LLM assistance

Parts of this project were written with the help of large language models,
used as a paid service under the author's direction. They are acknowledged
here rather than credited as co-authors on commits, merges or pull requests.

Main assistance:
- **Claude** (Anthropic) — Claude Code with Claude Sonnet 5.5

Responsibility for everything in this repository rests under the license terms.

## License

Distributed under the [MIT License](LICENSE): free to use, modify and
redistribute, provided as is, without warranty or liability.
