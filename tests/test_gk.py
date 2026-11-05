import os
import re
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import pytest

import gk
from gk import GkError, GlyphError, KeyGen, PolicyError, check_key_passphrase, check_password, key_name
from gk.keygen import GLYPH_BYTES
from tests.conftest import LOGIN, PASSWORD, agent_keys

ROOT = Path(__file__).resolve().parent.parent


def snapshot(root: Path) -> set[Path]:
    return {p for p in root.rglob("*")}


# --- naming (as genkey.sh) -----------------------------------------------------

def test_key_names_match_genkey_sh():
    assert key_name("github", "workstation", "pro") == "id_ed25519_github_workstation_pro"
    assert key_name() == "id_ed25519"
    assert key_name("GitLab", "", "admin") == "id_ed25519_gitlab_admin"


@pytest.mark.parametrize("bad", [("nope", "", ""), ("github", "../x", ""), ("github", "a b", ""), ("", "", "p/q")])
def test_bad_name_parts_refused(bad):
    with pytest.raises(GkError):
        key_name(*bad)


def test_codeberg_has_snippet_and_url(kg):
    assert "Host codeberg.org" in kg.ssh_config("codeberg", "/k")
    assert kg.register_url("codeberg").startswith("https://codeberg.org/")
    assert kg.test_command("gitlab") == "ssh -T git@gitlab.com"


# --- S3: master password; test profile gating ---------------------------------------

@pytest.mark.parametrize("pw", ["short", "x" * 15, "passwordpassword", "aaaaaaaaaaaaaaaaaaaa"])
def test_weak_passwords_refused(pw):
    with pytest.raises(PolicyError):
        check_password(pw, LOGIN)


def test_password_may_not_contain_login():
    with pytest.raises(PolicyError):
        check_password("my-name-is-jonathan-and-more", "jonathan@x.org")


def test_policy_error_never_echoes_the_password():
    with pytest.raises(PolicyError) as error:
        check_password("Sup3rSecret", LOGIN)
    assert "Sup3rSecret" not in str(error.value)


def test_test_profile_needs_explicit_env(monkeypatch):
    monkeypatch.delenv("GK_ALLOW_TEST_PROFILE")
    with pytest.raises(GkError, match="CI only"):
        KeyGen(LOGIN, PASSWORD)


def test_test_profile_warns(monkeypatch):
    with pytest.warns(RuntimeWarning, match="weak"):
        KeyGen(LOGIN, PASSWORD)


# --- S9: typed key-file passphrase ------------------------------------------------------

@pytest.mark.parametrize("pw", ["", "   ", "1234567"])
def test_typed_passphrase_floor(pw):
    with pytest.raises(PolicyError):
        check_key_passphrase(pw)


def test_typed_passphrase_of_eight_is_accepted():
    check_key_passphrase("12345678")


def test_write_refuses_a_weak_typed_passphrase(kg, tmp_path):
    with pytest.raises(PolicyError):
        kg.write(kg.ssh_key("github"), tmp_path / ".ssh", passphrase="short")
    assert not (tmp_path / ".ssh" / "id_ed25519_github").exists()


# --- C1, C6: the shared vectors; the same login+password is the same identity ----------

