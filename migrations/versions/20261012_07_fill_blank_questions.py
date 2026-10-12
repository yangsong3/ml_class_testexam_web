"""빈칸 채우기 문제 유형을 추가한다.

Revision ID: 20261012_07
Revises: 20261005_06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261012_07"
down_revision: str | None = "20261005_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """문제 유형 제약 조건과 빈칸 채우기 하위 테이블을 추가한다."""
    op.drop_constraint("ck_questions_type", "questions", type_="check")
    op.create_check_constraint(
        "ck_questions_type",
        "questions",
        "question_type IN ('multiple_choice', 'short_answer', 'fill_blank')",
    )
    op.create_table(
        "fill_blank_options",
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.identifier"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("identifier"),
        sa.UniqueConstraint(
            "question_id", "position", name="uq_fill_blank_option_position"
        ),
    )
    op.create_table(
        "fill_blank_items",
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(length=500), nullable=False),
        sa.Column("answer", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.identifier"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("identifier"),
        sa.UniqueConstraint(
            "question_id", "position", name="uq_fill_blank_item_position"
        ),
    )


def downgrade() -> None:
    """빈칸 채우기 하위 테이블과 문제 유형을 제거한다."""
    op.drop_table("fill_blank_items")
    op.drop_table("fill_blank_options")
    op.drop_constraint("ck_questions_type", "questions", type_="check")
    op.create_check_constraint(
        "ck_questions_type",
        "questions",
        "question_type IN ('multiple_choice', 'short_answer')",
    )
