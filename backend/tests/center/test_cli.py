import pytest
from sqlalchemy import select

from api.center import cli
from api.center.models import User
from tests.center.helpers import CREDS, STRONG, register


@pytest.fixture
def run(client):
    def run_test_cli(*argv, password=STRONG):
        return cli.main(list(argv), read_password=lambda: password, open_session=client.app.state.session_factory)

    return run_test_cli


def user_of(client) -> User:
    with client.app.state.session_factory() as db:
        return db.scalar(select(User))


def test_usage_on_bad_arguments(run, capsys):
    assert run() == 2 and run("explode", "alice") == 2 and run("promote") == 2
    assert "promote" in capsys.readouterr().out


def test_unknown_user(run, capsys):
    assert run("promote", "ghost") == 1
    assert "not found" in capsys.readouterr().out


def test_promote_then_demote(client, run):
    register(client)
    assert run("promote", "ALICE") == 0
    assert user_of(client).group == "admin"
    assert (user_of(client).token_version) == 0
    assert run("demote", "alice") == 0
    assert (user_of(client).group, user_of(client).token_version) == ("user", 1)


def test_promoted_role_reaches_the_jwt(client, run):
    from sn_shared import COOKIE_NAME, decode_token

    register(client)
    run("promote", "alice")
    client.cookies.clear()
    client.post("/auth/login", json=CREDS)
    assert decode_token(client.cookies.get(COOKIE_NAME)).group == "admin"


def test_reset_password_changes_it_and_revokes_sessions(client, run):
    register(client)
    old_access = client.cookies.get("sn_token")
    assert run("reset-password", "alice", password=STRONG) == 0
    client.cookies.set("sn_token", old_access, path="/")
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/auth/login", json=CREDS).status_code == 401
    assert client.post("/auth/login", json={**CREDS, "password": STRONG}).status_code == 200


def test_reset_password_enforces_the_policy(client, run, capsys):
    register(client)
    assert run("reset-password", "alice", password="short") == 1
    assert "at least 8" in capsys.readouterr().out
    assert client.post("/auth/login", json=CREDS).status_code == 200  # unchanged


def test_reset_password_gives_a_google_only_account_a_password(google_client, run):
    google_client.post("/auth/google", json={"id_token": "s1|gil@example.com"})
    assert run("reset-password", "gil") == 0
    assert google_client.post("/auth/login", json={"username": "gil", "password": STRONG}).status_code == 200


def test_password_reader_uses_stdin_when_not_a_tty(monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("piped-password-1\n"))
    assert cli.read_new_password() == "piped-password-1"


def test_password_reader_prompts_on_a_tty(monkeypatch):
    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", Tty())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "typed-password-1")
    assert cli.read_new_password() == "typed-password-1"


def test_default_session_opens_the_configured_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    assert cli.main(["promote", "nobody"]) == 1  # creates and upgrades the schema, then finds no user


def test_moderator_commands_and_set_role(client, run):
    register(client)
    assert run("moderate", "alice") == 0
    assert (user_of(client).group, user_of(client).token_version) == ("moderator", 0)
    assert run("promote", "alice") == 0 and user_of(client).group == "admin"
    assert run("set-group", "alice", "moderator") == 0
    assert (user_of(client).group, user_of(client).token_version) == ("moderator", 1)  # lowered: sessions revoked
    assert run("unmoderate", "alice") == 0
    assert (user_of(client).group, user_of(client).token_version) == ("user", 2)
    assert run("set-group", "alice", "root") == 2 and run("set-group", "alice") == 2
    assert user_of(client).group == "user"
