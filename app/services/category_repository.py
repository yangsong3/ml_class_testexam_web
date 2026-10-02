import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class Category:
    """문제 분야 한 개를 표현한다."""

    identifier: str
    name: str


class CategoryRepository:
    """JSON 파일에서 문제 분야를 읽고 추가한다."""

    def __init__(self, category_path: Path, seed_path: Path) -> None:
        self._category_path = category_path
        self._write_lock = Lock()
        self._initialize_if_missing(seed_path)

    def all(self) -> tuple[Category, ...]:
        """등록된 모든 분야를 반환한다."""
        return self._load_categories(self._category_path)

    def find(self, identifier: str) -> Category | None:
        """식별자에 해당하는 분야를 반환한다."""
        return next(
            (
                category
                for category in self.all()
                if category.identifier == identifier
            ),
            None,
        )

    def add(self, category: Category) -> None:
        """새 분야를 저장한다."""
        with self._write_lock:
            categories = list(self.all())
            if any(item.identifier == category.identifier for item in categories):
                raise ValueError("이미 사용 중인 분야 ID입니다.")
            if any(item.name.casefold() == category.name.casefold() for item in categories):
                raise ValueError("이미 사용 중인 분야 이름입니다.")
            categories.append(category)
            self._write_categories(categories)

    def _initialize_if_missing(self, seed_path: Path) -> None:
        if self._category_path.exists():
            return
        with self._write_lock:
            if self._category_path.exists():
                return
            categories = self._load_categories(seed_path)
            self._category_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_categories(categories)

    @staticmethod
    def _load_categories(path: Path) -> tuple[Category, ...]:
        try:
            raw_categories = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise RuntimeError("분야 데이터 파일을 찾을 수 없습니다.") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("분야 데이터 파일의 JSON 형식이 올바르지 않습니다.") from error

        if not isinstance(raw_categories, list):
            raise RuntimeError("분야 데이터의 최상위 값은 배열이어야 합니다.")

        categories: list[Category] = []
        for raw_category in raw_categories:
            if not isinstance(raw_category, dict):
                raise RuntimeError("각 분야 데이터는 객체여야 합니다.")
            identifier = raw_category.get("id")
            name = raw_category.get("name")
            if not isinstance(identifier, str) or not isinstance(name, str):
                raise RuntimeError("분야 ID와 이름은 문자열이어야 합니다.")
            categories.append(Category(identifier=identifier, name=name))
        return tuple(categories)

    def _write_categories(self, categories: tuple[Category, ...] | list[Category]) -> None:
        raw_categories = [
            {"id": category.identifier, "name": category.name}
            for category in categories
        ]
        temporary_path = self._category_path.with_suffix(
            f"{self._category_path.suffix}.tmp"
        )
        temporary_path.write_text(
            f"{json.dumps(raw_categories, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temporary_path.replace(self._category_path)
