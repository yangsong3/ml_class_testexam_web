import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.services.login_attempt_tracker import LoginAttemptTracker
from app.services.category_repository import Category
from app.services.database_repositories import CategoryRepository, QuestionRepository
from app.services.question_repository import (
    MULTIPLE_CHOICE,
    SHORT_ANSWER,
    Question,
)

admin = Blueprint("admin", __name__, url_prefix="/admin")

IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,49}$")
CATEGORY_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,29}$")
QUESTIONS_PER_PAGE = 10


@dataclass(frozen=True)
class QuestionFormValues:
    """검증 전후의 문제 폼 입력값을 표현한다."""

    identifier: str
    category: str
    prompt: str
    question_type: str
    choices: tuple[str, ...]
    correct_choice_indices: tuple[int, ...]
    accepted_text_answers: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class QuestionPage:
    """관리 목록의 한 페이지와 이동 정보를 표현한다."""

    questions: tuple[Question, ...]
    current_page: int
    total_pages: int
    total_items: int
    start_item: int
    end_item: int
    page_numbers: tuple[int, ...]

    @property
    def has_previous(self) -> bool:
        """이전 페이지가 있는지 반환한다."""
        return self.current_page > 1

    @property
    def has_next(self) -> bool:
        """다음 페이지가 있는지 반환한다."""
        return self.current_page < self.total_pages


def get_repository() -> QuestionRepository:
    """현재 애플리케이션의 문제 저장소를 반환한다."""
    return current_app.config["QUESTION_REPOSITORY"]


def get_login_tracker() -> LoginAttemptTracker:
    """현재 애플리케이션의 로그인 실패 추적기를 반환한다."""
    return current_app.config["LOGIN_ATTEMPT_TRACKER"]


def get_category_repository() -> CategoryRepository:
    """현재 애플리케이션의 분야 저장소를 반환한다."""
    return current_app.config["CATEGORY_REPOSITORY"]


def get_category_options() -> tuple[tuple[str, str], ...]:
    """문제 폼에서 사용할 분야 선택지를 반환한다."""
    return tuple(
        (category.identifier, category.name)
        for category in get_category_repository().all()
    )


