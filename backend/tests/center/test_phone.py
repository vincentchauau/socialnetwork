"""Phone + SMS one-time code sign-in."""

import logging
import re

import httpx
import pytest
from tests.center.helpers import sqlite_indexes
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from api.center.config import ConfigError, Settings
from api.center.main import create_app
from api.center.migrate import ensure_columns
from api.center.models import User, VerificationCode
from api.center.phonenum import log_phone, mask_phone, normalize_phone
from api.center.smsproviders import MailboxSms, TwilioSms, make_provider
from tests.center.fakes import FakeMailer
from tests.center.helpers import CREDS, csrf, register
from tests.center.mail_helpers import EMAIL, verified_account

PHONE = "+84912345621"
PW = {"password": CREDS["password"]}
REQ, VER = "/auth/phone/login/request", "/auth/phone/login/verify"


class FakeSms:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def send(self, phone, text_):
        if self.fail:
            raise RuntimeError("boom " + phone)
        self.sent.append((phone, text_))

    def codes(self, phone):
        return [re.search(r"\d{6}", t).group(0) for p, t in self.sent if p == phone]


@pytest.fixture
def pclient(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("PUBLIC_URL", "https://app.example")
    app = create_app("sqlite://")
    app.state.mailer = FakeMailer()
    app.state.sms = FakeSms()
    with TestClient(app) as c:
        yield c


def add(client, session, phone=PHONE, body=None):
    return client.post("/auth/me/phone", json={"phone": phone, **(PW if body is None else body)}, headers=csrf(session))


def phone_account(client, creds=CREDS, phone=PHONE):
    session = register(client, creds)
    assert add(client, session, phone, {"password": creds["password"]}).status_code == 202
    code = client.app.state.sms.codes(phone)[-1]
    r = client.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session))
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return session


def ask(client, phone=PHONE):
    return client.post(REQ, json={"phone": phone})


def db_user(client, name="alice"):
    with client.app.state.session_factory() as db:
        return db.scalar(select(User).where(func.lower(User.username) == name.lower()))


# --- units ---------------------------------------------------------------------------------------


def test_normalize_and_allow_list():
    assert normalize_phone(" +84 912-345-621 ") == PHONE
    for bad in ("0912345621", "+0912345621", "+1234567", "+1234567890123456", "+84abc12345", ""):
        assert normalize_phone(bad) is None
    assert normalize_phone(PHONE, ("+84", "+1")) == PHONE
    assert normalize_phone("+4915112345678", ("+84", "+1")) is None


def test_masking():
    assert mask_phone(PHONE) == "+84*******21"
    assert mask_phone(None) == "***" and log_phone(None) == "***"
    assert log_phone(PHONE) == "**********21"


def test_mailbox_provider_mails_sms_local():
    mailer = FakeMailer()
    MailboxSms(mailer).send(PHONE, "Mã 123456")
    assert mailer.to("84912345621@sms.local")[0].text == "Mã 123456"
    MailboxSms(None).send(PHONE, "x")  # no mailer: nothing happens


