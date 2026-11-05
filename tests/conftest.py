"""Every test runs in a temporary HOME with its own ssh-agent: the suite never touches the real one."""

import os
import shutil
import subprocess
import tempfile

import pytest

PASSWORD = "correct horse battery staple 42"  # 16+ characters, not on the common list
LOGIN = "me@x.org"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ATCGS_KDF_PROFILE", "test")
    monkeypatch.setenv("GK_ALLOW_TEST_PROFILE", "1")
    monkeypatch.setenv("ATCGS_GLYPHS", str(tmp_path / "glyphs"))
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    monkeypatch.delenv("SSH_AGENT_PID", raising=False)
    return home


@pytest.fixture
def agent(monkeypatch):
    """A private ssh-agent, killed at the end of the test."""
    if not shutil.which("ssh-agent"):
        pytest.skip("ssh-agent not available")
    sockdir = tempfile.mkdtemp(prefix="gk-", dir="/tmp")  # short: a socket path is limited to ~100 bytes
    sock = os.path.join(sockdir, "agent")
    out = subprocess.run(["ssh-agent", "-a", sock, "-s"], capture_output=True, text=True, check=True).stdout
    pid = next(p for p in out.split(";") if "SSH_AGENT_PID=" in p).split("=")[1]
    monkeypatch.setenv("SSH_AUTH_SOCK", sock)
    yield sock
    subprocess.run(["kill", pid], check=False)
    shutil.rmtree(sockdir, ignore_errors=True)


@pytest.fixture
def kg():
    import warnings

    from gk import KeyGen

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return KeyGen(LOGIN, PASSWORD)


def agent_keys(sock):
    result = subprocess.run(["ssh-add", "-l"], env={**os.environ, "SSH_AUTH_SOCK": sock},
                            capture_output=True, text=True, check=False)
    return [] if result.returncode != 0 else result.stdout.strip().splitlines()
