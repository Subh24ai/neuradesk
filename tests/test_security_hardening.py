"""Regression tests for vulnerabilities found in the pre-launch security probe."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _signup(client: TestClient, email: str, org: str = "Acme", password: str = "Password123!") -> str:
    """Register + verify, returning an access token."""
    with patch("api.auth.send_otp_email") as m:
        r = client.post("/auth/register", json={"email": email, "password": password,
                                                "first_name": "T", "last_name": "U", "org_name": org})
        assert r.status_code == 201, r.text
        otp = m.call_args[0][1]
    return client.post("/auth/verify-otp", json={"email": email.lower(), "otp": otp}).json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_email_is_case_insensitive(test_client) -> None:
    """'Ada@Corp.dev' and 'ada@corp.dev' are one account: no duplicate sign-up, login in any case."""
    _signup(test_client, "Ada@Corp.dev")
    dup = test_client.post("/auth/register", json={"email": "ADA@corp.dev", "password": "Password123!",
                                                   "first_name": "x", "last_name": "y", "org_name": "Dup"})
    assert dup.status_code == 409
    assert test_client.post("/auth/login", json={"email": "aDa@CORP.dev", "password": "Password123!"}).status_code == 200


def test_password_reset_signs_out_every_session(test_client) -> None:
    """Account recovery must cut off anyone else holding a session (e.g. a stolen token)."""
    _signup(test_client, "victim@corp.dev")
    stolen = test_client.post("/auth/login", json={"email": "victim@corp.dev", "password": "Password123!"}).json()["access_token"]
    with patch("api.auth.send_otp_email") as m:
        test_client.post("/auth/forgot-password", json={"email": "victim@corp.dev"})
        code = m.call_args[0][1]
    r = test_client.post("/auth/reset-password", json={"email": "victim@corp.dev", "otp": code, "new_password": "Recovered456!"})
    assert r.status_code == 200
    assert test_client.get("/auth/me", headers=_h(stolen)).status_code == 401
    assert test_client.get("/auth/me", headers=_h(r.json()["access_token"])).status_code == 200


def test_websocket_rejects_signed_out_token(test_client, db_engine, monkeypatch) -> None:
    """A logged-out token cannot open (or run) a ticket over the WebSocket."""
    from sqlalchemy.orm import sessionmaker

    import api.main as main_mod

    monkeypatch.setattr(main_mod, "SessionLocal", sessionmaker(bind=db_engine))  # WS uses the module session
    tok = _signup(test_client, "ws@corp.dev")
    tid = test_client.post("/tickets", json={"text": "hello"}, headers=_h(tok)).json()["ticket_id"]
    test_client.post("/auth/logout", headers=_h(tok))
    with test_client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"token": tok})
        assert ws.receive_json()["code"] == "WS_UNAUTHORIZED"


def test_notification_email_escapes_html() -> None:
    """Ticket/AI text is escaped in email HTML so it can't inject links or scripts."""
    from api.email import send_escalation_alert, send_ticket_notification

    evil = "<script>alert(1)</script><a href='http://evil'>click</a>"
    with patch("api.email._send") as s:
        send_ticket_notification("u@x.dev", "t1", "resolved", evil, None)
        send_ticket_notification("u@x.dev", "t1", "escalated", None, evil)
        send_escalation_alert("t1", evil, "tier-1-support", "HIGH", evil, "support@x.dev")
    for call in s.call_args_list:
        html = call[0][3]
        assert "<script>" not in html and "href='http://evil'" not in html


