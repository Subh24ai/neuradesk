"""One-time migration: add OTP columns to the users table.

Run once after deploying the OTP auth feature:
    python migrate_otp_columns.py
"""

from sqlalchemy import text
from api.models import engine

_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp VARCHAR(6)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP WITH TIME ZONE",
]

with engine.begin() as conn:
    for sql in _MIGRATIONS:
        conn.execute(text(sql))
        print(f"OK: {sql[:60]}…")

print("\nMigration complete.")
