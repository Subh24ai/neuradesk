"""Migration: add multi-tenant schema (organizations, org_configs, org_id/role on users/tickets).

Run once after deploying the multi-tenancy feature:
    python migrate_multi_tenant.py

Safe to re-run — uses IF NOT EXISTS / IF EXISTS guards throughout.
For a fresh (empty) database it drops and recreates all tables cleanly.
"""

from sqlalchemy import text

from api.models import Base, engine


def _table_is_empty(conn, table: str) -> bool:
    """Return True if the table exists and has zero rows."""
    try:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0
    except Exception:
        return True


with engine.begin() as conn:
    # Detect whether we can do a clean recreate (empty / new DB)
    users_empty = _table_is_empty(conn, "users")
    tickets_empty = _table_is_empty(conn, "tickets")

    if users_empty and tickets_empty:
        print("Empty DB detected — dropping and recreating all tables.")
        conn.execute(text("DROP TABLE IF EXISTS tickets"))
        conn.execute(text("DROP TABLE IF EXISTS users"))
        conn.execute(text("DROP TABLE IF EXISTS org_configs"))
        conn.execute(text("DROP TABLE IF EXISTS organizations"))
        print("Dropped old tables.")
    else:
        # Live DB: add columns surgically (PostgreSQL syntax)
        print("Live DB detected — adding missing columns.")
        ddl = [
            "CREATE TABLE IF NOT EXISTS organizations ("
            "  id VARCHAR(36) PRIMARY KEY,"
            "  name VARCHAR(255) NOT NULL,"
            "  slug VARCHAR(100) UNIQUE NOT NULL,"
            "  invite_code VARCHAR(32) UNIQUE NOT NULL,"
            "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            ")",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS org_id VARCHAR(36) REFERENCES organizations(id)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'member'",
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS org_id VARCHAR(36) REFERENCES organizations(id)",
        ]
        for stmt in ddl:
            conn.execute(text(stmt))
            print(f"  OK: {stmt[:70]}…")

        # Assign existing users/tickets to a default org if they have none
        no_org = conn.execute(text("SELECT COUNT(*) FROM users WHERE org_id IS NULL")).scalar()
        if no_org:
            import secrets as _secrets
            import uuid as _uuid
            default_id = str(_uuid.uuid4())
            conn.execute(text(
                "INSERT INTO organizations (id, name, slug, invite_code, created_at) VALUES "
                "(:id, 'Default Organization', 'default', :ic, NOW())"
            ), {"id": default_id, "ic": _secrets.token_urlsafe(12)})
            conn.execute(text(
                "UPDATE users SET org_id = :id, role = 'admin' WHERE org_id IS NULL"
            ), {"id": default_id})
            conn.execute(text(
                "UPDATE tickets SET org_id = (SELECT org_id FROM users WHERE users.id = tickets.user_id) "
                "WHERE org_id IS NULL"
            ))
            print(f"  Assigned {no_org} existing user(s) to default org.")

# Recreate / create all tables (creates organizations, org_configs, and any missing tables)
Base.metadata.create_all(bind=engine)
print("\nSchema up to date. Migration complete.")
