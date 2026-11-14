# Creates persistent HTTP request metadata storage and its chronological index.
"""Create request_logs.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


# Creates the initial request table independently of future ORM model changes.
def upgrade() -> None:
    """Create request metadata columns, constraints, and timestamp index."""
    op.create_table(
        "request_logs",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Double(), nullable=False),
        sa.Column("client_ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("http_version", sa.Text(), nullable=False),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("request_id"),
        sa.CheckConstraint("status_code BETWEEN 100 AND 599"),
        sa.CheckConstraint("duration_ms >= 0"),
    )
    op.create_index("request_logs_started_at_idx", "request_logs", ["started_at"])


# Reverses the initial schema migration when an explicit downgrade is requested.
def downgrade() -> None:
    """Remove the timestamp index and request log table, including its records."""
    op.drop_index("request_logs_started_at_idx", table_name="request_logs")
    op.drop_table("request_logs")
