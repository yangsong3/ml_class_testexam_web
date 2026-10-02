import json
from pathlib import Path

from flask import Flask
from flask.testing import FlaskClient
from werkzeug.datastructures import MultiDict

from app import create_app


def copy_test_data(tmp_path: Path) -> tuple[Path, Path]:
    """격리된 문제와 분야 데이터 파일을 생성한다."""
    data_path = Path(__file__).resolve().parent.parent / "data"
    question_path = tmp_path / "questions.json"
    category_path = tmp_path / "categories.json"
    question_path.write_text(
        (data_path / "questions.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    category_path.write_text(
        (data_path / "categories.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return question_path, category_path


def create_test_app(tmp_path: Path) -> Flask:
    """격리된 데이터 파일을 사용하는 테스트 앱을 생성한다."""
    question_path, category_path = copy_test_data(tmp_path)
    return create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "테스트-관리자-비밀번호",
            "SECRET_KEY": "테스트에서만-사용하는-세션-서명키",
            "SESSION_COOKIE_SECURE": False,
            "QUESTION_PATH": question_path,
            "CATEGORY_PATH": category_path,
            "CATEGORY_SEED_PATH": category_path,
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
        "question_type": "multiple_choice",
        "choice_0": "선택지 1",
        "choice_1": "선택지 2",
        "choice_2": "선택지 3",
        "choice_3": "선택지 4",
        "answers": "2",
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
    question_path, category_path = copy_test_data(tmp_path)
    app = create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": None,
            "SECRET_KEY": None,
            "QUESTION_PATH": question_path,
            "CATEGORY_PATH": category_path,
            "CATEGORY_SEED_PATH": category_path,
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


def test_admin_can_add_category(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)

    form_response = client.get("/admin/categories/new")
    assert form_response.status_code == 200
    assert "분야 추가" in form_response.get_data(as_text=True)

    create_response = client.post(
        "/admin/categories/new",
        data={
            "csrf_token": get_csrf_token(client),
            "identifier": "deep-learning",
            "name": "딥러닝",
        },
        follow_redirects=True,
    )
    assert create_response.status_code == 200
    assert "분야를 추가했습니다." in create_response.get_data(as_text=True)

    question_form_response = client.get("/admin/questions/new")
    question_form_content = question_form_response.get_data(as_text=True)
    assert 'value="deep-learning"' in question_form_content
    assert 'data-recommended-id="deep-learning-001"' in question_form_content

    home_content = client.get("/").get_data(as_text=True)
    assert "딥러닝" in home_content
    assert "준비 중" in home_content

    json_form_content = client.get("/question-form").get_data(as_text=True)
    assert '<option value="deep-learning">딥러닝</option>' in json_form_content

    category_path = Path(app.config["CATEGORY_PATH"])
    stored_categories = json.loads(category_path.read_text(encoding="utf-8"))
    assert {"id": "deep-learning", "name": "딥러닝"} in stored_categories


def test_category_data_is_initialized_when_volume_file_is_missing(
    tmp_path: Path,
) -> None:
    data_path = Path(__file__).resolve().parent.parent / "data"
    question_path = tmp_path / "questions.json"
    question_path.write_text(
        (data_path / "questions.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    category_path = tmp_path / "volume" / "categories.json"

    app = create_app(
        {
            "TESTING": True,
            "QUESTION_PATH": question_path,
            "CATEGORY_PATH": category_path,
            "CATEGORY_SEED_PATH": data_path / "categories.json",
        }
    )

    assert category_path.exists()
    assert app.config["CATEGORY_REPOSITORY"].find("numpy") is not None


def test_admin_filters_and_paginates_questions(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)

    first_page_content = client.get("/admin").get_data(as_text=True)
    assert first_page_content.count('class="admin-question-card"') == 10
    assert "basics-001" in first_page_content
    assert "pandas-002" not in first_page_content
    assert "필터 결과 15개 중 1~10번째 문제" in first_page_content

    second_page_content = client.get("/admin?page=2").get_data(as_text=True)
    assert second_page_content.count('class="admin-question-card"') == 5
    assert "pandas-002" in second_page_content
    assert 'aria-current="page">2</a>' in second_page_content

    numpy_content = client.get("/admin?category=numpy").get_data(as_text=True)
    assert numpy_content.count('class="admin-question-card"') == 3
    assert "numpy-001" in numpy_content
    assert "basics-001" not in numpy_content
    assert "필터 결과 3개 중 1~3번째 문제" in numpy_content

    normalized_page_content = client.get("/admin?page=999").get_data(as_text=True)
    assert "pandas-002" in normalized_page_content
    assert 'aria-current="page">2</a>' in normalized_page_content

    invalid_query_content = client.get(
        "/admin?category=unknown&page=invalid"
    ).get_data(as_text=True)
    assert invalid_query_content.count('class="admin-question-card"') == 10
    assert '<option value="all" selected>전체 분야</option>' in invalid_query_content


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


def test_short_answer_and_multiple_correct_answers(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)
    csrf_token = get_csrf_token(client)

    short_answer_response = client.post(
        "/admin/questions/new",
        data={
            "csrf_token": csrf_token,
            "identifier": "numpy-998",
            "category": "numpy",
            "prompt": "넘파이의 영문 표기는?",
            "question_type": "short_answer",
            "text_answers": "NumPy\nnumpy",
            "explanation": "NumPy라고 표기합니다.",
        },
    )
    assert short_answer_response.status_code == 302

    multiple_choice_response = client.post(
        "/admin/questions/new",
        data=MultiDict(
            [
                ("csrf_token", csrf_token),
                ("identifier", "numpy-997"),
                ("category", "numpy"),
                ("prompt", "배열 연산의 특징을 모두 고르세요."),
                ("question_type", "multiple_choice"),
                ("choice_0", "벡터화 연산"),
                ("choice_1", "문자열 전용"),
                ("choice_2", "브로드캐스팅"),
                ("choice_3", "파일 저장 전용"),
                ("answers", "0"),
                ("answers", "2"),
                ("explanation", "벡터화 연산과 브로드캐스팅을 지원합니다."),
            ]
        ),
    )
    assert multiple_choice_response.status_code == 302

    quiz_content = client.get("/quiz?category=numpy").get_data(as_text=True)
    assert "주관식 답안" in quiz_content
    assert "복수 정답 문제입니다." in quiz_content
    assert 'type="checkbox" name="answer_numpy-997"' in quiz_content

    result_response = client.post(
        "/result",
        data=MultiDict(
            [
                ("category", "numpy"),
                ("answer_numpy-998", "  NUMPY  "),
                ("answer_numpy-997", "0"),
                ("answer_numpy-997", "2"),
            ]
        ),
    )
    result_content = result_response.get_data(as_text=True)
    assert result_response.status_code == 200
    assert "<strong>2</strong>문제를 맞혔어요." in result_content
    assert "벡터화 연산, 브로드캐스팅" in result_content

    partial_result = client.post(
        "/result",
        data={
            "category": "numpy",
            "answer_numpy-998": "NumPy",
            "answer_numpy-997": "0",
        },
    ).get_data(as_text=True)
    assert "<strong>1</strong>문제를 맞혔어요." in partial_result

    stored_questions = json.loads(
        Path(app.config["QUESTION_PATH"]).read_text(encoding="utf-8")
    )
    stored_short_answer = next(
        question for question in stored_questions if question["id"] == "numpy-998"
    )
    stored_multiple_choice = next(
        question for question in stored_questions if question["id"] == "numpy-997"
    )
    assert stored_short_answer["type"] == "short_answer"
    assert stored_short_answer["answers"] == ["NumPy", "numpy"]
    assert stored_multiple_choice["answers"] == [0, 2]
