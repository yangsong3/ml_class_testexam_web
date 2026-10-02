from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """애플리케이션 데이터베이스 모델의 기본 클래스다."""


class CategoryModel(Base):
    """문제 분야 테이블을 표현한다."""

    __tablename__ = "categories"

    identifier: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    questions: Mapped[list[QuestionModel]] = relationship(back_populates="category")


class QuestionModel(Base):
    """문제의 공통 정보를 저장한다."""

    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('multiple_choice', 'short_answer')",
            name="ck_questions_type",
        ),
    )

    identifier: Mapped[str] = mapped_column(String(50), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.identifier", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt: Mapped[str] = mapped_column(String(500), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[CategoryModel] = relationship(back_populates="questions")
    choices: Mapped[list[ChoiceModel]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="ChoiceModel.position",
    )
    short_answers: Mapped[list[ShortAnswerModel]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="ShortAnswerModel.position",
    )


class ChoiceModel(Base):
    """객관식 선택지와 정답 여부를 저장한다."""

    __tablename__ = "question_choices"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_choice_position"),
    )

    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.identifier", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question: Mapped[QuestionModel] = relationship(back_populates="choices")


class ShortAnswerModel(Base):
    """주관식에서 허용할 정답 표현을 저장한다."""

    __tablename__ = "short_answers"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_short_answer_position"),
    )

    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.identifier", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[QuestionModel] = relationship(back_populates="short_answers")


Index("uq_categories_name_lower", func.lower(CategoryModel.name), unique=True)