def paginate_questions(
    questions: tuple[Question, ...], page_value: str | None
) -> QuestionPage:
    """문제 목록을 유효한 페이지 범위로 나누어 반환한다."""
    try:
        requested_page = int(page_value or "1")
    except ValueError:
        requested_page = 1

    total_items = len(questions)
    total_pages = max(1, (total_items + QUESTIONS_PER_PAGE - 1) // QUESTIONS_PER_PAGE)
    current_page = min(max(requested_page, 1), total_pages)
    start_index = (current_page - 1) * QUESTIONS_PER_PAGE
    end_index = min(start_index + QUESTIONS_PER_PAGE, total_items)
    first_page_number = max(1, current_page - 2)
    last_page_number = min(total_pages, current_page + 2)
    return QuestionPage(
        questions=questions[start_index:end_index],
        current_page=current_page,
        total_pages=total_pages,
        total_items=total_items,
        start_item=start_index + 1 if total_items else 0,
        end_item=end_index,
        page_numbers=tuple(range(first_page_number, last_page_number + 1)),
    )


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    """관리자 인증이 필요한 화면을 보호한다."""

    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped_view


def csrf_token() -> str:
    """현재 세션의 CSRF 토큰을 생성하거나 반환한다."""
    token = session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf_token() -> None:
    """제출된 CSRF 토큰이 세션 값과 같은지 확인한다."""
    session_token = session.get("csrf_token")
    submitted_token = request.form.get("csrf_token", "")
    if (
        not isinstance(session_token, str)
        or not secrets.compare_digest(session_token, submitted_token)
    ):
        abort(400)


@admin.before_request
def protect_post_requests() -> None:
    """관리 기능의 모든 변경 요청에 CSRF 검증을 적용한다."""
    if request.method == "POST":
        validate_csrf_token()


@admin.context_processor
def inject_csrf_token() -> dict[str, Callable[[], str]]:
    """관리 템플릿에서 CSRF 토큰 함수를 사용하도록 제공한다."""
    return {"csrf_token": csrf_token}


@admin.route("/login", methods=("GET", "POST"))
def login() -> str | tuple[str, int] | Any:
    """관리자 비밀번호를 확인하고 세션을 시작한다."""
    configured_password = current_app.config.get("ADMIN_PASSWORD")
    if (
        not current_app.secret_key
        or not isinstance(configured_password, str)
        or len(configured_password) < 12
    ):
        return render_template("admin/login.html", configuration_error=True), 503

    if session.get("admin_authenticated"):
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        address = request.remote_addr or "unknown"
        tracker = get_login_tracker()
        if tracker.is_blocked(address):
            return render_template("admin/login.html", blocked=True), 429

        submitted_password = request.form.get("password", "")
        if secrets.compare_digest(
            configured_password.encode("utf-8"), submitted_password.encode("utf-8")
        ):
            tracker.clear(address)
            session.clear()
            session["admin_authenticated"] = True
            session.permanent = True
            return redirect(url_for("admin.dashboard"))

        tracker.record_failure(address)
        error = "비밀번호가 올바르지 않습니다."

    return render_template("admin/login.html", error=error)


@admin.post("/logout")
@admin_required
def logout() -> Any:
    """관리자 세션을 종료한다."""
    session.clear()
    return redirect(url_for("admin.login"))


@admin.get("")
@admin_required
def dashboard() -> str:
    """필터링하고 페이지를 나눈 문제 목록과 관리 작업을 표시한다."""
    repository = get_repository()
    counts = repository.category_counts()
    category_items = get_category_repository().all()
    categories = tuple(
        {
            "id": category.identifier,
            "name": category.name,
            "count": counts[category.identifier],
        }
        for category in category_items
    )
    selected_category = request.args.get("category", "all")
    valid_categories = {category.identifier for category in category_items}
    if selected_category != "all" and selected_category not in valid_categories:
        selected_category = "all"

    filtered_questions = repository.questions_for(selected_category)
    question_page = paginate_questions(filtered_questions, request.args.get("page"))
    return render_template(
        "admin/questions.html",
        questions=question_page.questions,
        categories=categories,
        selected_category=selected_category,
        question_page=question_page,
        total_question_count=sum(counts.values()),
    )


@admin.route("/categories/new", methods=("GET", "POST"))
@admin_required
def create_category() -> str | Any:
    """새 문제 분야를 입력받아 저장한다."""
    identifier = ""
    name = ""
    errors: list[str] = []
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        name = request.form.get("name", "").strip()
        if not CATEGORY_IDENTIFIER_PATTERN.fullmatch(identifier):
            errors.append("분야 ID는 영문 소문자로 시작하고 영문 소문자, 숫자, 하이픈으로 2~30자여야 합니다.")
        if not name or len(name) > 50:
            errors.append("분야 이름은 1~50자로 입력해 주세요.")

        if not errors:
            try:
                get_category_repository().add(
                    Category(identifier=identifier, name=name)
                )
            except ValueError as error:
                errors.append(str(error))
            else:
                flash("분야를 추가했습니다.", "success")
                return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/category_form.html",
        identifier=identifier,
        name=name,
        errors=tuple(errors),
    )


@admin.route("/questions/new", methods=("GET", "POST"))
@admin_required
def create_question() -> str | Any:
    """새 문제를 입력받아 저장한다."""
    repository = get_repository()
    categories = get_category_options()
    question = None
    errors: tuple[str, ...] = ()
    if request.method == "POST":
        submitted_question, errors, form_values = question_from_form()
        question = form_values
        if submitted_question is not None:
            try:
                repository.add(submitted_question)
            except ValueError as error:
                errors = (str(error),)
            else:
                flash("문제를 추가했습니다.", "success")
                return redirect(
                    url_for(
                        "admin.dashboard", category=submitted_question.category
                    )
                )

    return render_template(
        "admin/question_form.html",
        page_title="문제 추가",
        question=question,
        categories=categories,
        recommended_identifiers={
            category: repository.next_identifier(category)
            for category, _ in categories
        },
        is_create=True,
        errors=errors,
    )