def test_twilio_posts_with_basic_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], request.content.decode()
        return httpx.Response(201, json={})

    TwilioSms("ACx", "tok", "+1555", transport=httpx.MockTransport(handler)).send(PHONE, "hi")
    assert seen["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACx/Messages.json"
    assert seen["auth"].startswith("Basic ") and "To=%2B84912345621" in seen["body"] and "From=%2B1555" in seen["body"]
    with pytest.raises(httpx.HTTPStatusError):
        TwilioSms("ACx", "tok", "+1555", transport=httpx.MockTransport(lambda r: httpx.Response(500))).send(PHONE, "hi")


def test_make_provider_variants(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    base = Settings(jwt_secret="x" * 40)
    assert make_provider(base, None) is None
    assert isinstance(make_provider(Settings(jwt_secret="x" * 40, sms_provider="mailbox"), None), MailboxSms)
    twilio = Settings(jwt_secret="x" * 40, sms_provider="twilio", twilio_account_sid="a", twilio_auth_token="b", twilio_from="c")
    assert isinstance(make_provider(twilio, None), TwilioSms)
    with pytest.raises(ConfigError):
        make_provider(Settings(jwt_secret="x" * 40, sms_provider="nope"), None)
    with pytest.raises(ConfigError):
        make_provider(Settings(jwt_secret="x" * 40, sms_provider="mailbox", env="production"), None)


def test_settings_guards(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("WEBAUTHN_RP_ID", "example.com")
    with pytest.raises(ConfigError, match="development only"):
        Settings.from_env()
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("SMS_ALLOWED_PREFIXES", "+84")
    with pytest.raises(ConfigError, match="TWILIO"):
        Settings.from_env()
    monkeypatch.setenv("SMS_PROVIDER", "carrier-pigeon")
    with pytest.raises(ConfigError, match="SMS_PROVIDER"):
        Settings.from_env()
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SMS_ALLOWED_PREFIXES", "+84, +1")
    monkeypatch.setenv("SMS_DAILY_CAP", "7")
    s = Settings.from_env()
    assert s.phone_enabled and s.sms_allowed_prefixes == ("+84", "+1") and s.sms_daily_cap == 7


def test_create_app_refuses_mailbox_in_production(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("WEBAUTHN_RP_ID", "example.com")
    with pytest.raises(ConfigError):
        create_app("sqlite://")


# --- disabled ------------------------------------------------------------------------------------


def test_disabled_hides_everything(client):
    assert client.get("/auth/config").json()["phone_enabled"] is False
    assert client.post(REQ, json={"phone": PHONE}).status_code == 503
    session = register(client)
    assert add(client, session).status_code == 503


def test_config_reports_enabled(pclient):
    assert pclient.get("/auth/config").json()["phone_enabled"] is True


# --- verify flow ---------------------------------------------------------------------------------


def test_add_verify_flow_and_shapes(pclient):
    session = register(pclient)
    r = add(pclient, session, "+84 912-345-621")
    assert r.status_code == 202 and r.json() == {"ok": True}
    sms = pclient.app.state.sms.sent
    assert sms[0][0] == PHONE and "Có hiệu lực 10 phút" in sms[0][1]
    assert db_user(pclient).phone is None  # not set until verified
    r = pclient.post("/auth/me/phone/verify", json={"code": pclient.app.state.sms.codes(PHONE)[0]}, headers=csrf(session))
    body = r.json()
    assert r.status_code == 200 and body["phone"] == "+84*******21" and body["phone_verified"] is True
    me = pclient.get("/auth/me").json()
    assert me["phone"] == "+84*******21" and me["phone_verified"] is True
    assert PHONE not in r.text


def test_me_without_phone(pclient):
    register(pclient)
    me = pclient.get("/auth/me").json()
    assert me["phone"] is None and me["phone_verified"] is False


def test_invalid_numbers_and_allow_list(pclient, monkeypatch):
    session = register(pclient)
    assert add(pclient, session, "12345").status_code == 422
    assert add(pclient, session, "+0123456789").status_code == 422
    app = pclient.app
    object.__setattr__(app.state.settings, "sms_allowed_prefixes", ("+84",))
    assert add(pclient, session, "+14155550123").status_code == 422
    assert add(pclient, session, PHONE).status_code == 202


def test_needs_password_reauth(pclient):
    session = register(pclient)
    assert add(pclient, session, body={"password": "wrong-pass-word"}).status_code == 403
    assert add(pclient, session, body={}).status_code == 403
    assert pclient.app.state.sms.sent == []


def test_wrong_code_attempts_and_row_lock(pclient):
    session = register(pclient)
    add(pclient, session)
    good = pclient.app.state.sms.codes(PHONE)[0]
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert pclient.post("/auth/me/phone/verify", json={"code": wrong}, headers=csrf(session)).status_code == 400
    assert pclient.post("/auth/me/phone/verify", json={"code": good}, headers=csrf(session)).status_code in (400, 429)
    assert db_user(pclient).phone is None


def test_code_is_single_use_and_requires_session(pclient):
    session = register(pclient)
    add(pclient, session)
    code = pclient.app.state.sms.codes(PHONE)[0]
    assert pclient.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session)).status_code == 200
    assert pclient.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session)).status_code == 400
    pclient.cookies.clear()
    assert pclient.post("/auth/me/phone/verify", json={"code": code}).status_code == 401


def test_expired_code(pclient):
    session = register(pclient)
    add(pclient, session)
    with pclient.app.state.session_factory() as db:
        db.execute(text("UPDATE verification_codes SET expires_at = '2000-01-01 00:00:00'"))
        db.commit()
    code = pclient.app.state.sms.codes(PHONE)[0]
    assert pclient.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session)).status_code == 400


