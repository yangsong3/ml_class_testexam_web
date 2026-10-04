import json
from dataclasses import dataclass
from typing import Any


MAX_CONTENT_IMAGES = 5
ALLOWED_INLINE_ATTRIBUTES = {"bold", "italic", "underline"}
ALLOWED_LINE_ATTRIBUTES = {"header", "list", "align"}


@dataclass(frozen=True)
class QuestionDocument:
    """검증된 문제 본문 문서와 파생 정보를 표현한다."""

    json_data: str
    plain_text: str
    image_slots: tuple[int, ...]


def validate_question_document(raw_document: str, fallback_text: str) -> QuestionDocument:
    """Quill Delta 문서를 허용된 서식과 이미지 슬롯으로 제한한다."""
    if not raw_document.strip():
        plain_text = fallback_text.strip()
        document = {"ops": [{"insert": f"{plain_text}\n"}]}
        return QuestionDocument(
            json_data=json.dumps(document, ensure_ascii=False, separators=(",", ":")),
            plain_text=plain_text,
            image_slots=(),
        )

    try:
        document = json.loads(raw_document)
    except json.JSONDecodeError as error:
        raise ValueError("문제 본문 형식이 올바르지 않습니다.") from error
    if not isinstance(document, dict) or not isinstance(document.get("ops"), list):
        raise ValueError("문제 본문 형식이 올바르지 않습니다.")

    normalized_ops: list[dict[str, Any]] = []
    text_parts: list[str] = []
    image_slots: list[int] = []
    for operation in document["ops"]:
        if not isinstance(operation, dict) or "insert" not in operation:
            raise ValueError("문제 본문에 허용되지 않은 작업이 있습니다.")
        insert = operation["insert"]
        attributes = _validate_attributes(operation.get("attributes"))
        if isinstance(insert, str):
            if "\x00" in insert:
                raise ValueError("문제 본문에 허용되지 않은 문자가 있습니다.")
            text_parts.append(insert)
            normalized = {"insert": insert}
        elif isinstance(insert, dict) and set(insert) == {"questionImage"}:
            slot = insert["questionImage"]
            if type(slot) is not int or slot not in range(MAX_CONTENT_IMAGES):
                raise ValueError("문제 이미지 위치 정보가 올바르지 않습니다.")
            if slot in image_slots:
                raise ValueError("같은 문제 이미지를 두 번 배치할 수 없습니다.")
            image_slots.append(slot)
            normalized = {"insert": {"questionImage": slot}}
        else:
            raise ValueError("문제 본문에 허용되지 않은 콘텐츠가 있습니다.")
        if attributes:
            normalized["attributes"] = attributes
        normalized_ops.append(normalized)

    plain_text = "".join(text_parts).strip()
    if not plain_text or len(plain_text) > 500:
        raise ValueError("문제 내용은 1~500자로 입력해 주세요.")
    if len(image_slots) > MAX_CONTENT_IMAGES:
        raise ValueError("문제 이미지는 최대 5개까지 사용할 수 있습니다.")
    normalized_document = {"ops": normalized_ops}
    return QuestionDocument(
        json_data=json.dumps(
            normalized_document, ensure_ascii=False, separators=(",", ":")
        ),
        plain_text=plain_text,
        image_slots=tuple(image_slots),
    )


def _validate_attributes(raw_attributes: object) -> dict[str, object]:
    """문서 서식 속성을 안전한 값으로 제한한다."""
    if raw_attributes is None:
        return {}
    if not isinstance(raw_attributes, dict):
        raise ValueError("문제 본문 서식이 올바르지 않습니다.")
    if not set(raw_attributes).issubset(
        ALLOWED_INLINE_ATTRIBUTES | ALLOWED_LINE_ATTRIBUTES
    ):
        raise ValueError("문제 본문에 허용되지 않은 서식이 있습니다.")

    attributes: dict[str, object] = {}
    for name, value in raw_attributes.items():
        if name in ALLOWED_INLINE_ATTRIBUTES and value is True:
            attributes[name] = True
        elif name == "header" and value in (1, 2, 3):
            attributes[name] = value
        elif name == "list" and value in ("ordered", "bullet"):
            attributes[name] = value
        elif name == "align" and value in ("center", "right", "justify"):
            attributes[name] = value
        else:
            raise ValueError("문제 본문 서식 값이 올바르지 않습니다.")
    return attributes
