import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.datastructures import FileStorage


MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIME_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class ImageValidationError(ValueError):
    """사용자에게 안내할 수 있는 이미지 검증 오류다."""


@dataclass(frozen=True)
class QuestionImage:
    """검증과 재인코딩이 완료된 문제 이미지를 표현한다."""

    data: bytes
    mime_type: str
    digest: str


def process_question_image(upload: FileStorage | None) -> QuestionImage | None:
    """업로드 이미지를 검증하고 안전한 정적 이미지로 재인코딩한다."""
    if upload is None or not upload.filename:
        return None

    raw_data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw_data) > MAX_IMAGE_BYTES:
        raise ImageValidationError("이미지는 4MB 이하로 업로드해 주세요.")
    if not raw_data:
        raise ImageValidationError("비어 있는 이미지 파일은 업로드할 수 없습니다.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw_data)) as source:
                source.verify()
            with Image.open(BytesIO(raw_data)) as source:
                if source.format not in SUPPORTED_FORMATS:
                    raise ImageValidationError(
                        "PNG, JPEG, WebP 이미지만 업로드할 수 있습니다."
                    )
                if source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ImageValidationError(
                        "이미지 해상도는 2천만 픽셀 이하여야 합니다."
                    )
                source.seek(0)
                normalized = ImageOps.exif_transpose(source).copy()
                image_format = source.format
    except ImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImageValidationError("이미지 해상도가 너무 큽니다.") from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise ImageValidationError("올바른 이미지 파일이 아닙니다.") from error

    output = BytesIO()
    try:
        if image_format == "JPEG":
            if normalized.mode not in {"RGB", "L"}:
                normalized = normalized.convert("RGB")
            normalized.save(output, format="JPEG", quality=88, optimize=True)
        elif image_format == "PNG":
            if normalized.mode not in {"RGB", "RGBA", "L", "LA"}:
                normalized = normalized.convert("RGBA")
            normalized.save(output, format="PNG", optimize=True)
        else:
            if normalized.mode not in {"RGB", "RGBA"}:
                normalized = normalized.convert("RGBA")
            normalized.save(output, format="WEBP", quality=88, method=4)
    except OSError as error:
        raise ImageValidationError("이미지를 처리할 수 없습니다.") from error

    encoded_data = output.getvalue()
    if len(encoded_data) > MAX_IMAGE_BYTES:
        raise ImageValidationError("처리된 이미지가 4MB를 초과합니다.")
    return QuestionImage(
        data=encoded_data,
        mime_type=MIME_TYPES[image_format],
        digest=hashlib.sha256(encoded_data).hexdigest(),
    )
