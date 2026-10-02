import argparse
import json
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Database
from app.models import CategoryModel, ChoiceModel, QuestionModel, ShortAnswerModel
from app.services.question_repository import JsonQuestionRepository


def _load_json_array(path: Path) -> list[object]:
    """JSON 배열 파일을 읽고 형식을 검사한다."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"이전할 JSON 파일을 찾을 수 없습니다: {path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"JSON 형식이 올바르지 않습니다: {path}") from error
    if not isinstance(data, list):
        raise RuntimeError(f"JSON 최상위 값은 배열이어야 합니다: {path}")
    return data


def import_json_if_empty(
    session_factory: sessionmaker[Session],
    category_path: Path,
    question_path: Path,
) -> bool:
    """빈 데이터베이스에 기존 분야와 문제 JSON을 한 번만 가져온다."""
    raw_categories = _load_json_array(category_path)
    raw_questions = _load_json_array(question_path)

    categories: list[tuple[str, str]] = []
    for raw_category in raw_categories:
        if not isinstance(raw_category, dict):
            raise RuntimeError("각 분야 데이터는 객체여야 합니다.")
        identifier = raw_category.get("id")
        name = raw_category.get("name")
        if not isinstance(identifier, str) or not isinstance(name, str):
            raise RuntimeError("분야 ID와 이름은 문자열이어야 합니다.")
        categories.append((identifier, name))

    questions = [
        JsonQuestionRepository._to_question(raw_question)
        for raw_question in raw_questions
    ]
    category_ids = {identifier for identifier, _ in categories}
    if any(question.category not in category_ids for question in questions):
        raise RuntimeError("문제에 등록되지 않은 분야가 포함되어 있습니다.")

    with session_factory() as session:
        category_count = session.scalar(select(func.count()).select_from(CategoryModel))
        question_count = session.scalar(select(func.count()).select_from(QuestionModel))
        if category_count or question_count:
            return False

        session.add_all(
            CategoryModel(identifier=identifier, name=name, sort_order=index)
            for index, (identifier, name) in enumerate(categories, start=1)
        )
        for sort_order, question in enumerate(questions, start=1):
            model = QuestionModel(
                identifier=question.identifier,
                category_id=question.category,
                prompt=question.prompt,
                question_type=question.question_type,
                explanation=question.explanation,
                sort_order=sort_order,
            )
            model.choices = [
                ChoiceModel(
                    position=index,
                    text=choice,
                    is_correct=index in question.correct_choice_indices,
                )
                for index, choice in enumerate(question.choices)
            ]
            model.short_answers = [
                ShortAnswerModel(position=index, text=answer)
                for index, answer in enumerate(question.accepted_text_answers)
            ]
            session.add(model)
        session.commit()
    return True


def _select_source(source_dirs: tuple[Path, ...]) -> tuple[Path, Path]:
    """우선순위에 따라 완전한 JSON 이전 원본을 선택한다."""
    for source_dir in source_dirs:
        category_path = source_dir / "categories.json"
        question_path = source_dir / "questions.json"
        if category_path.exists() and question_path.exists():
            return category_path, question_path
    raise RuntimeError("분야와 문제 JSON 이전 원본을 찾을 수 없습니다.")


def main() -> None:
    """명령행에서 JSON 데이터를 PostgreSQL로 이전한다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-dir", type=Path, default=Path("/app/import-data"))
    parser.add_argument("--legacy-dir", type=Path, default=Path("/app/legacy-data"))
    parser.add_argument("--seed-dir", type=Path, default=Path("/app/seed"))
    arguments = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경변수가 필요합니다.")

    category_path, question_path = _select_source(
        (arguments.import_dir, arguments.legacy_dir, arguments.seed_dir)
    )
    database = Database(database_url)
    imported = import_json_if_empty(
        database.session_factory, category_path, question_path
    )
    status = "가져오기 완료" if imported else "기존 데이터가 있어 건너뜀"
    print(f"JSON 데이터 {status}: {category_path.parent}")


if __name__ == "__main__":
    main()