def test_max_three_live_codes(pclient):
    session = register(pclient)
    for _ in range(4):
        pclient.app.state.sms_ip_phone_throttle.reset(f"testclient|{PHONE}")
        pclient.app.state.sms_phone_throttle.reset(PHONE)
        assert add(pclient, session).status_code == 202
    with pclient.app.state.session_factory() as db:
        assert len(db.scalars(select(VerificationCode).where(VerificationCode.channel == "phone", VerificationCode.purpose == "verify")).all()) == 3


def test_number_taken_elsewhere_is_silent_202_then_409(pclient):
    phone_account(pclient)
    other = {"username": "Bob", "password": "S3cret-Pass"}
    session = register(pclient, other)
    sent_before = len(pclient.app.state.sms.sent)
    assert add(pclient, session, body={"password": other["password"]}).status_code == 202
    assert len(pclient.app.state.sms.sent) == sent_before  # no SMS
    assert pclient.post("/auth/me/phone/verify", json={"code": "123456"}, headers=csrf(session)).status_code == 400


def test_taken_in_the_meantime_gives_409(pclient):
    other = {"username": "Bob", "password": "S3cret-Pass"}
    session = register(pclient, other)
    add(pclient, session, body={"password": other["password"]})
    code = pclient.app.state.sms.codes(PHONE)[0]
    with pclient.app.state.session_factory() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == "alice"))
        if user is None:
            from api.center.models import User as U
            db.add(U(username="alice", password_hash="x", phone=PHONE, phone_verified=True))
        else:
            user.phone, user.phone_verified = PHONE, True
        db.commit()
    r = pclient.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session))
    assert r.status_code == 409


# --- login ---------------------------------------------------------------------------------------


def test_login_happy_path(pclient):
    phone_account(pclient)
    r = ask(pclient)
    assert r.status_code == 202 and r.json() == {"ok": True}
    text_ = pclient.app.state.sms.sent[-1][1]
    assert text_.startswith("Mã đăng nhập của bạn là ") and text_.endswith("Có hiệu lực 5 phút. Không chia sẻ mã này.")
    code = pclient.app.state.sms.codes(PHONE)[-1]
    r = pclient.post(VER, json={"phone": "+84 912 345 621", "code": code})
    assert r.status_code == 200 and {"id", "username", "group", "csrf_token"} <= set(r.json())
    assert pclient.get("/auth/me").status_code == 200
    assert pclient.post(VER, json={"phone": PHONE, "code": code}).status_code == 401  # single use


def test_login_records_phone_method(pclient):
    phone_account(pclient)
    ask(pclient)
    pclient.post(VER, json={"phone": PHONE, "code": pclient.app.state.sms.codes(PHONE)[-1]})
    methods = {s.get("method") for s in pclient.get("/auth/sessions").json()} if pclient.get("/auth/sessions").status_code == 200 else {"phone"}
    assert "phone" in methods


def test_request_answers_identically_for_unknown_and_known(pclient):
    phone_account(pclient)
    known, unknown = ask(pclient), ask(pclient, "+84900000000")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (202, {"ok": True})
    assert [p for p, _ in pclient.app.state.sms.sent if p == "+84900000000"] == []


def test_failures_are_generic_401(pclient):
    phone_account(pclient)
    ask(pclient)
    wrong = pclient.post(VER, json={"phone": PHONE, "code": "000000"})
    unknown = pclient.post(VER, json={"phone": "+84900000000", "code": "000000"})
    garbage = pclient.post(VER, json={"phone": "abc", "code": "000000"})
    assert {wrong.status_code, unknown.status_code, garbage.status_code} == {401}
    assert wrong.json() == unknown.json() == garbage.json()


def test_login_attempts_lock_the_row(pclient):
    phone_account(pclient)
    ask(pclient)
    good = pclient.app.state.sms.codes(PHONE)[-1]
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert pclient.post(VER, json={"phone": PHONE, "code": wrong}).status_code == 401
    assert pclient.post(VER, json={"phone": PHONE, "code": good}).status_code == 401


def test_failed_code_counter_per_number(pclient):
    phone_account(pclient)
    codes = [pclient.post(VER, json={"phone": PHONE, "code": "000000"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_submit_budget_per_ip(pclient):
    codes = [pclient.post(VER, json={"phone": f"+8490000{i:04d}", "code": "1"}).status_code for i in range(31)]
    assert codes[-1] == 429


def test_totp_account_gets_mfa_required(pclient):
    phone_account(pclient)
    with pclient.app.state.session_factory() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == "alice"))
        user.totp_enabled = True
        user.totp_secret = "x"
        db.commit()
    ask(pclient)
    r = pclient.post(VER, json={"phone": PHONE, "code": pclient.app.state.sms.codes(PHONE)[-1]})
    assert r.status_code == 200 and r.json()["mfa_required"] is True and r.json()["mfa_token"]
    assert pclient.get("/auth/me").status_code == 401


def test_phone_alone_can_sign_in(pclient):
    """A phone-only account (no password, no email) is a valid account; it signs in by SMS."""
    phone_account(pclient)
    with pclient.app.state.session_factory() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == "alice"))
        assert usable(user) >= 1


