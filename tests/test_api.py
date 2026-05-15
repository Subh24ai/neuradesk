"""Tests for FastAPI routes — auth endpoints, ticket CRUD, and access control."""

import pytest


class TestAuth:
    """POST /auth/register and POST /auth/login."""

    def test_register_success(self, test_client) -> None:
        """Valid registration returns 201 with a bearer token."""
        r = test_client.post(
            "/auth/register",
            json={"email": "newuser@neuradesk.ai", "password": "password123"},
        )
        assert r.status_code == 201
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_register_duplicate_email_returns_409(self, test_client) -> None:
        """Registering the same email twice returns 409 EMAIL_TAKEN."""
        payload = {"email": "dup@neuradesk.ai", "password": "password123"}
        test_client.post("/auth/register", json=payload)
        r = test_client.post("/auth/register", json=payload)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "EMAIL_TAKEN"

    def test_login_success(self, test_client) -> None:
        """Correct credentials return 200 with a bearer token."""
        test_client.post(
            "/auth/register",
            json={"email": "logintest@neuradesk.ai", "password": "password123"},
        )
        r = test_client.post(
            "/auth/login",
            json={"email": "logintest@neuradesk.ai", "password": "password123"},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password_returns_401(self, test_client) -> None:
        """Wrong password returns 401 BAD_CREDENTIALS."""
        test_client.post(
            "/auth/register",
            json={"email": "wrongpw@neuradesk.ai", "password": "password123"},
        )
        r = test_client.post(
            "/auth/login",
            json={"email": "wrongpw@neuradesk.ai", "password": "wrongpassword"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "BAD_CREDENTIALS"


class TestTickets:
    """POST /tickets, GET /tickets/, GET /tickets/{id}."""

    def test_submit_ticket_authenticated(
        self, auth_client, mock_run_ticket, sample_ticket_payload
    ) -> None:
        """Authenticated POST /tickets → 201 with ticket_id and graph output."""
        r = auth_client.post("/tickets", json=sample_ticket_payload)
        assert r.status_code == 201
        body = r.json()
        assert "ticket_id" in body
        assert body["status"] == "resolved"
        assert body["category"] == "password_reset"
        assert body["confidence"] == 0.92

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
        self, auth_client, mock_run_ticket, sample_ticket_payload
    ) -> None:
        """Ticket appears in the list after submission."""
        auth_client.post("/tickets", json=sample_ticket_payload)
        r = auth_client.get("/tickets/")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_ticket_success(
        self, auth_client, mock_run_ticket, sample_ticket_payload
    ) -> None:
        """Owner can retrieve their ticket by ID."""
        create_r = auth_client.post("/tickets", json=sample_ticket_payload)
        ticket_id = create_r.json()["ticket_id"]

        r = auth_client.get(f"/tickets/{ticket_id}")
        assert r.status_code == 200
        assert r.json()["ticket_id"] == ticket_id

    def test_get_ticket_not_owned_returns_404(
        self, auth_client, mock_run_ticket, sample_ticket_payload
    ) -> None:
        """User B cannot retrieve User A's ticket — returns 404."""
        # User A (auth_client session) submits a ticket.
        create_r = auth_client.post("/tickets", json=sample_ticket_payload)
        assert create_r.status_code == 201
        ticket_id = create_r.json()["ticket_id"]

        # Register and login as User B using the same DB-overridden client.
        # Per-request Authorization headers override the session header in requests.
        auth_client.post(
            "/auth/register",
            json={"email": "userb@neuradesk.ai", "password": "password123"},
        )
        login_r = auth_client.post(
            "/auth/login",
            json={"email": "userb@neuradesk.ai", "password": "password123"},
        )
        assert login_r.status_code == 200
        token_b = login_r.json()["access_token"]

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


class TestHealth:
    """GET /health liveness probe."""

    def test_health_returns_ok(self, test_client) -> None:
        """Health endpoint returns 200 regardless of auth state."""
        r = test_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
