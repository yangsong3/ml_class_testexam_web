from app import create_app


def test_home_displays_categories() -> None:
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "머신러닝 기초" in response.get_data(as_text=True)


def test_quiz_submission_returns_result() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/result",
        data={"category": "numpy", "answer_numpy-001": "1"},
    )

    assert response.status_code == 200
    assert "<strong>1</strong>문제를 맞혔어요." in response.get_data(as_text=True)
