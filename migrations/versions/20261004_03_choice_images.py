"""객관식 선택지 이미지 저장 컬럼을 추가한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261004_03"
down_revision: str | None = "20261004_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """선택지 테이블에 이미지 데이터와 캐시 식별자를 추가한다."""
    with op.batch_alter_table("question_choices") as batch_op:
        batch_op.add_column(sa.Column("image_data", sa.LargeBinary(), nullable=True))
        batch_op.add_column(
            sa.Column("image_mime_type", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column("image_digest", sa.String(length=64), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_question_choices_image_complete",
            "(image_data IS NULL AND image_mime_type IS NULL "
            "AND image_digest IS NULL) OR (image_data IS NOT NULL "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
        )


def downgrade() -> None:
    """선택지 이미지 컬럼과 제약 조건을 제거한다."""
    with op.batch_alter_table("question_choices") as batch_op:
        batch_op.drop_constraint(
            "ck_question_choices_image_complete", type_="check"
        )
        batch_op.drop_column("image_digest")
        batch_op.drop_column("image_mime_type")
        batch_op.drop_column("image_data")
