from flask import Blueprint, Response, abort, current_app, render_template, request, send_file

from app.services.database_repositories import CategoryRepository, QuestionRepository
from app.services.question_repository import Question

quiz = Blueprint("quiz", __name__)


def get_repository() -> QuestionRepository:
    """현재 애플리케이션의 문제 저장소를 반환한다."""
    return current_app.config["QUESTION_REPOSITORY"]


def get_category_repository() -> CategoryRepository:
    """현재 애플리케이션의 분야 저장소를 반환한다."""
    return current_app.config["CATEGORY_REPOSITORY"]


@quiz.get("/")
def home() -> str:
    """학습 분야 선택 화면을 표시한다."""
    repository = get_repository()
    counts = repository.category_counts()
    categories = tuple(
        {"id": category.identifier, "name": category.name, "count": counts[category.identifier]}
        for category in get_category_repository().all()
    )
    return render_template("home.html", categories=categories)


@quiz.get("/quiz")
def show_quiz() -> str:
    """선택한 분야의 문제를 표시한다."""
    repository = get_repository()
    categories = tuple(request.args.getlist("category"))
    if not categories and request.args.get("selection") == "1":
        abort(400)
    categories = categories or ("all",)
    questions, category_name = selected_questions(repository, categories)
    if not questions:
        abort(404)
    return render_template(
        "quiz.html",
        categories=categories,
        category_name=category_name,
        questions=questions,
    )


@quiz.post("/result")
def show_result() -> str:
    """제출 답안을 채점하고 해설을 표시한다."""
    repository = get_repository()
    categories = tuple(request.form.getlist("category")) or ("all",)
    questions, _ = selected_questions(repository, categories)
    if not questions:
        abort(404)

    responses = {key: tuple(values) for key, values in request.form.lists()}
    results = repository.grade(questions, responses)
    correct_count = sum(result.is_correct for result in results)
    return render_template(
        "result.html",
        categories=categories,
        results=results,
        correct_count=correct_count,
        total_count=len(results),
    )


def selected_questions(
    repository: QuestionRepository, categories: tuple[str, ...]
) -> tuple[tuple[Question, ...], str]:
    """선택한 분야의 문제와 표시 이름을 반환한다."""
    if categories == ("all",):
        return repository.questions_for("all"), "전체 복습"
    available = {item.identifier: item.name for item in get_category_repository().all()}
    if "all" in categories or any(category not in available for category in categories):
        abort(404)
    selected = set(categories)
    questions = tuple(
        question for question in repository.questions_for("all")
        if question.category in selected
    )
    name = ", ".join(available[category] for category in dict.fromkeys(categories))
    return questions, name


@quiz.get("/questions/<identifier>/image")
def question_image(identifier: str) -> Response:
    """문제에 등록된 이미지를 캐시 가능한 응답으로 반환한다."""
    image = get_repository().get_image(identifier)
    if image is None:
        abort(404)
    return send_file(
        image.path,
        mimetype=image.mime_type,
        conditional=True,
        etag=image.digest,
        max_age=86_400,
    )


@quiz.get("/questions/<identifier>/choices/<int:position>/image")
def choice_image(identifier: str, position: int) -> Response:
    """객관식 선택지 이미지를 캐시 가능한 응답으로 반환한다."""
    image = get_repository().get_choice_image(identifier, position)
    if image is None:
        abort(404)
    return send_file(
        image.path,
        mimetype=image.mime_type,
        conditional=True,
        etag=image.digest,
        max_age=86_400,
    )


@quiz.get("/questions/<identifier>/content-images/<int:slot>")
def content_image(identifier: str, slot: int) -> Response:
    """문제 본문 이미지 슬롯을 캐시 가능한 응답으로 반환한다."""
    image = get_repository().get_content_image(identifier, slot)
    if image is None:
        abort(404)
    return send_file(
        image.path,
        mimetype=image.mime_type,
        conditional=True,
        etag=image.digest,
        max_age=86_400,
    )


@quiz.get("/question-form")
def question_form() -> str:
    """문제 데이터 작성 양식을 표시한다."""
    return render_template(
        "question_form.html", categories=get_category_repository().all()
    )
