"""Tests for FastAPI routes — auth endpoints, ticket CRUD, and access control."""

from unittest.mock import patch


def _register_and_verify(
    client, email: str, password: str, org_name: str = "Test Org"
) -> str:
    """Register a user (new org → admin role), complete OTP, return token."""
    with patch("api.auth.send_otp_email") as mock_email:
        r = client.post("/auth/register", json={"email": email, "password": password, "first_name": "Test", "last_name": "User", "org_name": org_name})
        assert r.status_code == 201, f"register failed: {r.text}"
        otp = mock_email.call_args[0][1]  # second positional arg to send_otp_email

    r = client.post("/auth/verify-otp", json={"email": email, "otp": otp})
    assert r.status_code == 200, f"verify-otp failed: {r.text}"
    return r.json()["access_token"]


def _register_member(client, admin_token: str, email: str, password: str) -> str:
    """Join an existing org as a member (non-admin) and return a verified token."""
    r = client.post(
        "/admin/invites",
        json={"expires_days": 7},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201, f"invite creation failed: {r.text}"
    invite_code = r.json()["code"]

    with patch("api.auth.send_otp_email") as mock_email:
        r = client.post("/auth/register", json={"email": email, "password": password, "first_name": "Test", "last_name": "User", "invite_code": invite_code})
        assert r.status_code == 201, f"member register failed: {r.text}"
        otp = mock_email.call_args[0][1]

    r = client.post("/auth/verify-otp", json={"email": email, "otp": otp})
    assert r.status_code == 200, f"member verify-otp failed: {r.text}"
    return r.json()["access_token"]


class TestAuth:
    """POST /auth/register, verify-otp, resend-otp, and POST /auth/login."""

    def test_register_success(self, test_client) -> None:
        """Valid registration returns 201 OtpSentResponse (not a token)."""
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "newuser@neuradesk.ai", "password": "password123", "first_name": "New", "last_name": "User", "org_name": "New Co"},
            )
        assert r.status_code == 201
        body = r.json()
        assert body["message"] == "OTP sent"
        assert body["email"] == "newuser@neuradesk.ai"

    def test_register_without_org_returns_400(self, test_client) -> None:
        """Registration without org_name or invite_code returns 400 ORG_REQUIRED."""
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "noorg@neuradesk.ai", "password": "password123", "first_name": "No", "last_name": "Org"},
            )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "ORG_REQUIRED"

    def test_register_duplicate_email_returns_409(self, test_client) -> None:
        """Registering the same email twice returns 409 EMAIL_TAKEN."""
        payload = {"email": "dup@neuradesk.ai", "password": "password123", "first_name": "Dup", "last_name": "User", "org_name": "Dup Org"}
        with patch("api.auth.send_otp_email"):
            test_client.post("/auth/register", json=payload)
            r = test_client.post("/auth/register", json=payload)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_register_join_via_invite(self, test_client) -> None:
        """A second user can join an existing org with a single-use invite code."""
        token_admin = _register_and_verify(test_client, "admin@org.ai", "password123", "My Org")
        r = test_client.post(
            "/admin/invites",
            json={"expires_days": 7},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert r.status_code == 201
        invite = r.json()["code"]

        with patch("api.auth.send_otp_email") as mock:
            r = test_client.post(
                "/auth/register",
                json={"email": "employee@org.ai", "password": "password123", "first_name": "Employee", "last_name": "User", "invite_code": invite},
            )
            assert r.status_code == 201
            otp = mock.call_args[0][1]
        r = test_client.post("/auth/verify-otp", json={"email": "employee@org.ai", "otp": otp})
        assert r.status_code == 200

    def test_invite_code_single_use(self, test_client) -> None:
        """An invite code cannot be reused after it has been claimed."""
        token_admin = _register_and_verify(test_client, "admin.singleuse@org.ai", "password123", "SingleUse Org")
        r = test_client.post(
            "/admin/invites",
            json={"expires_days": 7},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        invite = r.json()["code"]

        # First use succeeds
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "first@org.ai", "password": "password123", "first_name": "First", "last_name": "User", "invite_code": invite},
            )
        assert r.status_code == 201

        # Second use with the same code must be rejected
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "second@org.ai", "password": "password123", "first_name": "Second", "last_name": "User", "invite_code": invite},
            )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVITE_USED"

    def test_verify_otp_success(self, test_client) -> None:
        """Correct OTP activates account and returns an access token."""
        with patch("api.auth.send_otp_email") as mock_email:
            test_client.post(
                "/auth/register",
                json={"email": "otpuser@neuradesk.ai", "password": "password123", "first_name": "Otp", "last_name": "User", "org_name": "OTP Org"},
            )
            otp = mock_email.call_args[0][1]
        r = test_client.post(
            "/auth/verify-otp",
            json={"email": "otpuser@neuradesk.ai", "otp": otp},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_verify_otp_invalid_returns_400(self, test_client) -> None:
        """Wrong OTP returns 400 INVALID_OTP."""
        with patch("api.auth.send_otp_email"):
            test_client.post(
                "/auth/register",
                json={"email": "badotp@neuradesk.ai", "password": "password123", "first_name": "Bad", "last_name": "Otp", "org_name": "Bad OTP Org"},
            )
        r = test_client.post(
            "/auth/verify-otp",
            json={"email": "badotp@neuradesk.ai", "otp": "000000"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_OTP"

    def test_login_success(self, test_client) -> None:
        """Correct credentials for a verified account return 200 with a bearer token."""
        _register_and_verify(test_client, "logintest@neuradesk.ai", "password123")
        r = test_client.post(
            "/auth/login",
            json={"email": "logintest@neuradesk.ai", "password": "password123"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body

    def test_login_unverified_returns_403(self, test_client) -> None:
        """Unverified account (OTP not completed) is rejected with 403 EMAIL_NOT_VERIFIED."""
        with patch("api.auth.send_otp_email"):
            test_client.post(
                "/auth/register",
                json={"email": "unverified@neuradesk.ai", "password": "password123", "first_name": "Unverified", "last_name": "User", "org_name": "UV Org"},
            )
        r = test_client.post(
            "/auth/login",
            json={"email": "unverified@neuradesk.ai", "password": "password123"},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"

    def test_login_wrong_password_returns_401(self, test_client) -> None:
        """Wrong password returns 401 BAD_CREDENTIALS."""
        _register_and_verify(test_client, "wrongpw@neuradesk.ai", "password123")
        r = test_client.post(
            "/auth/login",
            json={"email": "wrongpw@neuradesk.ai", "password": "wrongpassword"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "BAD_CREDENTIALS"


class TestTickets:
    """POST /tickets, GET /tickets/, GET /tickets/{id}."""

    def test_submit_ticket_authenticated(
        self, auth_client, sample_ticket_payload
    ) -> None:
        """Authenticated POST /tickets → 201 with a pending ticket (graph runs over WS)."""
        r = auth_client.post("/tickets", json=sample_ticket_payload)
        assert r.status_code == 201
        body = r.json()
        assert "ticket_id" in body
        assert body["status"] == "pending"

    def test_submit_ticket_unauthenticated_returns_403(
        self, test_client, sample_ticket_payload
    ) -> None:
        """No Authorization header → 403 (HTTPBearer auto_error=True)."""
        r = test_client.post("/tickets", json=sample_ticket_payload)
        assert r.status_code == 403

    def test_list_tickets_empty_for_new_user(self, auth_client) -> None:
        """Newly registered user has no tickets."""
        r = auth_client.get("/tickets/")
        assert r.status_code == 200
        body = r.json()
        assert body["tickets"] == []
        assert body["total"] == 0

    def test_list_tickets_after_submit(
        self, auth_client, sample_ticket_payload
    ) -> None:
        """Ticket appears in the list after submission."""
        auth_client.post("/tickets", json=sample_ticket_payload)
        r = auth_client.get("/tickets/")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_list_tickets_filters_by_status(self, auth_client, db_engine) -> None:
        """?status= returns only matching tickets, with a matching total."""
        from sqlalchemy.orm import sessionmaker

        from api.models import TicketModel

        ids = [auth_client.post("/tickets", json={"text": f"ticket {i}"}).json()["ticket_id"] for i in range(3)]
        db = sessionmaker(bind=db_engine)()
        db.get(TicketModel, ids[0]).status = "awaiting_confirmation"
        db.commit()
        db.close()

        r = auth_client.get("/tickets/", params={"status": "awaiting_confirmation"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert [t["ticket_id"] for t in body["tickets"]] == [ids[0]]
        assert auth_client.get("/tickets/").json()["total"] == 3

    def _seed(self, auth_client, db_engine, items: list[tuple[str, str]]) -> list[str]:
        """Create tickets with given (text, status) via the API, then set their status."""
        from sqlalchemy.orm import sessionmaker

        from api.models import TicketModel

        ids = [auth_client.post("/tickets", json={"text": text}).json()["ticket_id"] for text, _ in items]
        db = sessionmaker(bind=db_engine)()
        for tid, (_, st) in zip(ids, items, strict=True):
            db.get(TicketModel, tid).status = st
        db.commit()
        db.close()
        return ids

    def test_list_tickets_multi_status_filter(self, auth_client, db_engine) -> None:
        """?status=a,b returns tickets in either status."""
        self._seed(auth_client, db_engine, [("one", "pending"), ("two", "processing"), ("three", "resolved")])
        r = auth_client.get("/tickets/", params={"status": "pending,processing"})
        assert r.json()["total"] == 2

    def test_list_tickets_search(self, auth_client, db_engine) -> None:
        """?q= searches the request text case-insensitively and treats % literally."""
        self._seed(auth_client, db_engine, [
            ("VPN keeps dropping", "resolved"), ("Need Jira access", "resolved"), ("Disk is 100% full", "escalated"),
        ])
        assert auth_client.get("/tickets/", params={"q": "vpn"}).json()["total"] == 1
        assert auth_client.get("/tickets/", params={"q": "100%"}).json()["total"] == 1
        assert auth_client.get("/tickets/", params={"q": "%"}).json()["total"] == 1  # literal, not wildcard
        assert auth_client.get("/tickets/", params={"q": "nothing-matches"}).json()["total"] == 0

    def test_ticket_summary_counts_all_tickets(self, auth_client, db_engine) -> None:
        """/tickets/summary counts every ticket by status (not just one page)."""
        self._seed(auth_client, db_engine, [("a", "resolved"), ("b", "resolved"), ("c", "awaiting_confirmation")])
        r = auth_client.get("/tickets/summary")
        assert r.status_code == 200
        assert r.json() == {"total": 3, "by_status": {"resolved": 2, "awaiting_confirmation": 1}}

    def test_ticket_summary_is_per_user(self, auth_client, test_client) -> None:
        """Another user's summary never includes my tickets."""
        auth_client.post("/tickets", json={"text": "mine"})
        other = _register_and_verify(test_client, "other.sum@acme.ai", "password123", "Other Org")
        r = test_client.get("/tickets/summary", headers={"Authorization": f"Bearer {other}"})
        assert r.json() == {"total": 0, "by_status": {}}

    def test_get_ticket_success(
        self, auth_client, sample_ticket_payload
    ) -> None:
        """Owner can retrieve their ticket by ID."""
        create_r = auth_client.post("/tickets", json=sample_ticket_payload)
        ticket_id = create_r.json()["ticket_id"]

        r = auth_client.get(f"/tickets/{ticket_id}")
        assert r.status_code == 200
        assert r.json()["ticket_id"] == ticket_id

    def test_get_ticket_not_owned_returns_404(
        self, auth_client, sample_ticket_payload
    ) -> None:
        """User B cannot retrieve User A's ticket — returns 404."""
        create_r = auth_client.post("/tickets", json=sample_ticket_payload)
        assert create_r.status_code == 201
        ticket_id = create_r.json()["ticket_id"]

        # Register + verify User B, then login (uses the same DB-overridden client).
        token_b = _register_and_verify(auth_client, "userb@neuradesk.ai", "password123")

        r = auth_client.get(
            f"/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "TICKET_NOT_FOUND"

    def test_get_nonexistent_ticket_returns_404(self, auth_client) -> None:
        """Requesting a ticket ID that does not exist returns 404."""
        r = auth_client.get("/tickets/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


class TestOrgCreationGuard:
    """ORG_CREATION_SECRET — restrict who can create orgs."""

    def test_config_returns_restricted_false_by_default(self, test_client) -> None:
        """Without ORG_CREATION_SECRET set, config reports unrestricted."""
        r = test_client.get("/auth/config")
        assert r.status_code == 200
        assert r.json()["org_creation_restricted"] is False

    def test_config_returns_restricted_true_when_secret_set(self, test_client, monkeypatch) -> None:
        """With ORG_CREATION_SECRET set, config reports restricted."""
        monkeypatch.setenv("ORG_CREATION_SECRET", "super-secret-token")
        import api.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_ORG_CREATION_SECRET", "super-secret-token")
        r = test_client.get("/auth/config")
        assert r.status_code == 200
        assert r.json()["org_creation_restricted"] is True

    def test_register_with_org_blocked_when_no_token(self, test_client, monkeypatch) -> None:
        """When restricted, creating an org without the token returns 403 ORG_TOKEN_REQUIRED."""
        import api.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_ORG_CREATION_SECRET", "super-secret-token")
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "blocked@org.ai", "password": "password123", "first_name": "Blocked", "last_name": "User", "org_name": "Blocked Org"},
            )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "ORG_TOKEN_REQUIRED"

    def test_register_with_org_blocked_when_wrong_token(self, test_client, monkeypatch) -> None:
        """Wrong token is rejected with 403."""
        import api.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_ORG_CREATION_SECRET", "super-secret-token")
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "wrong@org.ai", "password": "password123", "first_name": "Wrong", "last_name": "Token", "org_name": "Wrong Org",
                      "org_creation_token": "wrong-token"},
            )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "ORG_TOKEN_REQUIRED"

    def test_register_with_org_succeeds_with_correct_token(self, test_client, monkeypatch) -> None:
        """Correct token allows org creation."""
        import api.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_ORG_CREATION_SECRET", "super-secret-token")
        with patch("api.auth.send_otp_email"):
            r = test_client.post(
                "/auth/register",
                json={"email": "admin@correct.ai", "password": "password123", "first_name": "Admin", "last_name": "Correct", "org_name": "Correct Org",
                      "org_creation_token": "super-secret-token"},
            )
        assert r.status_code == 201

    def test_join_via_invite_unaffected_by_restriction(self, test_client, monkeypatch) -> None:
        """Joining an existing org with invite code works even when org creation is restricted."""
        admin_token = _register_and_verify(test_client, "admin5@org.ai", "password123", "Invite Org 5")
        r = test_client.post(
            "/admin/invites",
            json={"expires_days": 7},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        invite = r.json()["code"]

        # Now restrict org creation — joining via invite must still work
        import api.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_ORG_CREATION_SECRET", "super-secret-token")

        with patch("api.auth.send_otp_email") as mock_email:
            r = test_client.post(
                "/auth/register",
                json={"email": "member5@org.ai", "password": "password123", "first_name": "Member", "last_name": "Five", "invite_code": invite},
            )
            assert r.status_code == 201
            otp = mock_email.call_args[0][1]
        r = test_client.post("/auth/verify-otp", json={"email": "member5@org.ai", "otp": otp})
        assert r.status_code == 200


class TestForgotResetPassword:
    """POST /auth/forgot-password and POST /auth/reset-password."""

    def test_forgot_password_always_returns_200(self, test_client) -> None:
        """Non-existent email still returns 200 to prevent user enumeration."""
        r = test_client.post(
            "/auth/forgot-password",
            json={"email": "ghost@neuradesk.ai"},
        )
        assert r.status_code == 200
        assert r.json()["message"] == "OTP sent"

    def test_forgot_password_sends_otp(self, test_client) -> None:
        """Verified user receives an OTP email after calling forgot-password."""
        _register_and_verify(test_client, "resetme@neuradesk.ai", "password123")
        with patch("api.auth.send_otp_email") as mock_email:
            r = test_client.post(
                "/auth/forgot-password",
                json={"email": "resetme@neuradesk.ai"},
            )
        assert r.status_code == 200
        mock_email.assert_called_once()

    def test_reset_password_success(self, test_client) -> None:
        """Valid OTP + new password resets credentials and returns a token."""
        _register_and_verify(test_client, "reset2@neuradesk.ai", "oldpassword")
        with patch("api.auth.send_otp_email") as mock_email:
            test_client.post("/auth/forgot-password", json={"email": "reset2@neuradesk.ai"})
            otp = mock_email.call_args[0][1]

        r = test_client.post(
            "/auth/reset-password",
            json={"email": "reset2@neuradesk.ai", "otp": otp, "new_password": "newpassword123"},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_reset_password_wrong_otp_returns_400(self, test_client) -> None:
        """Wrong OTP returns 400 INVALID_RESET."""
        _register_and_verify(test_client, "reset3@neuradesk.ai", "password123")
        with patch("api.auth.send_otp_email"):
            test_client.post("/auth/forgot-password", json={"email": "reset3@neuradesk.ai"})

        r = test_client.post(
            "/auth/reset-password",
            json={"email": "reset3@neuradesk.ai", "otp": "000000", "new_password": "newpassword123"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_RESET"

    def test_new_password_works_for_login(self, test_client) -> None:
        """After reset, old password is rejected and new password succeeds."""
        _register_and_verify(test_client, "reset4@neuradesk.ai", "oldpassword")
        with patch("api.auth.send_otp_email") as mock_email:
            test_client.post("/auth/forgot-password", json={"email": "reset4@neuradesk.ai"})
            otp = mock_email.call_args[0][1]
        test_client.post(
            "/auth/reset-password",
            json={"email": "reset4@neuradesk.ai", "otp": otp, "new_password": "newpassword123"},
        )

        r_old = test_client.post("/auth/login", json={"email": "reset4@neuradesk.ai", "password": "oldpassword"})
        assert r_old.status_code == 401

        r_new = test_client.post("/auth/login", json={"email": "reset4@neuradesk.ai", "password": "newpassword123"})
        assert r_new.status_code == 200
        assert "access_token" in r_new.json()


class TestOrg:
    """GET /orgs/me, POST /orgs/invite/regenerate, GET /orgs/members."""

    def test_get_org_me(self, auth_client) -> None:
        """Authenticated user can retrieve their org details."""
        r = auth_client.get("/orgs/me")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Fixture Org"
        assert "invite_code" in body

    def test_get_org_me_unauthenticated(self, test_client) -> None:
        """No token → 403."""
        r = test_client.get("/orgs/me")
        assert r.status_code == 403

    def test_regenerate_invite_code_admin(self, auth_client) -> None:
        """Admin can regenerate the invite code; new code differs from old."""
        r1 = auth_client.get("/orgs/me")
        old_code = r1.json()["invite_code"]

        r2 = auth_client.post("/orgs/invite/regenerate")
        assert r2.status_code == 200
        new_code = r2.json()["invite_code"]
        assert new_code != old_code

    def test_regenerate_invite_code_non_admin_denied(self, test_client) -> None:
        """Non-admin member cannot regenerate the invite code."""
        admin_token = _register_and_verify(test_client, "admin@invite.ai", "password123", "Invite Org")
        member_token = _register_member(test_client, admin_token, "member@invite.ai", "password123")
        r = test_client.post("/orgs/invite/regenerate", headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403

    def test_get_members_admin(self, auth_client) -> None:
        """Admin can list org members."""
        r = auth_client.get("/orgs/members")
        assert r.status_code == 200
        body = r.json()
        assert "members" in body
        assert len(body["members"]) >= 1

    def test_get_members_non_admin_denied(self, test_client) -> None:
        """Non-admin member cannot list org members."""
        admin_token = _register_and_verify(test_client, "admin2@invite.ai", "password123", "Invite Org 2")
        member_token = _register_member(test_client, admin_token, "member2@invite.ai", "password123")
        r = test_client.get("/orgs/members", headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403


class TestAdmin:
    """GET /admin/tickets, GET /admin/stats."""

    def test_admin_stats_returns_counts(self, auth_client, sample_ticket_payload) -> None:
        """Admin stats returns total/resolved/escalated/pending counts."""
        auth_client.post("/tickets", json=sample_ticket_payload)
        r = auth_client.get("/admin/stats")
        assert r.status_code == 200
        body = r.json()
        for key in ("total", "resolved", "escalated", "pending"):
            assert key in body
        assert body["total"] >= 1

    def test_admin_tickets_returns_list(self, auth_client, sample_ticket_payload) -> None:
        """GET /admin/tickets returns a paginated list of org tickets."""
        auth_client.post("/tickets", json=sample_ticket_payload)
        r = auth_client.get("/admin/tickets")
        assert r.status_code == 200
        body = r.json()
        assert "tickets" in body
        assert body["total"] >= 1

    def test_admin_tickets_status_filter(self, auth_client, sample_ticket_payload) -> None:
        """Status filter limits results to matching tickets only."""
        auth_client.post("/tickets", json=sample_ticket_payload)
        r = auth_client.get("/admin/tickets?status=resolved")
        assert r.status_code == 200
        for t in r.json()["tickets"]:
            assert t["status"] == "resolved"

    def test_admin_tickets_non_admin_denied(self, test_client) -> None:
        """Non-admin member cannot access the admin ticket list."""
        admin_token = _register_and_verify(test_client, "admin3@admin.ai", "password123", "NoAdmin Org")
        member_token = _register_member(test_client, admin_token, "nonadmin@admin.ai", "password123")
        r = test_client.get("/admin/tickets", headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403

    def test_admin_stats_non_admin_denied(self, test_client) -> None:
        """Non-admin member cannot access admin stats."""
        admin_token = _register_and_verify(test_client, "admin4@admin.ai", "password123", "NoAdmin Org 2")
        member_token = _register_member(test_client, admin_token, "nonadmin2@admin.ai", "password123")
        r = test_client.get("/admin/stats", headers={"Authorization": f"Bearer {member_token}"})
        assert r.status_code == 403

    def test_admin_tickets_pagination(self, auth_client, sample_ticket_payload) -> None:
        """Offset/limit pagination works for admin ticket list."""
        for _ in range(3):
            auth_client.post("/tickets", json=sample_ticket_payload)

        r = auth_client.get("/admin/tickets?limit=2&offset=0")
        assert r.status_code == 200
        body = r.json()
        assert len(body["tickets"]) <= 2
        assert body["limit"] == 2
        assert body["offset"] == 0


class TestJWTRevocation:
    """POST /auth/logout — token blocklist and revocation on logout + password change."""

    def test_logout_returns_200(self, auth_client) -> None:
        """POST /auth/logout with a valid token returns 200 with a message."""
        r = auth_client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json()["message"] == "Logged out successfully"

    def test_revoked_token_rejected_with_401(self, auth_client) -> None:
        """After logout, the same token is rejected on any authenticated endpoint."""
        auth_client.post("/auth/logout")
        r = auth_client.get("/tickets/")
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "TOKEN_REVOKED"

    def test_change_password_revokes_old_token(self, auth_client) -> None:
        """After change-password, the old Bearer token is rejected with TOKEN_REVOKED."""
        old_auth_header = auth_client.headers["Authorization"]
        auth_client.post(
            "/auth/change-password",
            json={"current_password": "testpassword99", "new_password": "newpassword99"},
        )
        r = auth_client.get("/tickets/", headers={"Authorization": old_auth_header})
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "TOKEN_REVOKED"

    def test_logout_is_idempotent(self, auth_client) -> None:
        """Calling logout twice does not raise a 500 — second call is a no-op."""
        r1 = auth_client.post("/auth/logout")
        assert r1.status_code == 200
        # Second call uses already-revoked token — logout bypasses get_current_user's
        # blocklist check and is idempotent (jti already present, no duplicate insert).
        r2 = auth_client.post("/auth/logout")
        assert r2.status_code == 200

    def test_fresh_token_after_logout_works(self, test_client) -> None:
        """A new login after logout returns a fresh valid token."""
        token = _register_and_verify(test_client, "fresh@logout.ai", "password123", "Logout Org")
        test_client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        # Re-login and get a new token
        r = test_client.post("/auth/login", json={"email": "fresh@logout.ai", "password": "password123"})
        assert r.status_code == 200
        new_token = r.json()["access_token"]
        # New token should work
        r2 = test_client.get("/tickets/", headers={"Authorization": f"Bearer {new_token}"})
        assert r2.status_code == 200


class TestAdminKB:
    """POST /admin/kb — knowledge base doc creation with live retriever update."""

    def test_create_kb_doc_updates_retriever(self, auth_client) -> None:
        """Creating a KB doc via POST /admin/kb persists it to DB and returns the created doc."""
        r = auth_client.post(
            "/admin/kb",
            json={"title": "VPN Troubleshooting", "content": "If VPN fails, restart the client and re-authenticate using your SSO credentials."},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "VPN Troubleshooting"
        assert "VPN" in body["content"]

    def test_create_kb_doc_succeeds_even_if_retriever_raises(self, auth_client) -> None:
        """POST /admin/kb returns 201 and persists the doc — org docs no longer touch the retriever."""
        r = auth_client.post(
            "/admin/kb",
            json={"title": "Fallback Test", "content": "Content that is at least ten characters long."},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "Fallback Test"


class TestConfirmCancel:
    """POST /tickets/{id}/confirm-action and POST /tickets/{id}/cancel."""

    def _create_awaiting_ticket(self, test_client, db_engine, email: str, org: str) -> tuple[str, str]:
        """Register a user, create a ticket, force status to awaiting_confirmation. Returns (ticket_id, token)."""
        from sqlalchemy.orm import sessionmaker

        from api.models import TicketModel

        token = _register_and_verify(test_client, email, "password123", org)
        r = test_client.post(
            "/tickets",
            json={"text": "revoke my access immediately"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        ticket_id = r.json()["ticket_id"]

        S = sessionmaker(bind=db_engine)
        db = S()
        t = db.get(TicketModel, ticket_id)
        t.status = "awaiting_confirmation"
        db.commit()
        db.close()
        return ticket_id, token

    @staticmethod
    def _as_triaged_delete(db_engine, ticket_id: str) -> None:
        """Give the awaiting ticket the triage an account_delete request would have."""
        from sqlalchemy.orm import sessionmaker

        from api.models import TicketModel

        db = sessionmaker(bind=db_engine)()
        t = db.get(TicketModel, ticket_id)
        t.category, t.intent, t.confidence, t.priority = "account_delete", "account_delete", 0.95, "HIGH"
        db.commit()
        db.close()

    def test_confirm_action_runs_real_graph_and_resolves(self, test_client, db_engine, monkeypatch) -> None:
        """Confirm runs the REAL async graph (regression: sync invoke() crashed with
        'No synchronous function provided to action_node') and executes the SAME action."""
        from unittest.mock import AsyncMock, MagicMock

        from sqlalchemy.orm import sessionmaker

        import api.main as main_mod

        ticket_id, token = self._create_awaiting_ticket(test_client, db_engine, "confirm@action.ai", "Confirm Org")
        self._as_triaged_delete(db_engine, ticket_id)
        monkeypatch.setattr(main_mod, "SessionLocal", sessionmaker(bind=db_engine))
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="Your account deletion is complete, {username}.")
        retr = MagicMock()
        retr.search.return_value = [{"source": "org-kb:Offboarding", "content": "Account deletion steps.", "score": 3.0}]
        iam_ok = {"success": True, "action": "delete-account", "result": {"deleted": True}}

        with patch("agents.knowledge_node.get_llm", return_value=llm), \
             patch("agents.knowledge_node.get_retriever", return_value=retr), \
             patch("agents.intake_node.classify") as classify, \
             patch("agents.action_node._post_enterprise", new_callable=AsyncMock, return_value=iam_ok) as post:
            r = test_client.post(f"/tickets/{ticket_id}/confirm-action", headers={"Authorization": f"Bearer {token}"})

        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        assert r.json()["category"] == "account_delete"
        classify.assert_not_called()  # resumed from the persisted triage — no re-classification
        post.assert_awaited_once()
        assert post.call_args.args[0] == "/iam/delete-account"

    def test_double_confirm_cannot_execute_twice(self, test_client, db_engine) -> None:
        """Once a confirmation is claimed, a second confirm is rejected (no double delete)."""
        from sqlalchemy.orm import sessionmaker

        import api.main as main_mod
        from api.main import _claim_ticket

        ticket_id, token = self._create_awaiting_ticket(test_client, db_engine, "dbl@action.ai", "Double Org")
        main_mod_session = main_mod.SessionLocal
        main_mod.SessionLocal = sessionmaker(bind=db_engine)
        try:
            assert _claim_ticket(ticket_id, from_status="awaiting_confirmation") is True  # first click wins
            r = test_client.post(f"/tickets/{ticket_id}/confirm-action", headers={"Authorization": f"Bearer {token}"})
        finally:
            main_mod.SessionLocal = main_mod_session
        assert r.status_code == 409

    def test_cancel_action_escalates(self, test_client, db_engine) -> None:
        """POST /tickets/{id}/cancel sets status to escalated with a cancellation reason."""
        ticket_id, token = self._create_awaiting_ticket(
            test_client, db_engine, "cancel@action.ai", "Cancel Org"
        )
        r = test_client.post(
            f"/tickets/{ticket_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "escalated"
        assert body["escalation_reason"] is not None
        assert "cancelled" in body["escalation_reason"].lower()

    def test_confirm_action_rejects_wrong_user(self, test_client, db_engine) -> None:
        """User B cannot confirm User A's ticket — returns 404."""
        ticket_id, _token_a = self._create_awaiting_ticket(
            test_client, db_engine, "owner.conf@action.ai", "Owner Org Conf"
        )
        token_b = _register_and_verify(test_client, "attacker.conf@action.ai", "password123", "Attacker Org Conf")
        r = test_client.post(
            f"/tickets/{ticket_id}/confirm-action",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "TICKET_NOT_FOUND"

    def test_confirm_returns_409_if_not_awaiting(self, test_client, db_engine) -> None:
        """Confirming a ticket that is already resolved returns 409 INVALID_TICKET_STATUS."""
        token = _register_and_verify(test_client, "conf409@action.ai", "password123", "409 Org")
        r = test_client.post(
            "/tickets",
            json={"text": "I forgot my password"},
            headers={"Authorization": f"Bearer {token}"},
        )
        ticket_id = r.json()["ticket_id"]

        r = test_client.post(
            f"/tickets/{ticket_id}/confirm-action",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "INVALID_TICKET_STATUS"


class TestImagePersistence:
    """POST /tickets image upload via GCS."""

    def test_image_url_stored_when_upload_succeeds(self, test_client) -> None:
        """When upload_image_b64 returns a URL, it is persisted and returned in the response."""
        token = _register_and_verify(test_client, "imgtest1@acme.ai", "password123", "ImgOrg1")
        fake_url = "https://storage.googleapis.com/neuradesk-bucket/tickets/abc/screenshot.png"
        with patch("api.main.upload_image_b64", return_value=fake_url):
            r = test_client.post(
                "/tickets",
                json={"text": "My screen is broken", "image_b64": "aGVsbG8="},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 201
        assert r.json()["image_url"] == fake_url

    def test_image_url_none_when_no_image(self, test_client) -> None:
        """Tickets without image_b64 have image_url=None in the response."""
        token = _register_and_verify(test_client, "imgtest2@acme.ai", "password123", "ImgOrg2")
        r = test_client.post(
            "/tickets",
            json={"text": "No screenshot attached"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert r.json()["image_url"] is None

    def test_ticket_created_even_if_upload_fails(self, test_client) -> None:
        """A GCS upload failure does not prevent ticket creation (image_url remains None)."""
        token = _register_and_verify(test_client, "imgtest3@acme.ai", "password123", "ImgOrg3")
        with patch("api.main.upload_image_b64", return_value=None):
            r = test_client.post(
                "/tickets",
                json={"text": "Screenshot attached but GCS is down", "image_b64": "aGVsbG8="},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert r.status_code == 201
        assert r.json()["image_url"] is None

    def test_image_url_persisted_and_returned_by_get(self, test_client) -> None:
        """image_url stored on create is returned unchanged by GET /tickets/{id}."""
        token = _register_and_verify(test_client, "imgtest4@acme.ai", "password123", "ImgOrg4")
        fake_url = "https://storage.googleapis.com/neuradesk-bucket/tickets/xyz/screenshot.png"
        with patch("api.main.upload_image_b64", return_value=fake_url):
            create_r = test_client.post(
                "/tickets",
                json={"text": "Persisted screenshot", "image_b64": "aGVsbG8="},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert create_r.status_code == 201
        ticket_id = create_r.json()["ticket_id"]

        get_r = test_client.get(
            f"/tickets/{ticket_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_r.status_code == 200
        assert get_r.json()["image_url"] == fake_url


class TestAdminSSE:
    """GET /admin/stream SSE endpoint."""

    def test_sse_missing_token_returns_422(self, test_client) -> None:
        """SSE endpoint requires token query param — omitting it returns 422."""
        r = test_client.get("/admin/stream")
        assert r.status_code == 422

    def test_sse_invalid_token_returns_401(self, test_client) -> None:
        """Malformed JWT in token query param returns 401."""
        r = test_client.get("/admin/stream", params={"token": "garbage.jwt.value"})
        assert r.status_code == 401

    def test_sse_non_admin_returns_403(self, test_client) -> None:
        """Member (non-admin) token returns 403."""
        admin_token = _register_and_verify(test_client, "sse_adm@acme.ai", "password123", "SseOrgA")
        member_token = _register_member(test_client, admin_token, "sse_mem@acme.ai", "password123")
        r = test_client.get("/admin/stream", params={"token": member_token})
        assert r.status_code == 403

    def test_sse_admin_gets_event_stream(self, test_client) -> None:
        """Valid admin token → 200 text/event-stream; first event is a ping."""
        token = _register_and_verify(test_client, "sse_adm2@acme.ai", "password123", "SseOrgB")

        # Patch _sse_event_stream with a finite one-shot generator so test_client.get()
        # returns cleanly instead of blocking forever on an infinite stream.
        async def _one_ping(org_id: str, start_after_id: int):
            yield "event: ping\ndata: {}\n\n"

        with patch("api.admin._sse_event_stream", side_effect=_one_ping):
            r = test_client.get("/admin/stream", params={"token": token})

        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        assert b"ping" in r.content


class TestOtpLockout:
    """OTP brute-force lockout on /auth/verify-otp."""

    def test_otp_locks_after_max_attempts(self, test_client) -> None:
        """Five wrong OTP guesses invalidate the code; the sixth returns 429 OTP_LOCKED."""
        with patch("api.auth.send_otp_email") as mock_email:
            r = test_client.post("/auth/register", json={
                "email": "lockout@acme.ai", "password": "password123",
                "first_name": "Lock", "last_name": "Out", "org_name": "Lockout Org",
            })
            assert r.status_code == 201
            real_otp = mock_email.call_args[0][1]

        wrong = "000000" if real_otp != "000000" else "111111"
        for _ in range(5):
            rr = test_client.post("/auth/verify-otp", json={"email": "lockout@acme.ai", "otp": wrong})
            assert rr.status_code == 400

        # Sixth attempt → locked.
        rr = test_client.post("/auth/verify-otp", json={"email": "lockout@acme.ai", "otp": wrong})
        assert rr.status_code == 429
        assert rr.json()["detail"]["code"] == "OTP_LOCKED"

        # The code is now cleared — even the correct OTP no longer verifies.
        rr = test_client.post("/auth/verify-otp", json={"email": "lockout@acme.ai", "otp": real_otp})
        assert rr.status_code == 400


class TestHealth:
    """GET /health liveness probe."""

    def test_health_returns_ok(self, test_client) -> None:
        """Health endpoint returns 200 regardless of auth state."""
        r = test_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_response_datetimes_are_explicit_utc() -> None:
    """Naive DB datetimes (SQLite) are serialised with a UTC offset, never as bare local time."""
    from datetime import datetime

    from api.models import TicketResponse

    body = TicketResponse(ticket_id="t", status="resolved", created_at=datetime(2026, 11, 24, 12, 0)).model_dump_json()
    assert '"created_at":"2026-11-24T12:00:00Z"' in body


class TestAdminDashboardApi:
    """Admin stats breakdown and ticket search used by the Overview dashboard."""

    def _seed(self, auth_client, db_engine, rows):
        """rows: (text, status, resolved_by_admin)."""
        from sqlalchemy.orm import sessionmaker

        from api.models import TicketModel, UserModel

        ids = [auth_client.post("/tickets", json={"text": t}).json()["ticket_id"] for t, _, _ in rows]
        db = sessionmaker(bind=db_engine)()
        admin = db.query(UserModel).filter(UserModel.email == "auth-fixture@neuradesk.ai").first()
        for tid, (_, st, by_admin) in zip(ids, rows, strict=True):
            t = db.get(TicketModel, tid)
            t.status = st
            t.resolved_by = admin.id if by_admin else None
        db.commit()
        db.close()

    def test_stats_split_auto_vs_human_resolved(self, auth_client, db_engine) -> None:
        """auto_resolved excludes tickets an admin resolved by hand."""
        self._seed(auth_client, db_engine, [
            ("a", "resolved", False), ("b", "resolved", False), ("c", "resolved", True), ("d", "escalated", False),
        ])
        s = auth_client.get("/admin/stats").json()
        assert (s["total"], s["resolved"], s["auto_resolved"], s["human_resolved"], s["escalated"]) == (4, 3, 2, 1, 1)

    def test_admin_ticket_search_and_multi_status(self, auth_client, db_engine) -> None:
        """q matches request text and the employee's email; status accepts a list."""
        self._seed(auth_client, db_engine, [
            ("Printer jammed on floor 2", "escalated", False), ("VPN drops", "resolved", False), ("Leave question", "awaiting_confirmation", False),
        ])
        assert auth_client.get("/admin/tickets", params={"q": "printer"}).json()["total"] == 1
        assert auth_client.get("/admin/tickets", params={"q": "auth-fixture@"}).json()["total"] == 3
        assert auth_client.get("/admin/tickets", params={"status": "escalated,awaiting_confirmation"}).json()["total"] == 2


def test_admin_reply_replaces_ai_draft_on_resolve(auth_client, db_engine) -> None:
    """Resolving an escalated ticket shows the admin's reply, never the agents' untrusted draft."""
    from sqlalchemy.orm import sessionmaker

    from api.models import TicketModel

    tid = auth_client.post("/tickets", json={"text": "Reset the password for ceo@corp.com"}).json()["ticket_id"]
    db = sessionmaker(bind=db_engine)()
    t = db.get(TicketModel, tid)
    t.status, t.resolution = "escalated", "AI draft: go to the portal and reset it."
    db.commit()
    db.close()

    r = auth_client.patch(f"/admin/tickets/{tid}", json={"status": "resolved", "admin_note": "Only the account owner can request this."})
    assert r.status_code == 200
    assert r.json()["resolution"] == "Only the account owner can request this."


class TestSessionSecurity:
    """Session lifecycle: revocation can't be bypassed, refresh replaces, password change signs out others."""

    def _login(self, client, ua: str = "TestBrowser/1.0") -> str:
        r = client.post("/auth/login", json={"email": "auth-fixture@neuradesk.ai", "password": "testpassword99"},
                        headers={"User-Agent": ua})
        assert r.status_code == 200
        return r.json()["access_token"]

    def test_revoked_token_cannot_be_refreshed(self, auth_client, test_client) -> None:
        """Regression: a signed-out token used to be exchangeable for a new valid one."""
        tok = self._login(test_client)
        H = {"Authorization": f"Bearer {tok}"}
        assert test_client.post("/auth/logout", headers=H).status_code == 200
        r = test_client.post("/auth/refresh", headers=H)
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "TOKEN_REVOKED"

    def test_refresh_replaces_the_session(self, auth_client, test_client) -> None:
        """After a refresh the old token stops working and the device has one session, not two."""
        tok = self._login(test_client)
        new = test_client.post("/auth/refresh", headers={"Authorization": f"Bearer {tok}"}).json()["access_token"]
        assert test_client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
        sessions = test_client.get("/auth/sessions", headers={"Authorization": f"Bearer {new}"}).json()["sessions"]
        assert tok not in [s["jti"] for s in sessions]

    def test_sessions_record_device(self, auth_client, test_client) -> None:
        """The session list shows which browser signed in."""
        tok = self._login(test_client, ua="Mozilla/5.0 (Macintosh) Chrome/131.0")
        sessions = test_client.get("/auth/sessions", headers={"Authorization": f"Bearer {tok}"}).json()["sessions"]
        current = next(s for s in sessions if s["is_current"])
        assert "Chrome" in current["user_agent"]

    def test_password_change_signs_out_other_devices(self, auth_client, test_client) -> None:
        """Changing the password revokes every other session; this device gets a fresh token."""
        laptop = self._login(test_client, ua="Laptop")
        phone = self._login(test_client, ua="Phone")
        r = test_client.post("/auth/change-password", json={"current_password": "testpassword99", "new_password": "brandNewPass42"},
                             headers={"Authorization": f"Bearer {laptop}"})
        assert r.status_code == 200
        assert r.json()["other_sessions_signed_out"] >= 1
        assert test_client.get("/auth/me", headers={"Authorization": f"Bearer {phone}"}).status_code == 401
        assert test_client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200

    def test_new_password_must_differ(self, auth_client) -> None:
        """Re-using the current password is rejected."""
        r = auth_client.post("/auth/change-password", json={"current_password": "testpassword99", "new_password": "testpassword99"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "PASSWORD_UNCHANGED"

    def test_sign_out_all_other_sessions(self, auth_client, test_client) -> None:
        """DELETE /auth/sessions keeps the caller signed in and signs everything else out."""
        a = self._login(test_client, ua="A")
        b = self._login(test_client, ua="B")
        r = test_client.delete("/auth/sessions", headers={"Authorization": f"Bearer {a}"})
        assert r.status_code == 200 and r.json()["signed_out"] >= 1
        assert test_client.get("/auth/me", headers={"Authorization": f"Bearer {b}"}).status_code == 401
        assert test_client.get("/auth/me", headers={"Authorization": f"Bearer {a}"}).status_code == 200

    def test_update_name(self, auth_client) -> None:
        """PATCH /auth/me updates the name; blank names are rejected."""
        r = auth_client.patch("/auth/me", json={"first_name": " Ada ", "last_name": "Lovelace"})
        assert r.status_code == 200 and r.json()["first_name"] == "Ada"
        assert auth_client.get("/auth/me").json()["last_name"] == "Lovelace"
        assert auth_client.patch("/auth/me", json={"first_name": "", "last_name": "X"}).status_code == 422
