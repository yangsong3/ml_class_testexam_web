import os
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

from flask import Flask

from app.admin_routes import admin
from app.routes import quiz
from app.services.login_attempt_tracker import LoginAttemptTracker
from app.services.question_repository import QuestionRepository


def create_app(test_config: Mapping[str, object] | None = None) -> Flask:
    """애플리케이션 인스턴스를 생성한다."""
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        static_folder=project_root / "static",
        template_folder=project_root / "templates",
    )
    app.config.from_mapping(
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        QUESTION_PATH=project_root / "data" / "questions.json",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        MAX_FORM_MEMORY_SIZE=64 * 1024,
    )
    if test_config is not None:
        app.config.update(test_config)

    app.config["QUESTION_REPOSITORY"] = QuestionRepository(
        Path(app.config["QUESTION_PATH"])
    )
    app.config["LOGIN_ATTEMPT_TRACKER"] = LoginAttemptTracker()
    app.register_blueprint(quiz)
    app.register_blueprint(admin)

    @app.after_request
    def add_security_headers(response):
        """브라우저 보안 응답 헤더를 추가한다."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    return app
