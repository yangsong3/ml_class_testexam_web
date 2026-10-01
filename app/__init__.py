from pathlib import Path

from flask import Flask

from app.routes import quiz
from app.services.question_repository import QuestionRepository


def create_app() -> Flask:
    """애플리케이션 인스턴스를 생성한다."""
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        static_folder=project_root / "static",
        template_folder=project_root / "templates",
    )
    app.config["QUESTION_REPOSITORY"] = QuestionRepository(
        project_root / "data" / "questions.json"
    )
    app.register_blueprint(quiz)
    return app
