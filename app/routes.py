from flask import Blueprint, Response, abort, current_app, render_template, request

from app.services.database_repositories import CategoryRepository, QuestionRepository

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
    category = request.args.get("category", "all")
    if category == "all":
        category_name = "전체 복습"
    else:
        selected_category = get_category_repository().find(category)
        if selected_category is None:
            abort(404)
        category_name = selected_category.name
    questions = repository.questions_for(category)
    if not questions:
        abort(404)
    return render_template(
        "quiz.html",
        category=category,
        category_name=category_name,
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

    responses = {key: tuple(values) for key, values in request.form.lists()}
    results = repository.grade(questions, responses)
    correct_count = sum(result.is_correct for result in results)
    return render_template(
        "result.html",
        category=category,
        results=results,
        correct_count=correct_count,
        total_count=len(results),
    )


@quiz.get("/questions/<identifier>/image")
def question_image(identifier: str) -> Response:
    """문제에 등록된 이미지를 캐시 가능한 응답으로 반환한다."""
    image = get_repository().get_image(identifier)
    if image is None:
        abort(404)
    response = Response(image.data, mimetype=image.mime_type)
    response.set_etag(image.digest)
    response.cache_control.public = True
    response.cache_control.max_age = 86_400
    return response.make_conditional(request)


@quiz.get("/questions/<identifier>/choices/<int:position>/image")
def choice_image(identifier: str, position: int) -> Response:
    """객관식 선택지 이미지를 캐시 가능한 응답으로 반환한다."""
    image = get_repository().get_choice_image(identifier, position)
    if image is None:
        abort(404)
    response = Response(image.data, mimetype=image.mime_type)
    response.set_etag(image.digest)
    response.cache_control.public = True
    response.cache_control.max_age = 86_400
    return response.make_conditional(request)


@quiz.get("/question-form")
def question_form() -> str:
    """문제 데이터 작성 양식을 표시한다."""
    return render_template(
        "question_form.html", categories=get_category_repository().all()
    )
