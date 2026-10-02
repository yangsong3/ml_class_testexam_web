import re
from collections import Counter

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.models import CategoryModel, ChoiceModel, QuestionModel, ShortAnswerModel
from app.services.category_repository import Category
from app.services.question_repository import (
    GradeResult,
    JsonQuestionRepository,
    Question,
)


class CategoryRepository:
    """데이터베이스에서 문제 분야를 조회하고 추가한다."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def all(self) -> tuple[Category, ...]:
        """등록된 모든 분야를 반환한다."""
        with self._session_factory() as session:
            models = session.scalars(
                select(CategoryModel).order_by(
                    CategoryModel.sort_order, CategoryModel.identifier
                )
            ).all()
            return tuple(
                Category(identifier=model.identifier, name=model.name)
                for model in models
            )

    def find(self, identifier: str) -> Category | None:
        """식별자에 해당하는 분야를 반환한다."""
        with self._session_factory() as session:
            model = session.get(CategoryModel, identifier)
            if model is None:
                return None
            return Category(identifier=model.identifier, name=model.name)

    def add(self, category: Category) -> None:
        """새 분야를 저장한다."""
        with self._session_factory() as session:
            duplicate_name = session.scalar(
                select(CategoryModel.identifier).where(
                    func.lower(CategoryModel.name) == category.name.casefold()
                )
            )
            if session.get(CategoryModel, category.identifier) is not None:
                raise ValueError("이미 사용 중인 분야 ID입니다.")
            if duplicate_name is not None:
                raise ValueError("이미 사용 중인 분야 이름입니다.")
            last_order = session.scalar(select(func.max(CategoryModel.sort_order)))
            session.add(
                CategoryModel(
                    identifier=category.identifier,
                    name=category.name,
                    sort_order=(last_order or 0) + 1,
                )
            )
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError("이미 사용 중인 분야입니다.") from error


class QuestionRepository:
    """데이터베이스에서 문제를 조회하고 변경한다."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _query() -> Select[tuple[QuestionModel]]:
        return select(QuestionModel).options(
            selectinload(QuestionModel.category),
            selectinload(QuestionModel.choices),
            selectinload(QuestionModel.short_answers),
        )

    @staticmethod
    def _to_question(model: QuestionModel) -> Question:
        return Question(
            identifier=model.identifier,
            category=model.category_id,
            category_name=model.category.name,
            prompt=model.prompt,
            question_type=model.question_type,
            choices=tuple(choice.text for choice in model.choices),
            correct_choice_indices=tuple(
                choice.position for choice in model.choices if choice.is_correct
            ),
            accepted_text_answers=tuple(
                answer.text for answer in model.short_answers
            ),
            explanation=model.explanation,
        )

    def category_counts(self) -> Counter[str]:
        """분야별 문제 수를 반환한다."""
        with self._session_factory() as session:
            rows = session.execute(
                select(QuestionModel.category_id, func.count(QuestionModel.identifier))
                .group_by(QuestionModel.category_id)
            )
            return Counter({category: count for category, count in rows})

    def questions_for(self, category: str) -> tuple[Question, ...]:
        """선택한 분야의 문제를 반환한다."""
        query = self._query().order_by(
            QuestionModel.sort_order, QuestionModel.identifier
        )
        if category != "all":
            query = query.where(QuestionModel.category_id == category)
        with self._session_factory() as session:
            return tuple(self._to_question(model) for model in session.scalars(query))

    def find(self, identifier: str) -> Question | None:
        """식별자에 해당하는 문제를 반환한다."""
        with self._session_factory() as session:
            model = session.scalar(
                self._query().where(QuestionModel.identifier == identifier)
            )
            return self._to_question(model) if model is not None else None

    def next_identifier(self, category: str) -> str:
        """분야에서 사용 중인 숫자 ID 다음 값을 반환한다."""
        identifier_pattern = re.compile(rf"^{re.escape(category)}-(\d+)$")
        with self._session_factory() as session:
            identifiers = session.scalars(
                select(QuestionModel.identifier).where(
                    QuestionModel.category_id == category
                )
            )
            numbers = [
                int(match.group(1))
                for identifier in identifiers
                if (match := identifier_pattern.fullmatch(identifier))
            ]
        return f"{category}-{max(numbers, default=0) + 1:03d}"

    def add(self, question: Question) -> None:
        """새 문제를 저장한다."""
        with self._session_factory() as session:
            if session.get(QuestionModel, question.identifier) is not None:
                raise ValueError("이미 사용 중인 문제 ID입니다.")
            last_order = session.scalar(select(func.max(QuestionModel.sort_order)))
            model = self._build_model(question, (last_order or 0) + 1)
            session.add(model)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError("문제를 저장할 수 없습니다.") from error

    def update(self, original_identifier: str, question: Question) -> None:
        """기존 문제를 수정한다."""
        with self._session_factory() as session:
            existing = session.get(QuestionModel, original_identifier)
            if existing is None:
                raise KeyError("수정할 문제를 찾을 수 없습니다.")
            duplicate = session.get(QuestionModel, question.identifier)
            if duplicate is not None and duplicate.identifier != original_identifier:
                raise ValueError("이미 사용 중인 문제 ID입니다.")

            sort_order = existing.sort_order
            session.delete(existing)
            session.flush()
            session.add(self._build_model(question, sort_order))
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError("문제를 수정할 수 없습니다.") from error

    def delete(self, identifier: str) -> None:
        """기존 문제를 삭제한다."""
        with self._session_factory() as session:
            model = session.get(QuestionModel, identifier)
            if model is None:
                raise KeyError("삭제할 문제를 찾을 수 없습니다.")
            session.delete(model)
            session.commit()

    @staticmethod
    def _build_model(question: Question, sort_order: int) -> QuestionModel:
        """도메인 문제를 데이터베이스 모델로 변환한다."""
        model = QuestionModel(
            identifier=question.identifier,
            category_id=question.category,
            prompt=question.prompt,
            question_type=question.question_type,
            explanation=question.explanation,
            sort_order=sort_order,
        )
        model.choices = [
            ChoiceModel(
                position=index,
                text=choice,
                is_correct=index in question.correct_choice_indices,
            )
            for index, choice in enumerate(question.choices)
        ]
        model.short_answers = [
            ShortAnswerModel(position=index, text=answer)
            for index, answer in enumerate(question.accepted_text_answers)
        ]
        return model

    @staticmethod
    def grade(
        questions: tuple[Question, ...], responses: dict[str, tuple[str, ...]]
    ) -> tuple[GradeResult, ...]:
        """제출된 답안을 문제별로 채점한다."""
        return JsonQuestionRepository.grade(questions, responses)
