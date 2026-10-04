"""서식 있는 문제 본문과 추가 이미지를 저장한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261004_04"
down_revision: str | None = "20261004_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """문제 문서와 두 번째 이후 이미지 테이블을 추가한다."""
    op.add_column("questions", sa.Column("prompt_document", sa.Text(), nullable=True))
    op.create_table(
        "question_content_images",
        sa.Column("identifier", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.String(length=50), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("image_mime_type", sa.String(length=50), nullable=False),
        sa.Column("image_digest", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "slot BETWEEN 1 AND 4", name="ck_question_content_image_slot"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.identifier"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("identifier"),
        sa.UniqueConstraint(
            "question_id", "slot", name="uq_question_content_image_slot"
        ),
    )


def downgrade() -> None:
    """추가 이미지 테이블과 문제 문서 컬럼을 제거한다."""
    op.drop_table("question_content_images")
    op.drop_column("questions", "prompt_document")
