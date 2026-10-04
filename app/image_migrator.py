import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Database
from app.models import ChoiceModel, QuestionContentImageModel, QuestionModel
from app.services.image_processor import QuestionImage
from app.services.image_storage import ImageStorage


def migrate_database_images(
    session_factory: sessionmaker[Session], image_storage: ImageStorage
) -> int:
    """데이터베이스 바이너리 이미지를 파일 저장소로 이전한다."""
    created_paths: list[str] = []
    migrated_count = 0
    with session_factory() as session:
        models = [
            *session.scalars(
                select(QuestionModel).where(QuestionModel.image_data.is_not(None))
            ),
            *session.scalars(
                select(ChoiceModel).where(ChoiceModel.image_data.is_not(None))
            ),
            *session.scalars(
                select(QuestionContentImageModel).where(
                    QuestionContentImageModel.image_data.is_not(None)
                )
            ),
        ]
        try:
            for model in models:
                if model.image_path is None:
                    reference = image_storage.store(
                        QuestionImage(
                            data=model.image_data,
                            mime_type=model.image_mime_type,
                            digest=model.image_digest,
                        )
                    )
                    model.image_path = reference.relative_path
                    created_paths.append(reference.relative_path)
                model.image_data = None
                migrated_count += 1
            session.commit()
        except (SQLAlchemyError, ValueError):
            session.rollback()
            for relative_path in created_paths:
                image_storage.delete(relative_path)
            raise
    return migrated_count


def main() -> None:
    """운영 데이터베이스의 이미지를 영속 파일 볼륨으로 이전한다."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경변수가 필요합니다.")
    storage_path = Path(os.environ.get("IMAGE_STORAGE_PATH", "/app/uploads"))
    database = Database(database_url)
    try:
        migrated_count = migrate_database_images(
            database.session_factory, ImageStorage(storage_path)
        )
    finally:
        database.dispose()
    print(f"이미지 파일 이전 완료: {migrated_count}개")


if __name__ == "__main__":
    main()