def test_vectors_are_stable():
    vectors = tomllib.loads((ROOT / "tests" / "vectors.toml").read_text())
    for v in vectors["vector"]:
        seed = gk.derive(v["login"], v["password"], v["profile"])
        assert seed.hex() == v["idseed"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            assert KeyGen(v["login"], v["password"], v["profile"]).uid == v["uid"]


def test_same_login_and_password_same_uid_anywhere(kg):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        assert KeyGen(LOGIN, PASSWORD).uid == kg.uid
        assert KeyGen("other@x.org", PASSWORD).uid != kg.uid


def test_nfc_normalisation_is_part_of_the_contract():
    assert gk.derive("é", "x" * 20, "test") == gk.derive("é", "x" * 20, "test")


def test_purposes_are_domain_separated(kg):
    assert kg.passphrase() != kg.glyph_key().hex() and kg.passphrase() != kg.seed.hex()


# --- the key file export ---------------------------------------------------------------------

def test_write_makes_an_encrypted_key_with_modes(kg, tmp_path):
    key = kg.ssh_key("github", "laptop", "pro")
    path = kg.write(key, tmp_path / ".ssh")
    assert path.name == "id_ed25519_github_laptop_pro"
    assert (path.parent.stat().st_mode & 0o777) == 0o700 and (path.stat().st_mode & 0o777) == 0o600
    assert (path.with_name(path.name + ".pub").stat().st_mode & 0o777) == 0o644
    assert key.private not in path.read_text()
    no = subprocess.run(["ssh-keygen", "-y", "-P", "wrong", "-f", str(path)], capture_output=True, check=False)
    ok = subprocess.run(["ssh-keygen", "-y", "-P", kg.passphrase(), "-f", str(path)], capture_output=True, text=True, check=False)
    assert no.returncode != 0 and ok.returncode == 0 and ok.stdout.split()[1] == key.public.split()[1]


def test_write_never_overwrites(kg, tmp_path):
    key = kg.ssh_key("github")
    kg.write(key, tmp_path / ".ssh")
    with pytest.raises(GkError, match="already exists"):
        kg.write(key, tmp_path / ".ssh")


def test_a_typed_passphrase_opens_the_file(kg, tmp_path):
    key = kg.ssh_key()
    path = kg.write(key, tmp_path / ".ssh", passphrase="twelve chars!")
    ok = subprocess.run(["ssh-keygen", "-y", "-P", "twelve chars!", "-f", str(path)], capture_output=True, check=False)
    assert ok.returncode == 0


# --- S1, S5, S8: the GLYPH ---------------------------------------------------------------------

def test_glyph_roundtrip_and_size(kg):
    key = kg.ssh_key("github", "a", "b")
    sealed = kg.glyph_seal([key])
    assert len(sealed) == GLYPH_BYTES == 8192
    (back,) = kg.glyph_open(sealed)
    assert (back.repo, back.role, back.private) == (key.repo, key.role, key.private)


def test_glyph_hides_the_private_key(kg):
    key = kg.ssh_key()
    sealed = kg.glyph_seal([key])
    body = key.private.split("\n")[1].encode()
    assert body not in sealed and b"OPENSSH" not in sealed


def test_two_glyphs_of_one_user_differ(kg):
    key = kg.ssh_key()
    assert kg.glyph_seal([key]) != kg.glyph_seal([key])


def test_flipped_bit_is_refused(kg):
    sealed = bytearray(kg.glyph_seal([kg.ssh_key()]))
    sealed[200] ^= 1
    with pytest.raises(GlyphError):
        kg.glyph_open(bytes(sealed))


def test_wrong_password_is_refused(kg):
    sealed = kg.glyph_seal([kg.ssh_key()])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        other = KeyGen(LOGIN, PASSWORD + " but different")
    with pytest.raises(GlyphError):
        other.glyph_open(sealed)


def test_glyph_capacity_is_reported(kg):
    keys = [kg.ssh_key("github", f"h{i}") for i in range(40)]
    with pytest.raises(GlyphError, match="do not fit"):
        kg.glyph_seal(keys)


def test_glyph_add_modes_backup_and_duplicates(kg, tmp_path):
    path = kg.glyph_add(kg.ssh_key("github", "a"))
    assert (path.stat().st_mode & 0o777) == 0o600 and (path.parent.stat().st_mode & 0o777) == 0o700
    kg.glyph_add(kg.ssh_key("gitlab", "a"))
    assert path.with_name(path.name + ".bak").exists()
    assert {k.repo for k in kg.glyph_keys()} == {"id_ed25519_github_a", "id_ed25519_gitlab_a"}
    with pytest.raises(GkError, match="already holds"):
        kg.glyph_add(kg.ssh_key("github", "a"))


def test_glyph_refused_inside_a_git_work_tree(kg, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(GkError, match="git work tree"):
        kg.glyph_add(kg.ssh_key(), repo / "x.glyph")


# --- S4: the agent, nothing on disk -------------------------------------------------------------------

def test_load_into_agent_writes_nothing(kg, agent, isolated, tmp_path):
    key = kg.ssh_key("github", "tmp")
    before = snapshot(isolated)
    kg.load_into_agent(key, lifetime=60)
    assert snapshot(isolated) == before
    (line,) = agent_keys(agent)
    assert key.fingerprint in line


def test_no_agent_is_a_clear_error(kg):
    with pytest.raises(GkError, match="no ssh-agent"):
        kg.load_into_agent(kg.ssh_key())


# --- S6: the secret leaves no trace ------------------------------------------------------------------------

def run_cli(args, password, env, extra_input=""):
    read, write = os.pipe()
    os.write(write, (password + "\n").encode())
    os.close(write)
    result = subprocess.run([sys.executable, "-m", "gk", *args, "--password-fd", str(read)], capture_output=True,
                            text=True, env=env, pass_fds=(read,), cwd=ROOT, input=extra_input, check=False)
    os.close(read)
    return result


@pytest.fixture
def cli_env(isolated, tmp_path, agent):
    return {**os.environ, "PYTHONPATH": str(ROOT / "src"), "HOME": str(isolated)}


def test_classic_create_gives_key_glyph_and_agent_entry(cli_env, isolated, agent):
    result = run_cli(["me@x.org", "github", "laptop", "pro", "--no-agent"], PASSWORD, cli_env)
    assert result.returncode == 0, result.stderr
    assert (isolated / ".ssh" / "id_ed25519_github_laptop_pro").exists()
    assert "Host github.com" in result.stdout and "github.com/settings/keys" in result.stdout
    assert PASSWORD not in result.stdout + result.stderr


def test_cli_secret_not_in_argv_and_not_in_output(cli_env):
    result = run_cli(["me@x.org", "--no-export", "--no-agent"], PASSWORD, cli_env)
    assert result.returncode == 0, result.stderr
    assert PASSWORD not in result.stdout + result.stderr


def test_cli_has_no_password_argument():
    from gk.cli import _parser

    flags = " ".join(a.option_strings[0] for sp in _parser()._subparsers._group_actions[0].choices.values()
                     for a in sp._actions if a.option_strings)
    assert "--password " not in flags + " " and "--password-fd" in flags


def test_weak_cli_password_is_refused(cli_env):
    result = run_cli(["me@x.org"], "short", cli_env)
    assert result.returncode == 1 and "at least 16" in result.stderr


def test_load_then_list_from_glyph_only(cli_env, isolated, agent):
    assert run_cli(["me@x.org", "github", "a", "--no-export", "--no-agent"], PASSWORD, cli_env).returncode == 0
    ssh_before = snapshot(isolated)
    result = run_cli(["load", "me@x.org"], PASSWORD, cli_env)
    assert result.returncode == 0, result.stderr
    assert snapshot(isolated) == ssh_before
    assert len(agent_keys(agent)) == 1
    listed = run_cli(["list", "me@x.org"], PASSWORD, cli_env)
    assert "id_ed25519_github_a" in listed.stdout


def test_passphrase_command_matches_the_class(cli_env, kg):
    result = run_cli(["passphrase", "me@x.org"], PASSWORD, cli_env)
    assert result.stdout.strip() == kg.passphrase()


# --- versions agree ---------------------------------------------------------------------------------------------

def test_version_is_single_sourced():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    pixi = tomllib.loads((ROOT / "pixi.toml").read_text())["workspace"]["version"]
    assert gk.__version__ == py == pixi
    assert re.fullmatch(r"\d+\.\d+\.\d+", gk.__version__)
