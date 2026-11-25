# Provisions the environment-specific runtime login and read/insert privileges.
"""Create restricted runtime access.

Revision ID: 0002
Revises: 0001
"""

import os

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.engine import make_url

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


# Creates the selected environment's login without embedding secrets in SQL previews.
def upgrade() -> None:
    """Apply identical runtime permissions to existing and future app tables."""
    environment = os.environ.get("APP_ENV", "development")
    if environment not in {"development", "production"}:
        raise ValueError("APP_ENV must be development or production")
    suffix = "PROD" if environment == "production" else "DEV"
    role = "yoink_prod_runtime" if environment == "production" else "yoink_dev_runtime"
    if not context.is_offline_mode():
        url = make_url(os.environ.get(f"DATABASE_{suffix}_URL", ""))
        if url.username != role or not url.password:
            raise ValueError(
                f"DATABASE_{suffix}_URL must contain {role} and its runtime password"
            )
        op.get_bind().execute(
            sa.text("SELECT set_config('yoink.runtime_password', :password, true)"),
            {"password": url.password},
        )
    # Role names are fixed constants, and PostgreSQL quotes the password server-side.
    op.execute(
        f"""
        DO $runtime$
        DECLARE
            runtime_password text := current_setting('yoink.runtime_password');
        BEGIN
            IF runtime_password = '' THEN
                RAISE EXCEPTION 'Set yoink.runtime_password before applying SQL';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_auth_members
                WHERE member = (SELECT oid FROM pg_roles WHERE rolname = '{role}')
            ) THEN
                RAISE EXCEPTION 'Runtime role must not belong to other roles';
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{role}'
                AND (rolsuper OR rolreplication OR rolbypassrls)
            ) THEN
                RAISE EXCEPTION 'Runtime role has elevated privileges';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role};
            END IF;
            EXECUTE format(
                'ALTER ROLE {role} LOGIN PASSWORD %L NOCREATEDB '
                'NOCREATEROLE NOINHERIT', runtime_password
            );
            EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
            EXECUTE format(
                'REVOKE ALL ON DATABASE %I FROM {role}', current_database()
            );
            EXECUTE format(
                'GRANT CONNECT ON DATABASE %I TO {role}', current_database()
            );
        END
        $runtime$;
        """
    )
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {role}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
    op.execute(f"GRANT SELECT, INSERT ON TABLE public.request_logs TO {role}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT ON TABLES TO {role}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO {role}"
    )


# Preserves credentials and access when rolling back unrelated application schemas.
def downgrade() -> None:
    """Require deliberate administrator action to remove shared cluster logins."""
    raise RuntimeError(
        "Runtime permission migration is irreversible; remove access explicitly "
        "as a database administrator"
    )
