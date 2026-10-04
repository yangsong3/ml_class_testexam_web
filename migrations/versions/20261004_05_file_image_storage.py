"""이미지 파일 저장 경로 컬럼을 추가한다."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20261004_05"
down_revision: str | None = "20261004_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """각 이미지 테이블에 서버 파일 상대 경로를 추가한다."""
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint("ck_questions_image_complete", type_="check")
        batch_op.add_column(sa.Column("image_path", sa.String(255), nullable=True))
        batch_op.create_check_constraint(
            "ck_questions_image_complete",
            "(image_data IS NULL AND image_path IS NULL "
            "AND image_mime_type IS NULL AND image_digest IS NULL) "
            "OR ((image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
        )

    with op.batch_alter_table("question_choices") as batch_op:
        batch_op.drop_constraint(
            "ck_question_choices_image_complete", type_="check"
        )
        batch_op.add_column(sa.Column("image_path", sa.String(255), nullable=True))
        batch_op.create_check_constraint(
            "ck_question_choices_image_complete",
            "(image_data IS NULL AND image_path IS NULL "
            "AND image_mime_type IS NULL AND image_digest IS NULL) "
            "OR ((image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
        )

    with op.batch_alter_table("question_content_images") as batch_op:
        batch_op.add_column(sa.Column("image_path", sa.String(255), nullable=True))
        batch_op.alter_column("image_data", existing_type=sa.LargeBinary(), nullable=True)
        batch_op.create_check_constraint(
            "ck_question_content_images_image_complete",
            "(image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL",
        )


def downgrade() -> None:
    """파일 경로 컬럼과 새 제약 조건을 제거한다."""
    with op.batch_alter_table("question_content_images") as batch_op:
        batch_op.drop_constraint(
            "ck_question_content_images_image_complete", type_="check"
        )
        batch_op.alter_column("image_data", existing_type=sa.LargeBinary(), nullable=False)
        batch_op.drop_column("image_path")

    with op.batch_alter_table("question_choices") as batch_op:
        batch_op.drop_constraint(
            "ck_question_choices_image_complete", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_question_choices_image_complete",
            "(image_data IS NULL AND image_mime_type IS NULL "
            "AND image_digest IS NULL) OR (image_data IS NOT NULL "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
        )
        batch_op.drop_column("image_path")

    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint("ck_questions_image_complete", type_="check")
        batch_op.create_check_constraint(
            "ck_questions_image_complete",
            "(image_data IS NULL AND image_mime_type IS NULL "
            "AND image_digest IS NULL) OR (image_data IS NOT NULL "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
        )
        batch_op.drop_column("image_path")
