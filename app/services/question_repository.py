import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Question:
    """객관식 문제 한 개를 표현한다."""

    identifier: str
    category: str
    category_name: str
    prompt: str
    choices: tuple[str, ...]
    answer: int
    explanation: str


@dataclass(frozen=True)
class GradeResult:
    """문제별 채점 결과를 표현한다."""

    question: Question
    selected_answer: int | None
    is_correct: bool


class QuestionRepository:
    """JSON 파일에서 문제를 읽고 채점 기능을 제공한다."""

    def __init__(self, question_path: Path) -> None:
        self._question_path = question_path

    def _load_questions(self) -> tuple[Question, ...]:
        try:
            raw_questions = json.loads(self._question_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise RuntimeError("문제 데이터 파일을 찾을 수 없습니다.") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("문제 데이터 파일의 JSON 형식이 올바르지 않습니다.") from error

        if not isinstance(raw_questions, list):
            raise RuntimeError("문제 데이터의 최상위 값은 배열이어야 합니다.")
        return tuple(self._to_question(raw_question) for raw_question in raw_questions)

    @staticmethod
    def _to_question(raw_question: object) -> Question:
        if not isinstance(raw_question, dict):
            raise RuntimeError("각 문제 데이터는 객체여야 합니다.")
        required_fields = {
            "id",
            "category",
            "category_name",
            "prompt",
            "choices",
            "answer",
            "explanation",
        }
        if not required_fields.issubset(raw_question):
            raise RuntimeError("문제 데이터에 필수 항목이 누락되었습니다.")

        choices = raw_question["choices"]
        answer = raw_question["answer"]
        if (
            not isinstance(choices, list)
            or len(choices) < 2
            or not all(isinstance(choice, str) for choice in choices)
            or not isinstance(answer, int)
            or answer not in range(len(choices))
        ):
            raise RuntimeError("선택지 또는 정답 데이터가 올바르지 않습니다.")

        text_fields = ("id", "category", "category_name", "prompt", "explanation")
        if not all(isinstance(raw_question[field], str) for field in text_fields):
            raise RuntimeError("문제의 텍스트 항목은 문자열이어야 합니다.")

        return Question(
            identifier=raw_question["id"],
            category=raw_question["category"],
            category_name=raw_question["category_name"],
            prompt=raw_question["prompt"],
            choices=tuple(choices),
            answer=answer,
            explanation=raw_question["explanation"],
        )

    def categories(self) -> tuple[dict[str, str | int], ...]:
        """분야별 문제 수를 반환한다."""
        questions = self._load_questions()
        counts = Counter(question.category for question in questions)
        names = {question.category: question.category_name for question in questions}
        return tuple(
            {"id": category, "name": names[category], "count": count}
            for category, count in counts.items()
        )

    def category_name(self, category: str) -> str:
        """분야 식별자에 해당하는 표시 이름을 반환한다."""
        if category == "all":
            return "전체 복습"
        for item in self.categories():
            if item["id"] == category:
                return str(item["name"])
        return ""

    def questions_for(self, category: str) -> tuple[Question, ...]:
        """선택한 분야의 문제를 반환한다."""
        questions = self._load_questions()
        if category == "all":
            return questions
        return tuple(question for question in questions if question.category == category)

    @staticmethod
    def grade(
        questions: Sequence[Question], responses: Mapping[str, str]
    ) -> tuple[GradeResult, ...]:
        """제출된 답안을 문제별로 채점한다."""
        results: list[GradeResult] = []
        for question in questions:
            response = responses.get(f"answer_{question.identifier}")
            try:
                selected_answer = int(response) if response is not None else None
            except ValueError:
                selected_answer = None
            results.append(
                GradeResult(
                    question=question,
                    selected_answer=selected_answer,
                    is_correct=selected_answer == question.answer,
                )
            )
        return tuple(results)
