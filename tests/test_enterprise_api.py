"""Tests for the mock enterprise API endpoints and audit log."""

import json

import pytest
import services.audit_log as audit_mod


def _auth(token: str) -> dict:
    """Build an Authorization header dict for the given bearer token."""
    return {"Authorization": f"Bearer {token}"}


class TestITSM:
    """ITSM endpoint smoke tests."""

    def test_reset_password_success(self, enterprise_client, enterprise_token) -> None:
        """reset-password returns success, destructive=True, and a temp_password."""
        r = enterprise_client.post(
            "/itsm/reset-password",
            json={"user_id": "jdoe", "email": "jdoe@corp.com"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is True
        assert body["action"] == "reset-password"
        assert "temp_password" in body["result"]
        assert "timestamp" in body

    def test_provision_access_success(self, enterprise_client, enterprise_token) -> None:
        """provision-access returns success, destructive=True, and a ticket_ref."""
        r = enterprise_client.post(
            "/itsm/provision-access",
            json={"user_id": "jdoe", "resource": "github-org", "role": "member"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is True
        assert "ticket_ref" in body["result"]

    def test_create_incident_p1_routes_to_sre(self, enterprise_client, enterprise_token) -> None:
        """P1 severity incident is routed to sre-oncall."""
        r = enterprise_client.post(
            "/itsm/create-incident",
            json={"user_id": "jdoe", "description": "VPN is down", "severity": "P1"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is False
        assert body["result"]["assigned_team"] == "sre-oncall"

    def test_notify_manager_success(self, enterprise_client, enterprise_token) -> None:
        """notify-manager returns success and destructive=False."""
        r = enterprise_client.post(
            "/itsm/notify-manager",
            json={"user_id": "jdoe", "message": "Ticket resolved automatically."},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is False
        assert body["result"]["delivered"] is True


class TestHR:
    """HR endpoint smoke tests."""

    def test_approve_leave_success(self, enterprise_client, enterprise_token) -> None:
        """approve-leave returns success, destructive=False, and days_approved."""
        r = enterprise_client.post(
            "/hr/approve-leave",
            json={
                "user_id": "jdoe",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
                "days": 5,
            },
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is False
        assert body["result"]["days_approved"] == 5
        assert "approval_ref" in body["result"]


class TestAuthGuard:
    """Token validation for all enterprise endpoints."""

    def test_wrong_token_returns_401(self, enterprise_client) -> None:
        """Incorrect bearer token → 401."""
        r = enterprise_client.post(
            "/itsm/reset-password",
            json={"user_id": "jdoe", "email": "jdoe@corp.com"},
            headers=_auth("completely-wrong-token"),
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "TOKEN_INVALID"

    def test_missing_token_returns_403(self, enterprise_client) -> None:
        """No Authorization header → 403 (HTTPBearer auto_error=True)."""
        r = enterprise_client.post(
            "/itsm/reset-password",
            json={"user_id": "jdoe", "email": "jdoe@corp.com"},
        )
        assert r.status_code == 403


class TestAuditLog:
    """Async audit log write verification."""

    def test_audit_log_written_after_successful_call(
        self, enterprise_client, enterprise_token, tmp_path, monkeypatch
    ) -> None:
        """One JSON line must appear in the audit file after a successful endpoint call.

        _AUDIT_FILE is monkeypatched to a tmp path so the test is hermetic and
        does not pollute services/audit.jsonl.
        """
        audit_file = tmp_path / "test_audit.jsonl"
        monkeypatch.setattr(audit_mod, "_AUDIT_FILE", audit_file)
        monkeypatch.setattr(audit_mod, "_handler", None)

        r = enterprise_client.post(
            "/itsm/reset-password",
            json={"user_id": "jdoe", "email": "jdoe@corp.com"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200, f"endpoint failed: {r.text}"

        assert audit_file.exists(), "audit.jsonl was not created by the endpoint"
        raw_lines = [ln for ln in audit_file.read_text().strip().split("\n") if ln]
        assert len(raw_lines) == 1, f"expected 1 audit line, got {len(raw_lines)}"

        entry = json.loads(raw_lines[0])
        assert entry["endpoint"] == "/itsm/reset-password"
        assert "token_hash" in entry
        # Hash stored, NOT the raw token
        assert entry["token_hash"] != enterprise_token
        assert len(entry["token_hash"]) == 16
        assert entry["response_status"] == 200
        assert "latency_ms" in entry
        assert "request_body" in entry
        assert "timestamp" in entry
