"""초기 PostgreSQL 스키마를 생성한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261002_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """분야, 문제, 선택지와 주관식 정답 테이블을 생성한다."""
    op.create_table(
        "categories",
        sa.Column("identifier", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("identifier"),
    )
    op.create_index(
        "uq_categories_name_lower",
        "categories",
        [sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "questions",
        sa.Column("identifier", sa.String(length=50), nullable=False),
        sa.Column("category_id", sa.String(length=30), nullable=False),
        sa.Column("prompt", sa.String(length=500), nullable=False),
        sa.Column("question_type", sa.String(length=20), nullable=False),
        sa.Column("explanation", sa.String(length=1000), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'short_answer')",
            name="ck_questions_type",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.identifier"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("identifier"),
    )
    op.create_index(
        op.f("ix_questions_category_id"),
        "questions",
        ["category_id"],
        unique=False,
    )
    op.create_table(
        "question_choices",
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.identifier"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("identifier"),
        sa.UniqueConstraint("question_id", "position", name="uq_choice_position"),
    )
    op.create_table(
        "short_answers",
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.identifier"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("identifier"),
        sa.UniqueConstraint(
            "question_id", "position", name="uq_short_answer_position"
        ),
    )


def downgrade() -> None:
    """초기 스키마의 테이블을 역순으로 제거한다."""
    op.drop_table("short_answers")
    op.drop_table("question_choices")
    op.drop_index(op.f("ix_questions_category_id"), table_name="questions")
    op.drop_table("questions")
    op.drop_index("uq_categories_name_lower", table_name="categories")
    op.drop_table("categories")
