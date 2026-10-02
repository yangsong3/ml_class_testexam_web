import json
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient

from app import create_app


def create_test_app(tmp_path: Path) -> Flask:
    """격리된 문제 파일을 사용하는 테스트 앱을 생성한다."""
    source_path = Path(__file__).resolve().parent.parent / "data" / "questions.json"
    question_path = tmp_path / "questions.json"
    question_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    return create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "테스트-관리자-비밀번호",
            "SECRET_KEY": "테스트에서만-사용하는-세션-서명키",
            "SESSION_COOKIE_SECURE": False,
            "QUESTION_PATH": question_path,
        }
    )


def get_csrf_token(client: FlaskClient) -> str:
    """테스트 클라이언트 세션의 CSRF 토큰을 반환한다."""
    with client.session_transaction() as session:
        return str(session["csrf_token"])


def login(client: FlaskClient) -> None:
    """테스트 관리자로 로그인한다."""
    response = client.get("/admin/login")
    assert response.status_code == 200
    response = client.post(
        "/admin/login",
        data={
            "csrf_token": get_csrf_token(client),
            "password": "테스트-관리자-비밀번호",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "현재 15개의 문제가 등록되어 있습니다." in response.get_data(as_text=True)


def question_form_data(csrf_token: str, prompt: str = "새 문제") -> dict[str, str]:
    """관리 폼에 제출할 정상 문제 데이터를 반환한다."""
    return {
        "csrf_token": csrf_token,
        "identifier": "numpy-999",
        "category": "numpy",
        "prompt": prompt,
        "choice_0": "선택지 1",
        "choice_1": "선택지 2",
        "choice_2": "선택지 3",
        "choice_3": "선택지 4",
        "answer": "2",
        "explanation": "테스트 해설입니다.",
    }


def test_admin_requires_login_and_csrf(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()

    response = client.get("/admin")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")

    response = client.post(
        "/admin/login",
        data={"password": "테스트-관리자-비밀번호"},
    )
    assert response.status_code == 400


def test_admin_rejects_missing_configuration(tmp_path: Path) -> None:
    source_path = Path(__file__).resolve().parent.parent / "data" / "questions.json"
    question_path = tmp_path / "questions.json"
    question_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": None,
            "SECRET_KEY": None,
            "QUESTION_PATH": question_path,
        }
    )

    response = app.test_client().get("/admin/login")

    assert response.status_code == 503
    assert "관리자 인증 설정이 없거나" in response.get_data(as_text=True)


def test_admin_temporarily_blocks_repeated_login_failures(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    client.get("/admin/login")
    csrf_token = get_csrf_token(client)

    for _ in range(5):
        response = client.post(
            "/admin/login",
            data={"csrf_token": csrf_token, "password": "잘못된-비밀번호"},
        )
        assert response.status_code == 200

    blocked_response = client.post(
        "/admin/login",
        data={"csrf_token": csrf_token, "password": "테스트-관리자-비밀번호"},
    )

    assert blocked_response.status_code == 429
    assert "5분 후 다시 시도" in blocked_response.get_data(as_text=True)


def test_admin_can_create_edit_and_delete_question(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)

    form_response = client.get("/admin/questions/new")
    assert form_response.status_code == 200
    form_content = form_response.get_data(as_text=True)
    assert "문제 추가" in form_content
    assert 'value="basics-004"' in form_content
    assert 'data-recommended-id="numpy-004"' in form_content

    create_response = client.post(
        "/admin/questions/new",
        data=question_form_data(get_csrf_token(client)),
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    assert "문제를 추가했습니다." in create_response.get_data(as_text=True)

    next_form_response = client.get("/admin/questions/new")
    assert 'data-recommended-id="numpy-1000"' in next_form_response.get_data(
        as_text=True
    )

    edit_form_response = client.get("/admin/questions/numpy-999/edit")
    assert edit_form_response.status_code == 200
    assert "새 문제" in edit_form_response.get_data(as_text=True)

    edit_response = client.post(
        "/admin/questions/numpy-999/edit",
        data=question_form_data(get_csrf_token(client), prompt="수정된 문제"),
        follow_redirects=True,
    )
    assert edit_response.status_code == 200
    assert "수정된 문제" in edit_response.get_data(as_text=True)

    delete_form_response = client.get("/admin/questions/numpy-999/delete")
    assert delete_form_response.status_code == 200
    assert "이 문제를 삭제할까요?" in delete_form_response.get_data(as_text=True)

    delete_response = client.post(
        "/admin/questions/numpy-999/delete",
        data={"csrf_token": get_csrf_token(client)},
        follow_redirects=True,
    )
    assert delete_response.status_code == 200
    assert "문제를 삭제했습니다." in delete_response.get_data(as_text=True)

    question_path = Path(app.config["QUESTION_PATH"])
    stored_questions = json.loads(question_path.read_text(encoding="utf-8"))
    assert all(question["id"] != "numpy-999" for question in stored_questions)
