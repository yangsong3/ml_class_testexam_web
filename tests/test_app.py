from pathlib import Path

from app import create_app
from app.database import Database
from app.json_importer import import_json_if_empty
from app.models import Base


def create_seeded_app(tmp_path: Path):
    """기본 JSON을 가져온 격리 데이터베이스 앱을 생성한다."""
    project_root = Path(__file__).resolve().parent.parent
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'app.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    import_json_if_empty(
        database.session_factory,
        project_root / "data" / "categories.json",
        project_root / "data" / "questions.json",
    )
    database.dispose()
    return create_app({"TESTING": True, "DATABASE_URL": database_url})


def test_home_displays_categories(tmp_path: Path) -> None:
    app = create_seeded_app(tmp_path)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "머신러닝 기초" in response.get_data(as_text=True)


def test_quiz_submission_returns_result(tmp_path: Path) -> None:
    app = create_seeded_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/result",
        data={"category": "numpy", "answer_numpy-001": "1"},
    )

    assert response.status_code == 200
    assert "<strong>1</strong>문제를 맞혔어요." in response.get_data(as_text=True)
