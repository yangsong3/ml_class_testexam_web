import re
from collections import Counter

from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.models import (
    CategoryModel,
    ChoiceModel,
    QuestionContentImageModel,
    QuestionModel,
    ShortAnswerModel,
)
from app.services.category_repository import Category
from app.services.image_processor import QuestionImage
from app.services.image_storage import ImageReference, ImageStorage, StoredImage
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
            except SQLAlchemyError as error:
                session.rollback()
                raise ValueError("이미 사용 중인 분야입니다.") from error


class QuestionRepository:
    """데이터베이스에서 문제를 조회하고 변경한다."""

    def __init__(
        self, session_factory: sessionmaker[Session], image_storage: ImageStorage
    ) -> None:
        self._session_factory = session_factory
        self._image_storage = image_storage

    @staticmethod
    def _query() -> Select[tuple[QuestionModel]]:
        return select(QuestionModel).options(
            selectinload(QuestionModel.category),
            selectinload(QuestionModel.choices),
            selectinload(QuestionModel.short_answers),
            selectinload(QuestionModel.content_images),
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
            image_digest=model.image_digest,
            choice_image_digests=tuple(choice.image_digest for choice in model.choices),
            prompt_document=model.prompt_document,
            additional_image_digests=tuple(
                next(
                    (
                        image.image_digest
                        for image in model.content_images
                        if image.slot == slot
                    ),
                    None,
                )
                for slot in range(1, 5)
            ),
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

    def add(
        self,
        question: Question,
        image: QuestionImage | None = None,
        choice_images: tuple[QuestionImage | None, ...] = (),
        additional_images: tuple[QuestionImage | None, ...] = (),
    ) -> None:
        """새 문제를 저장한다."""
        with self._session_factory() as session:
            if session.get(QuestionModel, question.identifier) is not None:
                raise ValueError("이미 사용 중인 문제 ID입니다.")
            stored_images, created_paths = self._store_images(
                (image, *choice_images, *additional_images)
            )
            stored_image = stored_images[0]
            choice_end = 1 + len(choice_images)
            stored_choice_images = stored_images[1:choice_end]
            stored_additional_images = stored_images[choice_end:]
            last_order = session.scalar(select(func.max(QuestionModel.sort_order)))
            model = self._build_model(
                question,
                (last_order or 0) + 1,
                stored_image,
                stored_choice_images,
                stored_additional_images,
            )
            session.add(model)
            try:
                session.commit()
            except SQLAlchemyError as error:
                session.rollback()
                self._delete_paths(created_paths)
                raise ValueError("문제를 저장할 수 없습니다.") from error

    def update(
        self,
        original_identifier: str,
        question: Question,
        image: QuestionImage | None = None,
        remove_image: bool = False,
        choice_images: tuple[QuestionImage | None, ...] = (),
        remove_choice_images: frozenset[int] = frozenset(),
        additional_images: tuple[QuestionImage | None, ...] = (),
        remove_content_images: frozenset[int] = frozenset(),
    ) -> None:
        """기존 문제를 수정한다."""
        with self._session_factory() as session:
            existing = session.get(QuestionModel, original_identifier)
            if existing is None:
                raise KeyError("수정할 문제를 찾을 수 없습니다.")
            duplicate = session.get(QuestionModel, question.identifier)
            if duplicate is not None and duplicate.identifier != original_identifier:
                raise ValueError("이미 사용 중인 문제 ID입니다.")

            sort_order = existing.sort_order
            previous_paths = self._model_image_paths(existing)
            uploaded_references, created_paths = self._store_images(
                (image, *choice_images, *additional_images)
            )
            stored_image = uploaded_references[0]
            choice_upload_end = 1 + len(choice_images)
            choice_uploads = uploaded_references[1:choice_upload_end]
            additional_uploads = uploaded_references[choice_upload_end:]
            if stored_image is None and not remove_image:
                stored_image = self._image_reference(
                    existing.image_path,
                    existing.image_mime_type,
                    existing.image_digest,
                )
            stored_choice_images: list[ImageReference | None] = []
            existing_choices = {choice.position: choice for choice in existing.choices}
            for position in range(len(question.choices)):
                uploaded_image = (
                    choice_uploads[position]
                    if position < len(choice_uploads)
                    else None
                )
                existing_choice = existing_choices.get(position)
                if uploaded_image is not None:
                    stored_choice_images.append(uploaded_image)
                elif (
                    position not in remove_choice_images
                    and existing_choice is not None
                ):
                    stored_choice_images.append(
                        self._image_reference(
                            existing_choice.image_path,
                            existing_choice.image_mime_type,
                            existing_choice.image_digest,
                        )
                    )
                else:
                    stored_choice_images.append(None)
            stored_additional_images: list[ImageReference | None] = []
            existing_content_images = {
                content_image.slot: content_image
                for content_image in existing.content_images
            }
            for slot in range(1, 5):
                uploaded_image = (
                    additional_uploads[slot - 1]
                    if slot - 1 < len(additional_uploads)
                    else None
                )
                existing_content_image = existing_content_images.get(slot)
                if uploaded_image is not None:
                    stored_additional_images.append(uploaded_image)
                elif (
                    slot not in remove_content_images
                    and existing_content_image is not None
                ):
                    stored_additional_images.append(
                        self._image_reference(
                            existing_content_image.image_path,
                            existing_content_image.image_mime_type,
                            existing_content_image.image_digest,
                        )
                    )
                else:
                    stored_additional_images.append(None)
            try:
                session.delete(existing)
                session.flush()
                session.add(
                    self._build_model(
                        question,
                        sort_order,
                        stored_image,
                        tuple(stored_choice_images),
                        tuple(stored_additional_images),
                    )
                )
                session.commit()
            except SQLAlchemyError as error:
                session.rollback()
                self._delete_paths(created_paths)
                raise ValueError("문제를 수정할 수 없습니다.") from error
            retained_paths = {
                reference.relative_path
                for reference in (
                    stored_image,
                    *stored_choice_images,
                    *stored_additional_images,
                )
                if reference is not None
            }
            self._delete_paths(previous_paths - retained_paths)

    def delete(self, identifier: str) -> None:
        """기존 문제를 삭제한다."""
        with self._session_factory() as session:
            model = session.get(QuestionModel, identifier)
            if model is None:
                raise KeyError("삭제할 문제를 찾을 수 없습니다.")
            image_paths = self._model_image_paths(model)
            session.delete(model)
            session.commit()
            self._delete_paths(image_paths)

    def get_image(self, identifier: str) -> StoredImage | None:
        """문제에 등록된 이미지 파일을 반환한다."""
        with self._session_factory() as session:
            model = session.get(QuestionModel, identifier)
            if model is None:
                return None
            return self._image_storage.find(
                self._image_reference(
                    model.image_path, model.image_mime_type, model.image_digest
                )
            )

    def get_choice_image(self, identifier: str, position: int) -> StoredImage | None:
        """객관식 선택지에 등록된 이미지 파일을 반환한다."""
        with self._session_factory() as session:
            model = session.scalar(
                select(ChoiceModel).where(
                    ChoiceModel.question_id == identifier,
                    ChoiceModel.position == position,
                )
            )
            if model is None:
                return None
            return self._image_storage.find(
                self._image_reference(
                    model.image_path, model.image_mime_type, model.image_digest
                )
            )

    def get_content_image(self, identifier: str, slot: int) -> StoredImage | None:
        """문제 본문의 슬롯에 등록된 이미지 파일을 반환한다."""
        if slot == 0:
            return self.get_image(identifier)
        if slot not in range(1, 5):
            return None
        with self._session_factory() as session:
            model = session.scalar(
                select(QuestionContentImageModel).where(
                    QuestionContentImageModel.question_id == identifier,
                    QuestionContentImageModel.slot == slot,
                )
            )
            if model is None:
                return None
            return self._image_storage.find(
                self._image_reference(
                    model.image_path, model.image_mime_type, model.image_digest
                )
            )

    @staticmethod
    def _build_model(
        question: Question,
        sort_order: int,
        image: ImageReference | None = None,
        choice_images: tuple[ImageReference | None, ...] = (),
        additional_images: tuple[ImageReference | None, ...] = (),
    ) -> QuestionModel:
        """도메인 문제를 데이터베이스 모델로 변환한다."""
        model = QuestionModel(
            identifier=question.identifier,
            category_id=question.category,
            prompt=question.prompt,
            prompt_document=question.prompt_document,
            question_type=question.question_type,
            explanation=question.explanation,
            sort_order=sort_order,
            image_path=image.relative_path if image else None,
            image_mime_type=image.mime_type if image else None,
            image_digest=image.digest if image else None,
        )
        model.choices = []
        for index, choice in enumerate(question.choices):
            choice_image = choice_images[index] if index < len(choice_images) else None
            model.choices.append(
                ChoiceModel(
                    position=index,
                    text=choice,
                    is_correct=index in question.correct_choice_indices,
                    image_path=choice_image.relative_path if choice_image else None,
                    image_mime_type=choice_image.mime_type if choice_image else None,
                    image_digest=choice_image.digest if choice_image else None,
                )
            )
        model.short_answers = [
            ShortAnswerModel(position=index, text=answer)
            for index, answer in enumerate(question.accepted_text_answers)
        ]
        model.content_images = [
            QuestionContentImageModel(
                slot=slot,
                image_path=content_image.relative_path,
                image_mime_type=content_image.mime_type,
                image_digest=content_image.digest,
            )
            for slot, content_image in enumerate(additional_images, start=1)
            if content_image is not None
        ]
        return model

    def _store_images(
        self, images: tuple[QuestionImage | None, ...]
    ) -> tuple[tuple[ImageReference | None, ...], list[str]]:
        """새 이미지들을 저장하고 일부 실패 시 이미 만든 파일을 정리한다."""
        references: list[ImageReference | None] = []
        created_paths: list[str] = []
        try:
            for image in images:
                if image is None:
                    references.append(None)
                    continue
                reference = self._image_storage.store(image)
                references.append(reference)
                created_paths.append(reference.relative_path)
        except ValueError:
            self._delete_paths(created_paths)
            raise
        return tuple(references), created_paths

    @staticmethod
    def _image_reference(
        path: str | None, mime_type: str | None, digest: str | None
    ) -> ImageReference | None:
        """완전한 데이터베이스 이미지 메타데이터를 참조로 변환한다."""
        if path is None or mime_type is None or digest is None:
            return None
        return ImageReference(path, mime_type, digest)

    @staticmethod
    def _model_image_paths(model: QuestionModel) -> set[str]:
        """문제 모델이 참조하는 모든 이미지 상대 경로를 반환한다."""
        paths = {model.image_path} if model.image_path else set()
        paths.update(choice.image_path for choice in model.choices if choice.image_path)
        paths.update(
            image.image_path for image in model.content_images if image.image_path
        )
        return paths

    def _delete_paths(self, paths: set[str] | list[str]) -> None:
        """여러 이미지 경로를 파일 저장소에서 제거한다."""
        for path in paths:
            self._image_storage.delete(path)

    @staticmethod
    def grade(
        questions: tuple[Question, ...], responses: dict[str, tuple[str, ...]]
    ) -> tuple[GradeResult, ...]:
        """제출된 답안을 문제별로 채점한다."""
        return JsonQuestionRepository.grade(questions, responses)
