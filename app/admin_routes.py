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
from app.services.question_repository import Question, QuestionRepository

admin = Blueprint("admin", __name__, url_prefix="/admin")

CATEGORIES = (
    ("basics", "머신러닝 기초"),
    ("features", "데이터와 피처"),
    ("numpy", "NumPy"),
    ("pandas", "pandas"),
    ("visualization", "데이터 시각화"),
)
CATEGORY_NAMES = dict(CATEGORIES)
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,49}$")


@dataclass(frozen=True)
class QuestionFormValues:
    """검증 전후의 문제 폼 입력값을 표현한다."""

    identifier: str
    category: str
    prompt: str
    choices: tuple[str, ...]
    answer: int
    explanation: str


def get_repository() -> QuestionRepository:
    """현재 애플리케이션의 문제 저장소를 반환한다."""
    return current_app.config["QUESTION_REPOSITORY"]


def get_login_tracker() -> LoginAttemptTracker:
    """현재 애플리케이션의 로그인 실패 추적기를 반환한다."""
    return current_app.config["LOGIN_ATTEMPT_TRACKER"]


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
    """전체 문제와 관리 작업을 표시한다."""
    questions = get_repository().questions_for("all")
    return render_template("admin/questions.html", questions=questions)


@admin.route("/questions/new", methods=("GET", "POST"))
@admin_required
def create_question() -> str | Any:
    """새 문제를 입력받아 저장한다."""
    repository = get_repository()
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
                return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/question_form.html",
        page_title="문제 추가",
        question=question,
        categories=CATEGORIES,
        recommended_identifiers={
            category: repository.next_identifier(category)
            for category, _ in CATEGORIES
        },
        is_create=True,
        errors=errors,
    )


@admin.route("/questions/<identifier>/edit", methods=("GET", "POST"))
@admin_required
def edit_question(identifier: str) -> str | Any:
    """기존 문제를 수정해 저장한다."""
    repository = get_repository()
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
                return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/question_form.html",
        page_title="문제 수정",
        question=question,
        categories=CATEGORIES,
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
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/question_delete.html", question=question)


def question_from_form() -> tuple[
    Question | None, tuple[str, ...], QuestionFormValues
]:
    """관리 폼 입력을 검증하고 문제 객체로 변환한다."""
    identifier = request.form.get("identifier", "").strip()
    category = request.form.get("category", "").strip()
    prompt = request.form.get("prompt", "").strip()
    choices = tuple(
        request.form.get(f"choice_{index}", "").strip() for index in range(4)
    )
    explanation = request.form.get("explanation", "").strip()
    answer_value = request.form.get("answer", "")
    errors: list[str] = []

    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        errors.append("문제 ID는 영문 소문자, 숫자, 하이픈으로 3~50자여야 합니다.")
    if category not in CATEGORY_NAMES:
        errors.append("올바른 분야를 선택해 주세요.")
    if not prompt or len(prompt) > 500:
        errors.append("문제 내용은 1~500자로 입력해 주세요.")
    if any(not choice or len(choice) > 200 for choice in choices):
        errors.append("선택지는 각각 1~200자로 입력해 주세요.")
    if not explanation or len(explanation) > 1000:
        errors.append("해설은 1~1000자로 입력해 주세요.")

    try:
        answer = int(answer_value)
    except ValueError:
        answer = -1
    if answer not in range(len(choices)):
        errors.append("올바른 정답 번호를 선택해 주세요.")

    form_values = QuestionFormValues(
        identifier=identifier,
        category=category,
        prompt=prompt,
        choices=choices,
        answer=answer,
        explanation=explanation,
    )
    if errors:
        return None, tuple(errors), form_values

    return (
        Question(
            identifier=identifier,
            category=category,
            category_name=CATEGORY_NAMES[category],
            prompt=prompt,
            choices=choices,
            answer=answer,
            explanation=explanation,
        ),
        (),
        form_values,
    )
