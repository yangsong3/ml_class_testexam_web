import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


MULTIPLE_CHOICE = "multiple_choice"
SHORT_ANSWER = "short_answer"


@dataclass(frozen=True)
class Question:
    """객관식 또는 주관식 문제 한 개를 표현한다."""

    identifier: str
    category: str
    category_name: str
    prompt: str
    question_type: str
    choices: tuple[str, ...]
    correct_choice_indices: tuple[int, ...]
    accepted_text_answers: tuple[str, ...]
    explanation: str
    image_digest: str | None = None
    choice_image_digests: tuple[str | None, ...] = ()
    prompt_document: str | None = None
    additional_image_digests: tuple[str | None, ...] = ()

    @property
    def content_image_digests(self) -> tuple[str | None, ...]:
        """본문 이미지 슬롯별 해시를 반환한다."""
        return (self.image_digest, *self.additional_image_digests)

    @property
    def is_short_answer(self) -> bool:
        """주관식 문제인지 반환한다."""
        return self.question_type == SHORT_ANSWER

    @property
    def correct_answer_text(self) -> str:
        """화면에 표시할 정답 문자열을 반환한다."""
        if self.is_short_answer:
            return " / ".join(self.accepted_text_answers)
        return ", ".join(self.choices[index] for index in self.correct_choice_indices)


@dataclass(frozen=True)
class GradeResult:
    """문제별 채점 결과를 표현한다."""

    question: Question
    selected_choice_indices: tuple[int, ...]
    submitted_text: str | None
    is_correct: bool

    @property
    def submitted_answer_text(self) -> str:
        """화면에 표시할 제출 답안 문자열을 반환한다."""
        if self.question.is_short_answer:
            return self.submitted_text or "미응답"
        if not self.selected_choice_indices:
            return "미응답"
        return ", ".join(
            self.question.choices[index]
            for index in self.selected_choice_indices
            if 0 <= index < len(self.question.choices)
        )


class JsonQuestionRepository:
    """이전용 JSON 문제를 읽고 공통 채점 기능을 제공한다."""

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
            "explanation",
        }
        if not required_fields.issubset(raw_question):
            raise RuntimeError("문제 데이터에 필수 항목이 누락되었습니다.")

        text_fields = ("id", "category", "category_name", "prompt", "explanation")
        if not all(isinstance(raw_question[field], str) for field in text_fields):
            raise RuntimeError("문제의 텍스트 항목은 문자열이어야 합니다.")

        question_type = raw_question.get("type", MULTIPLE_CHOICE)
        choices = raw_question["choices"]
        raw_answers = raw_question.get("answers")
        if raw_answers is None and "answer" in raw_question:
            raw_answers = [raw_question["answer"]]
        if question_type not in {MULTIPLE_CHOICE, SHORT_ANSWER}:
            raise RuntimeError("문제 유형이 올바르지 않습니다.")
        if not isinstance(choices, list) or not all(
            isinstance(choice, str) for choice in choices
        ):
            raise RuntimeError("선택지 데이터가 올바르지 않습니다.")
        if not isinstance(raw_answers, list) or not raw_answers:
            raise RuntimeError("정답 데이터가 올바르지 않습니다.")

        if question_type == MULTIPLE_CHOICE:
            if len(choices) < 2 or not all(choice.strip() for choice in choices):
                raise RuntimeError("객관식 선택지 데이터가 올바르지 않습니다.")
            if not all(
                type(answer) is int and answer in range(len(choices))
                for answer in raw_answers
            ):
                raise RuntimeError("객관식 정답 데이터가 올바르지 않습니다.")
            correct_choice_indices = tuple(sorted(set(raw_answers)))
            accepted_text_answers: tuple[str, ...] = ()
        else:
            if choices:
                raise RuntimeError("주관식 문제에는 선택지를 등록할 수 없습니다.")
            if not all(
                isinstance(answer, str) and answer.strip() for answer in raw_answers
            ):
                raise RuntimeError("주관식 정답 데이터가 올바르지 않습니다.")
            correct_choice_indices = ()
            accepted_text_answers = tuple(
                dict.fromkeys(answer.strip() for answer in raw_answers)
            )

        return Question(
            identifier=raw_question["id"],
            category=raw_question["category"],
            category_name=raw_question["category_name"],
            prompt=raw_question["prompt"],
            question_type=question_type,
            choices=tuple(choices),
            correct_choice_indices=correct_choice_indices,
            accepted_text_answers=accepted_text_answers,
            explanation=raw_question["explanation"],
            image_digest=None,
            choice_image_digests=tuple(None for _ in choices),
            prompt_document=None,
            additional_image_digests=(),
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
        raw_questions = [self._to_raw_question(question) for question in questions]
        temporary_path = self._question_path.with_suffix(
            f"{self._question_path.suffix}.tmp"
        )
        temporary_path.write_text(
            f"{json.dumps(raw_questions, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temporary_path.replace(self._question_path)

    @staticmethod
    def _to_raw_question(question: Question) -> dict[str, object]:
        """문제 객체를 저장 가능한 JSON 객체로 변환한다."""
        answers: list[int] | list[str]
        if question.is_short_answer:
            answers = list(question.accepted_text_answers)
        else:
            answers = list(question.correct_choice_indices)
        return {
            "id": question.identifier,
            "category": question.category,
            "category_name": question.category_name,
            "prompt": question.prompt,
            "type": question.question_type,
            "choices": list(question.choices),
            "answers": answers,
            "explanation": question.explanation,
        }

    @staticmethod
    def grade(
        questions: Sequence[Question], responses: Mapping[str, Sequence[str]]
    ) -> tuple[GradeResult, ...]:
        """제출된 답안을 문제별로 채점한다."""
        results: list[GradeResult] = []
        for question in questions:
            submitted_values = responses.get(f"answer_{question.identifier}", ())
            if question.is_short_answer:
                submitted_text = submitted_values[0].strip() if submitted_values else None
                normalized_answer = submitted_text.casefold() if submitted_text else ""
                accepted_answers = {
                    answer.casefold() for answer in question.accepted_text_answers
                }
                selected_choice_indices: tuple[int, ...] = ()
                is_correct = bool(normalized_answer) and normalized_answer in accepted_answers
            else:
                submitted_text = None
                try:
                    selected_choice_indices = tuple(
                        sorted({int(value) for value in submitted_values})
                    )
                except ValueError:
                    selected_choice_indices = ()
                valid_selection = all(
                    index in range(len(question.choices))
                    for index in selected_choice_indices
                )
                is_correct = (
                    valid_selection
                    and selected_choice_indices == question.correct_choice_indices
                )
            results.append(
                GradeResult(
                    question=question,
                    selected_choice_indices=selected_choice_indices,
                    submitted_text=submitted_text,
                    is_correct=is_correct,
                )
            )
        return tuple(results)
