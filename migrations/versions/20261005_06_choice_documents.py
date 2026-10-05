"""객관식 선택지 서식 문서를 추가한다.

Revision ID: 20261005_06
Revises: 20261004_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20261005_06"
down_revision = "20261004_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """선택지별 Quill Delta 문서 열을 추가한다."""
    op.add_column(
        "question_choices",
        sa.Column("text_document", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """선택지 서식 문서 열을 제거한다."""
    op.drop_column("question_choices", "text_document")
