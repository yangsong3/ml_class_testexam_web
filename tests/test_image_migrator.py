import hashlib
from pathlib import Path

from sqlalchemy import select

from app.database import Database
from app.image_migrator import migrate_database_images
from app.models import Base, CategoryModel, QuestionModel
from app.services.image_storage import ImageStorage


def test_database_image_is_migrated_to_file_storage(tmp_path: Path) -> None:
    """기존 데이터베이스 이미지가 파일로 이전되고 바이너리가 비워진다."""
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    image_data = b"legacy-image-data"
    digest = hashlib.sha256(image_data).hexdigest()
    with database.session_factory() as session:
        session.add(CategoryModel(identifier="numpy", name="NumPy", sort_order=1))
        session.add(
            QuestionModel(
                identifier="numpy-001",
                category_id="numpy",
                prompt="이전 문제",
                question_type="short_answer",
                explanation="이전 해설",
                image_data=image_data,
                image_mime_type="image/png",
                image_digest=digest,
                sort_order=1,
            )
        )
        session.commit()

    storage_path = tmp_path / "uploads"
    migrated_count = migrate_database_images(
        database.session_factory, ImageStorage(storage_path)
    )

    assert migrated_count == 1
    with database.session_factory() as session:
        model = session.scalar(
            select(QuestionModel).where(
                QuestionModel.identifier == "numpy-001"
            )
        )
        assert model is not None
        assert model.image_data is None
        assert model.image_path is not None
        assert (storage_path / model.image_path).read_bytes() == image_data
    database.dispose()
