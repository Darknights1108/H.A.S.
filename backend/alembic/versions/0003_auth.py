"""auth: magic-link login with email allowlist, DB sessions, audit log

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allowlist: only enabled, listed emails can receive a login credential
    op.execute(
        """
        CREATE TABLE allowed_email (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email       citext      NOT NULL UNIQUE,
            name        text,
            role        text        NOT NULL DEFAULT 'user'
                        CHECK (role IN ('admin','interviewer','lecturer','supervisor','user')),
            enabled     boolean     NOT NULL DEFAULT true,
            added_by    citext,                        -- who added it (admin email); 'bootstrap' means the system
            added_at    timestamptz NOT NULL DEFAULT now(),
            verified_at timestamptz                    -- first successful login (email ownership verified)
        )
        """
    )
    # One-time login tokens: sha256 hash only, short-lived, single-use
    op.execute(
        """
        CREATE TABLE login_token (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email      citext      NOT NULL,
            token_hash text        NOT NULL UNIQUE,
            request_ip text,
            expires_at timestamptz NOT NULL,
            used_at    timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_login_token_email_created ON login_token(email, created_at)")
    op.execute("CREATE INDEX idx_login_token_ip_created ON login_token(request_ip, created_at)")
    # Server-side sessions: the cookie holds a random value, the DB its hash; revocable anytime
    op.execute(
        """
        CREATE TABLE user_session (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash text        NOT NULL UNIQUE,
            email      citext      NOT NULL,
            role       text        NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX idx_user_session_email ON user_session(email)")
    # Audit log: login requests/successes/failures, allowlist changes
    op.execute(
        """
        CREATE TABLE auth_log (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            event      text        NOT NULL,
            email      citext,
            ip         text,
            detail     text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_auth_log_created ON auth_log(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE auth_log")
    op.execute("DROP TABLE user_session")
    op.execute("DROP TABLE login_token")
    op.execute("DROP TABLE allowed_email")