@admin.route("/questions/<identifier>/edit", methods=("GET", "POST"))
@admin_required
def edit_question(identifier: str) -> str | Any:
    """기존 문제를 수정해 저장한다."""
    repository = get_repository()
    categories = get_category_options()
    existing_question = repository.find(identifier)
    if existing_question is None:
        abort(404)

    question = existing_question
    errors: tuple[str, ...] = ()
    if request.method == "POST":
        submitted_question, errors, form_values = question_from_form()
        question = form_values
        if submitted_question is not None:
            try:
                repository.update(identifier, submitted_question)
            except (KeyError, ValueError) as error:
                errors = (str(error.args[0]),)
            else:
                flash("문제를 수정했습니다.", "success")
                return redirect(
                    url_for(
                        "admin.dashboard", category=submitted_question.category
                    )
                )

    return render_template(
        "admin/question_form.html",
        page_title="문제 수정",
        question=question,
        categories=categories,
        recommended_identifiers={},
        is_create=False,
        errors=errors,
    )


@admin.route("/questions/<identifier>/delete", methods=("GET", "POST"))
@admin_required
def delete_question(identifier: str) -> str | Any:
    """삭제 확인 후 기존 문제를 제거한다."""
    repository = get_repository()
    question = repository.find(identifier)
    if question is None:
        abort(404)

    if request.method == "POST":
        try:
            repository.delete(identifier)
        except KeyError:
            abort(404)
        flash("문제를 삭제했습니다.", "success")
        return redirect(url_for("admin.dashboard", category=question.category))

    return render_template("admin/question_delete.html", question=question)


def question_from_form() -> tuple[
    Question | None, tuple[str, ...], QuestionFormValues
]:
    """관리 폼 입력을 검증하고 문제 객체로 변환한다."""
    identifier = request.form.get("identifier", "").strip()
    category = request.form.get("category", "").strip()
    prompt = request.form.get("prompt", "").strip()
    question_type = request.form.get("question_type", "").strip()
    submitted_choices = tuple(
        request.form.get(f"choice_{index}", "").strip() for index in range(4)
    )
    explanation = request.form.get("explanation", "").strip()
    errors: list[str] = []

    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        errors.append("문제 ID는 영문 소문자, 숫자, 하이픈으로 3~50자여야 합니다.")
    selected_category = get_category_repository().find(category)
    if selected_category is None:
        errors.append("올바른 분야를 선택해 주세요.")
    if not prompt or len(prompt) > 500:
        errors.append("문제 내용은 1~500자로 입력해 주세요.")
    if not explanation or len(explanation) > 1000:
        errors.append("해설은 1~1000자로 입력해 주세요.")

    correct_choice_indices: tuple[int, ...] = ()
    accepted_text_answers: tuple[str, ...] = ()
    if question_type == MULTIPLE_CHOICE:
        choices = submitted_choices
        if any(not choice or len(choice) > 200 for choice in choices):
            errors.append("객관식 선택지는 각각 1~200자로 입력해 주세요.")
        try:
            correct_choice_indices = tuple(
                sorted({int(value) for value in request.form.getlist("answers")})
            )
        except ValueError:
            correct_choice_indices = ()
        if not correct_choice_indices or any(
            answer not in range(len(choices)) for answer in correct_choice_indices
        ):
            errors.append("객관식 정답을 하나 이상 선택해 주세요.")
    elif question_type == SHORT_ANSWER:
        choices = ()
        accepted_text_answers = tuple(
            dict.fromkeys(
                line.strip()
                for line in request.form.get("text_answers", "").splitlines()
                if line.strip()
            )
        )
        if not accepted_text_answers or any(
            len(answer) > 200 for answer in accepted_text_answers
        ):
            errors.append("주관식 정답을 줄마다 1~200자로 하나 이상 입력해 주세요.")
    else:
        choices = submitted_choices
        errors.append("올바른 문제 유형을 선택해 주세요.")

    form_values = QuestionFormValues(
        identifier=identifier,
        category=category,
        prompt=prompt,
        question_type=question_type,
        choices=choices,
        correct_choice_indices=correct_choice_indices,
        accepted_text_answers=accepted_text_answers,
        explanation=explanation,
    )
    if errors:
        return None, tuple(errors), form_values

    return (
        Question(
            identifier=identifier,
            category=category,
            category_name=selected_category.name,
            prompt=prompt,
            question_type=question_type,
            choices=choices,
            correct_choice_indices=correct_choice_indices,
            accepted_text_answers=accepted_text_answers,
            explanation=explanation,
        ),
        (),
        form_values,
    )