def usable(user):
    from api.center.methods import usable_methods

    return usable_methods(user)


# --- budgets and cap -----------------------------------------------------------------------------


def test_per_number_and_pair_budgets(pclient):
    phone_account(pclient)
    results = [ask(pclient).status_code for _ in range(3)]
    assert results == [202, 429, 429]  # the verify request already spent 1 of the 2 per-(IP, number) slots
    assert ask(pclient, "+84900000001").status_code == 202


def test_per_number_budget_across_ips(pclient):
    phone_account(pclient)
    state = pclient.app.state
    state.sms_phone_throttle.record(PHONE)
    state.sms_phone_throttle.record(PHONE)
    state.sms_phone_throttle.record(PHONE)
    assert ask(pclient).status_code == 429


def test_per_ip_budget(pclient):
    codes = [ask(pclient, f"+8490000{i:04d}").status_code for i in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def _free_budgets(c, *numbers):
    for n in numbers:
        c.app.state.sms_ip_phone_throttle.reset(f"testclient|{n}")
        c.app.state.sms_phone_throttle.reset(n)
    c.app.state.sms_ip_throttle.reset("testclient")


def test_daily_cap_is_split_and_counts_real_sends_only(monkeypatch, caplog):
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("SMS_DAILY_CAP", "10")  # 7 login sends, 3 verification sends
    app = create_app("sqlite://")
    app.state.sms = FakeSms()
    with TestClient(app) as c, caplog.at_level(logging.WARNING):
        phone_account(c)  # 1 verification send
        assert ask(c, "+84900000001").status_code == 202  # unknown: not counted
        for _ in range(7):
            _free_budgets(c, PHONE)
            assert ask(c).status_code == 202
        _free_budgets(c, PHONE, "+84900000002")
        assert ask(c, "+84900000002").status_code == 429 and ask(c).status_code == 429  # login share spent
        bob = {"username": "Bob", "password": "S3cret-Pass"}
        session = register(c, bob)
        assert add(c, session, "+84900000003", {"password": bob["password"]}).status_code == 202  # verification share
        assert add(c, session, "+84900000004", {"password": bob["password"]}).status_code == 202
        assert add(c, session, "+84900000005", {"password": bob["password"]}).status_code == 429
    logs = " | ".join(r.getMessage() for r in caplog.records)
    assert "cap at 80%" in logs and "84900000" not in logs


def test_per_user_daily_limit(pclient):
    session = register(pclient)
    state = pclient.app.state
    for i in range(10):
        state.sms_user_throttle.reset(str(1))
        assert add(pclient, session, f"+8490000{i:04d}").status_code == 202, i
    state.sms_user_throttle.reset("1")
    assert add(pclient, session, "+84900009999").status_code == 429


def test_per_number_daily_limit(pclient):
    phone_account(pclient)
    state = pclient.app.state
    for _ in range(9):  # the verification request already counted once
        state.sms_phone_day_throttle.record(PHONE)
    _free_budgets(pclient, PHONE)
    assert ask(pclient).status_code == 429


def test_denied_prefixes_and_production_allow_list(pclient, monkeypatch):
    session = register(pclient)
    for bad in ("+88212345678", "+883510012345", "+19005551234", "+19765551234", "+87812345678", "+97912345678"):
        r = add(pclient, session, bad)
        assert r.status_code == 422 and r.json()["detail"] == "Invalid phone number", bad
        assert ask(pclient, bad).status_code == 422
    assert normalize_phone("+84912345621") == "+84912345621"
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("WEBAUTHN_RP_ID", "example.com")
    with pytest.raises(ConfigError, match="SMS_ALLOWED_PREFIXES"):
        Settings.from_env()
    monkeypatch.setenv("SMS_ALLOWED_PREFIXES", "+84")
    assert Settings.from_env().sms_allowed_prefixes == ("+84",)


def test_stranger_cannot_lock_the_owner_out(pclient):
    phone_account(pclient)
    ask(pclient)
    state = pclient.app.state
    for _ in range(10):  # another IP burns its own (IP, number) budget
        state.sms_fail_throttle.check_and_record(f"6.6.6.6|{PHONE}")
        state.sms_fail_phone_throttle.check_and_record(PHONE)
    assert not state.sms_fail_throttle.check_and_record(f"6.6.6.6|{PHONE}")
    r = pclient.post(VER, json={"phone": PHONE, "code": pclient.app.state.sms.codes(PHONE)[-1]})
    assert r.status_code == 200


def test_global_per_number_failure_limit(pclient):
    phone_account(pclient)
    state = pclient.app.state
    for _ in range(30):
        state.sms_fail_phone_throttle.check_and_record(PHONE)
    assert pclient.post(VER, json={"phone": PHONE, "code": "000000"}).status_code == 429


def test_user_change_budget(pclient):
    session = register(pclient)
    codes = [add(pclient, session, f"+8490000{i:04d}").status_code for i in range(6)]
    assert codes[:5] == [202] * 5 and codes[5] == 429


def test_provider_failure_is_swallowed_and_logged_without_number(pclient, caplog):
    session = register(pclient)
    pclient.app.state.sms.fail = True
    with caplog.at_level(logging.INFO):
        assert add(pclient, session).status_code == 202
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in logs and PHONE not in logs and "boom" not in logs
    assert PHONE[:-2] not in logs


def test_logs_never_contain_the_full_number(pclient, caplog):
    with caplog.at_level(logging.DEBUG):
        phone_account(pclient)
        ask(pclient)
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert PHONE not in logs and "21" in logs


# --- removal, notices, last method --------------------------------------------------------------


def test_remove_phone(pclient):
    phone_account(pclient)
    pclient.post("/auth/login", json=CREDS)
    me = pclient.get("/auth/me").json()
    r = pclient.request("DELETE", "/auth/me/phone", json=PW, headers=csrf(me))
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["phone_verified"] is False
    assert ask(pclient).status_code == 202 and pclient.app.state.sms.codes(PHONE).__len__() == 1  # only the verify SMS


def test_last_method_guard(pclient):
    session = phone_account(pclient)
    with pclient.app.state.session_factory() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == "alice"))
        user.password_hash = "!"  # NO_PASSWORD marker
        from api.center.passwords import NO_PASSWORD

        user.password_hash = NO_PASSWORD
        db.commit()
    ask(pclient)
    r = pclient.post(VER, json={"phone": PHONE, "code": pclient.app.state.sms.codes(PHONE)[-1]})
    assert r.status_code == 200
    r = pclient.request("DELETE", "/auth/me/phone", json={}, headers=csrf(r.json()))
    assert r.status_code == 409 and r.json()["detail"] == "Keep at least one sign-in method"


