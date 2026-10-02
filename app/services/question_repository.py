import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


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
        self._write_lock = Lock()

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

    def category_counts(self) -> Counter[str]:
        """분야별 문제 수를 반환한다."""
        return Counter(question.category for question in self._load_questions())

    def questions_for(self, category: str) -> tuple[Question, ...]:
        """선택한 분야의 문제를 반환한다."""
        questions = self._load_questions()
        if category == "all":
            return questions
        return tuple(question for question in questions if question.category == category)

    def find(self, identifier: str) -> Question | None:
        """식별자에 해당하는 문제를 반환한다."""
        return next(
            (
                question
                for question in self._load_questions()
                if question.identifier == identifier
            ),
            None,
        )

    def next_identifier(self, category: str) -> str:
        """분야에서 사용 중인 숫자 ID 다음 값을 반환한다."""
        identifier_pattern = re.compile(rf"^{re.escape(category)}-(\d+)$")
        numbers = [
            int(match.group(1))
            for question in self._load_questions()
            if (match := identifier_pattern.fullmatch(question.identifier))
        ]
        next_number = max(numbers, default=0) + 1
        return f"{category}-{next_number:03d}"

    def add(self, question: Question) -> None:
        """새 문제를 저장한다."""
        with self._write_lock:
            questions = list(self._load_questions())
            if any(item.identifier == question.identifier for item in questions):
                raise ValueError("이미 사용 중인 문제 ID입니다.")
            questions.append(question)
            self._write_questions(questions)

    def update(self, original_identifier: str, question: Question) -> None:
        """기존 문제를 수정한다."""
        with self._write_lock:
            questions = list(self._load_questions())
            target_index = next(
                (
                    index
                    for index, item in enumerate(questions)
                    if item.identifier == original_identifier
                ),
                None,
            )
            if target_index is None:
                raise KeyError("수정할 문제를 찾을 수 없습니다.")
            if any(
                item.identifier == question.identifier
                and item.identifier != original_identifier
                for item in questions
            ):
                raise ValueError("이미 사용 중인 문제 ID입니다.")
            questions[target_index] = question
            self._write_questions(questions)

    def delete(self, identifier: str) -> None:
        """기존 문제를 삭제한다."""
        with self._write_lock:
            questions = list(self._load_questions())
            remaining = [
                question
                for question in questions
                if question.identifier != identifier
            ]
            if len(remaining) == len(questions):
                raise KeyError("삭제할 문제를 찾을 수 없습니다.")
            self._write_questions(remaining)

    def _write_questions(self, questions: Sequence[Question]) -> None:
        raw_questions = [
            {
                "id": question.identifier,
                "category": question.category,
                "category_name": question.category_name,
                "prompt": question.prompt,
                "choices": list(question.choices),
                "answer": question.answer,
                "explanation": question.explanation,
            }
            for question in questions
        ]
        temporary_path = self._question_path.with_suffix(
            f"{self._question_path.suffix}.tmp"
        )
        temporary_path.write_text(
            f"{json.dumps(raw_questions, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temporary_path.replace(self._question_path)

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
