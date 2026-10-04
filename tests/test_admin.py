from pathlib import Path
from io import BytesIO

from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
from werkzeug.datastructures import MultiDict

from app import create_app
from app.database import Database
from app.json_importer import import_json_if_empty
from app.models import Base


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
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'app.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    import_json_if_empty(database.session_factory, category_path, question_path)
    database.dispose()
    return create_app(
        {
            "TESTING": True,
            "ADMIN_PASSWORD": "테스트-관리자-비밀번호",
            "SECRET_KEY": "테스트에서만-사용하는-세션-서명키",
            "SESSION_COOKIE_SECURE": False,
            "DATABASE_URL": database_url,
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


def png_upload() -> tuple[BytesIO, str]:
    """테스트용 PNG 업로드 값을 생성한다."""
    image_data = BytesIO()
    Image.new("RGB", (16, 12), "white").save(image_data, format="PNG")
    image_data.seek(0)
    return image_data, "formula.png"


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
    app = create_test_app(tmp_path)
    app.config.update(ADMIN_PASSWORD=None, SECRET_KEY=None)

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

    stored_category = app.config["CATEGORY_REPOSITORY"].find("deep-learning")
    assert stored_category is not None
    assert stored_category.name == "딥러닝"


def test_json_data_is_imported_when_database_is_empty(tmp_path: Path) -> None:
    data_path = Path(__file__).resolve().parent.parent / "data"
    question_path = tmp_path / "questions.json"
    question_path.write_text(
        (data_path / "questions.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    category_path = data_path / "categories.json"
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'import.db').as_posix()}"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)

    imported = import_json_if_empty(
        database.session_factory, category_path, question_path
    )
    imported_again = import_json_if_empty(
        database.session_factory, category_path, question_path
    )
    database.dispose()
    app = create_app({"TESTING": True, "DATABASE_URL": database_url})

    assert imported is True
    assert imported_again is False
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
    assert form_content.count("data-math-editor") == 6
    assert form_content.count('data-math-action="fraction"') == 6
    assert "실시간 미리보기" in form_content

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

    assert app.config["QUESTION_REPOSITORY"].find("numpy-999") is None


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

    repository = app.config["QUESTION_REPOSITORY"]
    stored_short_answer = repository.find("numpy-998")
    stored_multiple_choice = repository.find("numpy-997")
    assert stored_short_answer is not None
    assert stored_short_answer.question_type == "short_answer"
    assert stored_short_answer.accepted_text_answers == ("NumPy", "numpy")
    assert stored_multiple_choice is not None
    assert stored_multiple_choice.correct_choice_indices == (0, 2)


def test_admin_can_store_render_and_remove_question_image(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)
    csrf_token = get_csrf_token(client)
    form_data: dict[str, object] = question_form_data(
        csrf_token, prompt=r"다음 식 \(x^2 + 1\)을 확인하세요."
    )
    form_data["identifier"] = "basics-999"
    form_data["category"] = "basics"
    form_data["image"] = png_upload()

    create_response = client.post("/admin/questions/new", data=form_data)

    assert create_response.status_code == 302
    stored_question = app.config["QUESTION_REPOSITORY"].find("basics-999")
    assert stored_question is not None
    assert stored_question.image_digest is not None

    image_response = client.get("/questions/basics-999/image")
    assert image_response.status_code == 200
    assert image_response.content_type == "image/png"
    assert image_response.data.startswith(b"\x89PNG")
    assert image_response.headers["ETag"]
    cached_response = client.get(
        "/questions/basics-999/image",
        headers={"If-None-Match": image_response.headers["ETag"]},
    )
    assert cached_response.status_code == 304

    quiz_content = client.get("/quiz?category=basics").get_data(as_text=True)
    assert r"\(x^2 + 1\)" in quiz_content
    assert "mathjax@4.0.0/tex-chtml.js" in quiz_content
    assert "/questions/basics-999/image" in quiz_content

    retained_digest = stored_question.image_digest
    edit_data: dict[str, object] = question_form_data(
        get_csrf_token(client), prompt=r"수정된 식 \(x^2 + 1\)"
    )
    edit_data.update(
        {
            "identifier": "basics-999",
            "category": "basics",
        }
    )
    edit_response = client.post(
        "/admin/questions/basics-999/edit", data=edit_data
    )

    assert edit_response.status_code == 302
    assert (
        app.config["QUESTION_REPOSITORY"].find("basics-999").image_digest
        == retained_digest
    )

    edit_data["csrf_token"] = get_csrf_token(client)
    edit_data["remove_image"] = "1"
    remove_response = client.post(
        "/admin/questions/basics-999/edit", data=edit_data
    )

    assert remove_response.status_code == 302
    assert app.config["QUESTION_REPOSITORY"].find(
        "basics-999"
    ).image_digest is None
    assert client.get("/questions/basics-999/image").status_code == 404


def test_admin_can_store_render_and_remove_choice_images(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)
    form_data: dict[str, object] = question_form_data(get_csrf_token(client))
    form_data["identifier"] = "numpy-995"
    form_data["choice_image_0"] = png_upload()
    form_data["choice_image_2"] = png_upload()

    create_response = client.post("/admin/questions/new", data=form_data)

    assert create_response.status_code == 302
    stored_question = app.config["QUESTION_REPOSITORY"].find("numpy-995")
    assert stored_question is not None
    assert stored_question.choice_image_digests[0] is not None
    assert stored_question.choice_image_digests[1] is None
    assert stored_question.choice_image_digests[2] is not None

    image_response = client.get("/questions/numpy-995/choices/0/image")
    assert image_response.status_code == 200
    assert image_response.content_type == "image/png"
    assert image_response.headers["ETag"]
    assert client.get("/questions/numpy-995/choices/1/image").status_code == 404

    quiz_content = client.get("/quiz?category=numpy").get_data(as_text=True)
    assert "/questions/numpy-995/choices/0/image" in quiz_content
    assert "1번 선택지 참고 이미지" in quiz_content

    edit_content = client.get(
        "/admin/questions/numpy-995/edit"
    ).get_data(as_text=True)
    assert "현재 선택지 1 이미지" in edit_content
    retained_digest = stored_question.choice_image_digests[2]

    edit_data: dict[str, object] = question_form_data(get_csrf_token(client))
    edit_data["identifier"] = "numpy-995"
    edit_data["remove_choice_image_0"] = "1"
    edit_response = client.post(
        "/admin/questions/numpy-995/edit", data=edit_data
    )

    assert edit_response.status_code == 302
    updated_question = app.config["QUESTION_REPOSITORY"].find("numpy-995")
    assert updated_question is not None
    assert updated_question.choice_image_digests[0] is None
    assert updated_question.choice_image_digests[2] == retained_digest
    assert client.get("/questions/numpy-995/choices/0/image").status_code == 404


def test_admin_rejects_non_image_upload(tmp_path: Path) -> None:
    app = create_test_app(tmp_path)
    client = app.test_client()
    login(client)
    form_data: dict[str, object] = question_form_data(get_csrf_token(client))
    form_data["identifier"] = "numpy-996"
    form_data["image"] = (BytesIO(b"<svg></svg>"), "unsafe.svg")

    response = client.post("/admin/questions/new", data=form_data)

    assert response.status_code == 200
    assert "올바른 이미지 파일이 아닙니다." in response.get_data(as_text=True)
    assert app.config["QUESTION_REPOSITORY"].find("numpy-996") is None

    form_data = question_form_data(get_csrf_token(client))
    form_data["identifier"] = "numpy-995"
    form_data["choice_image_1"] = (BytesIO(b"<svg></svg>"), "unsafe.svg")

    choice_response = client.post("/admin/questions/new", data=form_data)

    assert choice_response.status_code == 200
    assert "선택지 2: 올바른 이미지 파일이 아닙니다." in choice_response.get_data(
        as_text=True
    )
    assert app.config["QUESTION_REPOSITORY"].find("numpy-995") is None
