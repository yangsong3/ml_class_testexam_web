from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.services.image_processor import QuestionImage


EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@dataclass(frozen=True)
class ImageReference:
    """데이터베이스에 저장할 이미지 파일 참조를 표현한다."""

    relative_path: str
    mime_type: str
    digest: str


@dataclass(frozen=True)
class StoredImage:
    """응답으로 전송할 검증된 이미지 파일을 표현한다."""

    path: Path
    mime_type: str
    digest: str


class ImageStorage:
    """문제 이미지를 지정된 파일 저장소에서 관리한다."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def store(self, image: QuestionImage) -> ImageReference:
        """검증된 이미지를 고유한 상대 경로에 원자적으로 저장한다."""
        extension = EXTENSIONS.get(image.mime_type)
        if extension is None:
            raise ValueError("지원하지 않는 이미지 형식입니다.")
        relative_path = Path("questions") / f"{uuid4().hex}{extension}"
        destination = self._resolve(relative_path.as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = destination.with_name(f".{destination.name}.tmp")
        try:
            temporary_path.write_bytes(image.data)
            temporary_path.replace(destination)
        except OSError as error:
            temporary_path.unlink(missing_ok=True)
            raise ValueError("이미지 파일을 서버에 저장할 수 없습니다.") from error
        return ImageReference(
            relative_path=relative_path.as_posix(),
            mime_type=image.mime_type,
            digest=image.digest,
        )

    def find(self, reference: ImageReference | None) -> StoredImage | None:
        """참조가 가리키는 저장 파일을 반환한다."""
        if reference is None:
            return None
        try:
            path = self._resolve(reference.relative_path)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return StoredImage(
            path=path,
            mime_type=reference.mime_type,
            digest=reference.digest,
        )

    def delete(self, relative_path: str | None) -> None:
        """저장소 경계 안의 이미지 파일을 삭제한다."""
        if relative_path is None:
            return
        try:
            self._resolve(relative_path).unlink(missing_ok=True)
        except (OSError, ValueError):
            return

    def _resolve(self, relative_path: str) -> Path:
        """상대 경로가 저장소 밖을 가리키지 않도록 확인한다."""
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("이미지 저장 경로가 올바르지 않습니다.")
        resolved = (self._root / candidate).resolve()
        if not resolved.is_relative_to(self._root):
            raise ValueError("이미지 저장 경로가 올바르지 않습니다.")
        return resolved
