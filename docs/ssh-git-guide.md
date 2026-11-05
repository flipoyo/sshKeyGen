# SSH and Git guide

*Created: 2026-11-05*

## Abstract — read this first

**What this document is.** A reference for using an SSH key with GitHub and
GitLab once [genkey.sh](../genkey.sh) has made it.

**Why it exists.** It used to be the body of the README. It is reference
material, not the quick start, so it lives here.

**Who it is for.** Users who have a key and want to configure, debug or switch
a repository to SSH. Start with the [README](../README.md) if you have no key yet.

```mermaid
graph LR
    R["README<br/>make a key"] --> G["this guide<br/>YOU ARE HERE<br/>register, configure, debug"]
```

---



## Register SSH key (manual)

Generate key:

```bash
./genkey.sh
```

List keys:

```bash
ls -al ~/.ssh
```

Display public key:

```bash
cat ~/.ssh/<key>.pub
```

Never share the private key.

---

## GitHub

Add key:

```text
GitHub -> Settings -> SSH and GPG keys -> New SSH key
```

Paste:

```text
~/.ssh/<key>.pub
```

Test:

```bash
ssh -T git@github.com
```

Expected:

```text
Hi <user>! You've successfully authenticated...
```

---

## GitLab

Add key:

```text
GitLab -> Preferences -> SSH Keys
```

Paste:

```text
~/.ssh/<key>.pub
```

Test:

```bash
ssh -T git@gitlab.com
```

Expected:

```text
Welcome to GitLab, @<user>!
```

---

## SSH config

Create:

```bash
nano ~/.ssh/config
```

GitHub:

```sshconfig
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/<github_key>
  IdentitiesOnly yes
```

GitLab:

```sshconfig
Host gitlab.com
  HostName gitlab.com
  User git
  IdentityFile ~/.ssh/<gitlab_key>
  IdentitiesOnly yes
```

Permissions:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/config
chmod 600 ~/.ssh/<key>
chmod 644 ~/.ssh/<key>.pub
```

---

## SSH agent

Start:

```bash
eval "$(ssh-agent -s)"
```

Clear agent:

```bash
ssh-add -D
```

Add key:

```bash
ssh-add ~/.ssh/<key>
```

List loaded keys:

```bash
ssh-add -l
```

Verbose debug:

```bash
ssh -vT git@github.com
```

---

## Convert existing repo from HTTPS to SSH

Check remote:

```bash
git remote -v
```

GitHub:

```bash
git remote set-url origin git@github.com:<account>/<repo>.git
```

GitLab:

```bash
git remote set-url origin git@gitlab.com:<group>/<repo>.git
```

Verify:

```bash
git remote -v
```

---

## Clone with SSH

GitHub:

```bash
git clone git@github.com:<account>/<repo>.git
```

GitLab:

```bash
git clone git@gitlab.com:<group>/<repo>.git
```

---

## Push

```bash
git push origin main
```

or:

```bash
git push -u origin <branch>
```

---

## Git identity

```bash
git config --global user.name "<name>"
git config --global user.email "<email>"
```

Not related to SSH authentication.

---

## Common failures

Wrong key used:

```bash
ssh-add -D
ssh-add ~/.ssh/<key>
```

Wrong remote:

```bash
git remote -v
```

Repo not found:

- wrong remote
- wrong account
- no repo access
- wrong SSH key

Debug:

```bash
ssh -vT git@github.com
```