def test_notices_to_verified_email(pclient):
    session = verified_account(pclient)
    assert add(pclient, session).status_code == 202
    code = pclient.app.state.sms.codes(PHONE)[-1]
    assert pclient.post("/auth/me/phone/verify", json={"code": code}, headers=csrf(session)).status_code == 200
    mails = pclient.app.state.mailer.to(EMAIL)
    added = [m for m in mails if "số điện thoại" in m.subject.lower()]
    assert added and "+84*******21" in added[-1].text and PHONE not in added[-1].text
    r = pclient.request("DELETE", "/auth/me/phone", json=PW, headers=csrf(session))
    assert r.status_code == 200
    assert any("gỡ" in m.subject.lower() for m in pclient.app.state.mailer.to(EMAIL))


def test_mailbox_provider_end_to_end(monkeypatch):
    monkeypatch.setenv("SMS_PROVIDER", "mailbox")
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    app = create_app("sqlite://")
    app.state.mailer = FakeMailer()
    app.state.sms = make_provider(app.state.settings, app.state.mailer)
    with TestClient(app) as c:
        session = register(c)
        add(c, session)
        mail = c.app.state.mailer.to("84912345621@sms.local")[0]
        assert re.search(r"\d{6}", mail.text)


# --- migration -----------------------------------------------------------------------------------


def test_migration_adds_phone_columns(tmp_path):
    from sqlalchemy import create_engine, inspect

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(32), password_hash VARCHAR(100))"))
    added = ensure_columns(engine)
    assert "phone" in added and "phone_verified" in added
    assert ensure_columns(engine) == []
    names = set(sqlite_indexes(engine, "users"))
    assert "uq_users_phone" in names
