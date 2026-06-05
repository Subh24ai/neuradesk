"""Tests for the mock IAM API endpoints (destructive identity actions)."""

import json

import services.audit_log as audit_mod


def _auth(token: str) -> dict:
    """Build an Authorization header dict for the given bearer token."""
    return {"Authorization": f"Bearer {token}"}


class TestRevokeAccess:
    """POST /iam/revoke-access."""

    def test_revoke_access_success(self, enterprise_client, enterprise_token) -> None:
        """revoke-access returns success, destructive=True, and a REV- ref."""
        r = enterprise_client.post(
            "/iam/revoke-access",
            json={"user_id": "jdoe", "resource": "vpn", "reason": "left the team"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is True
        assert body["action"] == "revoke-access"
        assert body["result"]["revoked"] is True
        assert body["result"]["resource"] == "vpn"
        assert body["result"]["ref"].startswith("REV-")
        assert "timestamp" in body


class TestLockAccount:
    """POST /iam/lock-account."""

    def test_lock_account_success(self, enterprise_client, enterprise_token) -> None:
        """lock-account returns success, destructive=True, and a LCK- ref."""
        r = enterprise_client.post(
            "/iam/lock-account",
            json={"user_id": "jdoe", "reason": "suspected compromise"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is True
        assert body["action"] == "lock-account"
        assert body["result"]["locked"] is True
        assert body["result"]["ref"].startswith("LCK-")


class TestDeleteAccount:
    """POST /iam/delete-account — body-level confirmation is mandatory."""

    def test_delete_account_without_confirm_is_rejected(self, enterprise_client, enterprise_token) -> None:
        """confirm omitted → 400 CONFIRMATION_REQUIRED."""
        r = enterprise_client.post(
            "/iam/delete-account",
            json={"user_id": "jdoe", "reason": "offboarded"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "CONFIRMATION_REQUIRED"

    def test_delete_account_confirm_false_is_rejected(self, enterprise_client, enterprise_token) -> None:
        """confirm=false → 400 CONFIRMATION_REQUIRED."""
        r = enterprise_client.post(
            "/iam/delete-account",
            json={"user_id": "jdoe", "confirm": False, "reason": "offboarded"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "CONFIRMATION_REQUIRED"

    def test_delete_account_with_confirm_succeeds(self, enterprise_client, enterprise_token) -> None:
        """confirm=true → 200 and deleted=True."""
        r = enterprise_client.post(
            "/iam/delete-account",
            json={"user_id": "jdoe", "confirm": True, "reason": "offboarded"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["destructive"] is True
        assert body["action"] == "delete-account"
        assert body["result"]["deleted"] is True
        assert body["result"]["ref"].startswith("DEL-")


class TestAuthGuard:
    """Token validation for the IAM endpoints."""

    def test_wrong_token_returns_401(self, enterprise_client) -> None:
        """Incorrect bearer token → 401."""
        r = enterprise_client.post(
            "/iam/revoke-access",
            json={"user_id": "jdoe", "resource": "vpn"},
            headers=_auth("completely-wrong-token"),
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "TOKEN_INVALID"

    def test_missing_token_returns_403(self, enterprise_client) -> None:
        """No Authorization header → 403 (HTTPBearer auto_error=True)."""
        r = enterprise_client.post("/iam/lock-account", json={"user_id": "jdoe"})
        assert r.status_code == 403


class TestAuditLog:
    """IAM calls are audited; free-text reason is redacted, resource is preserved."""

    def test_iam_call_is_audited_with_reason_redacted(
        self, enterprise_client, enterprise_token, tmp_path, monkeypatch
    ) -> None:
        """A revoke-access call writes one audit line with user_id and reason redacted."""
        audit_file = tmp_path / "test_iam_audit.jsonl"
        monkeypatch.setattr(audit_mod, "_AUDIT_FILE", audit_file)
        monkeypatch.setattr(audit_mod, "_handler", None)

        r = enterprise_client.post(
            "/iam/revoke-access",
            json={"user_id": "jdoe", "resource": "vpn", "reason": "John left the team"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 200, f"endpoint failed: {r.text}"

        assert audit_file.exists()
        raw_lines = [ln for ln in audit_file.read_text().strip().split("\n") if ln]
        assert len(raw_lines) == 1
        entry = json.loads(raw_lines[0])
        assert entry["endpoint"] == "/iam/revoke-access"
        assert entry["response_status"] == 200
        # PII redaction: user_id and reason masked; resource preserved for audit value.
        assert entry["request_body"]["user_id"] == "[REDACTED]"
        assert entry["request_body"]["reason"] == "[REDACTED]"
        assert entry["request_body"]["resource"] == "vpn"

    def test_rejected_delete_is_audited_with_400(
        self, enterprise_client, enterprise_token, tmp_path, monkeypatch
    ) -> None:
        """An unconfirmed delete still writes an audit line recording the 400."""
        audit_file = tmp_path / "test_iam_audit_400.jsonl"
        monkeypatch.setattr(audit_mod, "_AUDIT_FILE", audit_file)
        monkeypatch.setattr(audit_mod, "_handler", None)

        r = enterprise_client.post(
            "/iam/delete-account",
            json={"user_id": "jdoe", "reason": "offboarded"},
            headers=_auth(enterprise_token),
        )
        assert r.status_code == 400
        raw_lines = [ln for ln in audit_file.read_text().strip().split("\n") if ln]
        assert len(raw_lines) == 1
        entry = json.loads(raw_lines[0])
        assert entry["endpoint"] == "/iam/delete-account"
        assert entry["response_status"] == 400