class TestMemberManagement:
    """Offboarding: deactivate/reactivate, role changes, and their guardrails."""

    def _org(self, client):
        admin = _signup(client, "boss@team.dev", org="Team")
        inv = client.post("/admin/invites", json={"expires_days": 7}, headers=_h(admin)).json()["code"]
        with patch("api.auth.send_otp_email") as m:
            client.post("/auth/register", json={"email": "emp@team.dev", "password": "Password123!",
                                                "first_name": "E", "last_name": "P", "invite_code": inv})
            otp = m.call_args[0][1]
        emp = client.post("/auth/verify-otp", json={"email": "emp@team.dev", "otp": otp}).json()["access_token"]
        emp_id = next(m["id"] for m in client.get("/orgs/members", headers=_h(admin)).json()["members"] if m["email"] == "emp@team.dev")
        return admin, emp, emp_id

    def test_deactivate_cuts_access_immediately_and_reactivate_restores(self, test_client) -> None:
        admin, emp, emp_id = self._org(test_client)
        r = test_client.patch(f"/orgs/members/{emp_id}", json={"is_active": False}, headers=_h(admin))
        assert r.status_code == 200 and r.json()["is_active"] is False
        me = test_client.get("/auth/me", headers=_h(emp))
        assert me.status_code == 403 and me.json()["detail"]["code"] == "ACCOUNT_DEACTIVATED"
        login = test_client.post("/auth/login", json={"email": "emp@team.dev", "password": "Password123!"})
        assert login.status_code == 403 and login.json()["detail"]["code"] == "ACCOUNT_DEACTIVATED"
        test_client.patch(f"/orgs/members/{emp_id}", json={"is_active": True}, headers=_h(admin))
        assert test_client.post("/auth/login", json={"email": "emp@team.dev", "password": "Password123!"}).status_code == 200

    def test_deactivated_user_cannot_reset_password_back_in(self, test_client) -> None:
        admin, _, emp_id = self._org(test_client)
        test_client.patch(f"/orgs/members/{emp_id}", json={"is_active": False}, headers=_h(admin))
        with patch("api.auth.send_otp_email") as m:
            test_client.post("/auth/forgot-password", json={"email": "emp@team.dev"})
            code = m.call_args[0][1]
        r = test_client.post("/auth/reset-password", json={"email": "emp@team.dev", "otp": code, "new_password": "Another789!"})
        assert r.status_code == 403

    def test_promote_and_guardrails(self, test_client) -> None:
        admin, emp, emp_id = self._org(test_client)
        boss_id = next(m["id"] for m in test_client.get("/orgs/members", headers=_h(admin)).json()["members"] if m["email"] == "boss@team.dev")
        # Cannot modify yourself.
        assert test_client.patch(f"/orgs/members/{boss_id}", json={"role": "member"}, headers=_h(admin)).json()["detail"]["code"] == "CANNOT_MODIFY_SELF"
        # Promote employee → admin; employee can now use admin APIs.
        assert test_client.patch(f"/orgs/members/{emp_id}", json={"role": "admin"}, headers=_h(admin)).status_code == 200
        assert test_client.get("/admin/stats", headers=_h(emp)).status_code == 200
        # Members cannot manage people.
        test_client.patch(f"/orgs/members/{emp_id}", json={"role": "member"}, headers=_h(admin))
        assert test_client.patch(f"/orgs/members/{boss_id}", json={"is_active": False}, headers=_h(emp)).status_code == 403

    def test_last_admin_cannot_be_removed(self, test_client) -> None:
        admin, emp, emp_id = self._org(test_client)
        test_client.patch(f"/orgs/members/{emp_id}", json={"role": "admin"}, headers=_h(admin))
        boss_id = next(m["id"] for m in test_client.get("/orgs/members", headers=_h(admin)).json()["members"] if m["email"] == "boss@team.dev")
        # emp (now admin) deactivates boss — allowed, emp remains an admin.
        assert test_client.patch(f"/orgs/members/{boss_id}", json={"is_active": False}, headers=_h(emp)).status_code == 200
        # emp is now the only active admin; nobody else can demote them, and they can't demote themselves.
        r = test_client.patch(f"/orgs/members/{emp_id}", json={"role": "member"}, headers=_h(emp))
        assert r.status_code == 400

    def test_cannot_manage_other_orgs_members(self, test_client) -> None:
        admin, _, emp_id = self._org(test_client)
        other = _signup(test_client, "boss@other.dev", org="Other")
        assert test_client.patch(f"/orgs/members/{emp_id}", json={"is_active": False}, headers=_h(other)).status_code == 404


def test_resend_otp_does_not_reveal_which_emails_exist(test_client) -> None:
    """Unknown, verified and pending accounts all get the same answer (no enumeration)."""
    _signup(test_client, "known@corp.dev")  # verified
    with patch("api.auth.send_otp_email"):
        test_client.post("/auth/register", json={"email": "pending@corp.dev", "password": "Password123!",
                                                 "first_name": "P", "last_name": "D", "org_name": "Pend"})
    with patch("api.auth.send_otp_email") as sent:
        unknown = test_client.post("/auth/resend-otp", json={"email": "nobody@corp.dev"})
        verified = test_client.post("/auth/resend-otp", json={"email": "known@corp.dev"})
        assert sent.call_count == 0  # nothing is emailed for those two
        pending = test_client.post("/auth/resend-otp", json={"email": "pending@corp.dev"})
        assert sent.call_count == 1
    assert unknown.status_code == verified.status_code == pending.status_code == 200
    assert unknown.json()["message"] == verified.json()["message"] == pending.json()["message"]


def test_deep_health_does_not_leak_error_details(test_client, monkeypatch) -> None:
    """A failing dependency reports 'error', never the exception text (hosts, paths, SQL)."""
    import api.main as main_mod

    def boom() -> None:
        raise RuntimeError("could not connect to db-host-10.0.0.5:5432 user=prod_admin")

    monkeypatch.setattr(main_mod, "SessionLocal", boom)
    r = test_client.get("/health/deep")
    assert r.status_code == 503
    assert "db-host" not in r.text and "prod_admin" not in r.text
    assert r.json()["detail"]["db"] == "error"


def test_login_server_fault_is_not_reported_as_bad_password(test_client) -> None:
    """If the database fails mid-login, the message must not read like a wrong password."""
    _signup(test_client, "fault@corp.dev")
    with patch("api.auth.verify_password", side_effect=RuntimeError("db gone")):
        r = test_client.post("/auth/login", json={"email": "fault@corp.dev", "password": "Password123!"})
    assert r.status_code == 500
    assert "not your password" in r.json()["detail"]["error"]
