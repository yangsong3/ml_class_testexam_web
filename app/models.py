from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
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
        CheckConstraint(
            "(image_data IS NULL AND image_path IS NULL "
            "AND image_mime_type IS NULL AND image_digest IS NULL) "
            "OR ((image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
            name="ck_questions_image_complete",
        ),
    )

    identifier: Mapped[str] = mapped_column(String(50), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.identifier", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    prompt: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt_document: Mapped[str | None] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    image_path: Mapped[str | None] = mapped_column(String(255))
    image_mime_type: Mapped[str | None] = mapped_column(String(50))
    image_digest: Mapped[str | None] = mapped_column(String(64))
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
    content_images: Mapped[list[QuestionContentImageModel]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="QuestionContentImageModel.slot",
    )


class ChoiceModel(Base):
    """객관식 선택지와 정답 여부를 저장한다."""

    __tablename__ = "question_choices"
    __table_args__ = (
        UniqueConstraint("question_id", "position", name="uq_choice_position"),
        CheckConstraint(
            "(image_data IS NULL AND image_path IS NULL "
            "AND image_mime_type IS NULL AND image_digest IS NULL) "
            "OR ((image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL)",
            name="ck_question_choices_image_complete",
        ),
    )

    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.identifier", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    image_path: Mapped[str | None] = mapped_column(String(255))
    image_mime_type: Mapped[str | None] = mapped_column(String(50))
    image_digest: Mapped[str | None] = mapped_column(String(64))
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


class QuestionContentImageModel(Base):
    """문제 본문의 두 번째 이후 이미지를 저장한다."""

    __tablename__ = "question_content_images"
    __table_args__ = (
        UniqueConstraint("question_id", "slot", name="uq_question_content_image_slot"),
        CheckConstraint("slot BETWEEN 1 AND 4", name="ck_question_content_image_slot"),
        CheckConstraint(
            "(image_data IS NOT NULL OR image_path IS NOT NULL) "
            "AND image_mime_type IS NOT NULL AND image_digest IS NOT NULL",
            name="ck_question_content_images_image_complete",
        ),
    )

    identifier: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.identifier", ondelete="CASCADE"), nullable=False
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    image_path: Mapped[str | None] = mapped_column(String(255))
    image_mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[QuestionModel] = relationship(back_populates="content_images")


Index("uq_categories_name_lower", func.lower(CategoryModel.name), unique=True)
