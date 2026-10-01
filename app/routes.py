from collections.abc import Mapping

from flask import Blueprint, abort, current_app, render_template, request

from app.services.question_repository import QuestionRepository

quiz = Blueprint("quiz", __name__)


def get_repository() -> QuestionRepository:
    """현재 애플리케이션의 문제 저장소를 반환한다."""
    return current_app.config["QUESTION_REPOSITORY"]


@quiz.get("/")
def home() -> str:
    """학습 분야 선택 화면을 표시한다."""
    repository = get_repository()
    return render_template("home.html", categories=repository.categories())


@quiz.get("/quiz")
def show_quiz() -> str:
    """선택한 분야의 문제를 표시한다."""
    repository = get_repository()
    category = request.args.get("category", "all")
    questions = repository.questions_for(category)
    if not questions:
        abort(404)
    return render_template(
        "quiz.html",
        category=category,
        category_name=repository.category_name(category),
        questions=questions,
    )


@quiz.post("/result")
def show_result() -> str:
    """제출 답안을 채점하고 해설을 표시한다."""
    repository = get_repository()
    category = request.form.get("category", "all")
    questions = repository.questions_for(category)
    if not questions:
        abort(404)

    responses: Mapping[str, str] = request.form
    results = repository.grade(questions, responses)
    correct_count = sum(result.is_correct for result in results)
    return render_template(
        "result.html",
        category=category,
        results=results,
        correct_count=correct_count,
        total_count=len(results),
    )


@quiz.get("/question-form")
def question_form() -> str:
    """문제 데이터 작성 양식을 표시한다."""
    return render_template("question_form.html")
