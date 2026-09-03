"""Phase 1 queue skeleton: scans, findings, worker_heartbeat, rate_limit_hits.

Revision ID: 0001
Revises:
Create Date: 2026-09-03

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("repo_url", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("repo", sa.Text(), nullable=False),
        sa.Column("owner_token", sa.Text(), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("commit_sha", sa.Text()),
        sa.Column("default_branch", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column("score", sa.Integer()),
        sa.Column("grade", sa.CHAR(1)),
        sa.Column("score_detail", postgresql.JSONB()),
        sa.Column("summary_ko", sa.Text()),
        sa.Column("privacy_policy_md", sa.Text()),
        sa.Column("ai_notice_md", sa.Text()),
        sa.Column(
            "meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_scans_status_created_at", "scans", ["status", "created_at"])
    op.create_index(
        "ix_scans_owner_repo_finished_at",
        "scans",
        ["owner", "repo", sa.text("finished_at DESC")],
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "scan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("axis", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="app"),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("reg_rule", sa.Text()),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text()),
        sa.Column("file_path", sa.Text()),
        sa.Column("line_start", sa.Integer()),
        sa.Column("line_end", sa.Integer()),
        sa.Column("snippet", sa.Text()),
        sa.Column("title_ko", sa.Text(), nullable=False),
        sa.Column("explain_ko", sa.Text()),
        sa.Column("fix_ko", sa.Text()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_findings_scan_id", "findings", ["scan_id"])

    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "rate_limit_hits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ip", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("ip", "day"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_hits")
    op.drop_table("worker_heartbeat")
    op.drop_index("ix_findings_scan_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_scans_owner_repo_finished_at", table_name="scans")
    op.drop_index("ix_scans_status_created_at", table_name="scans")
    op.drop_table("scans")
