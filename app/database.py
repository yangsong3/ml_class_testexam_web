from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """데이터베이스 엔진과 세션 생성을 관리한다."""

    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if url.get_backend_name() == "sqlite":
            engine_options["connect_args"] = {"check_same_thread": False}
        else:
            engine_options.update({"pool_size": 5, "max_overflow": 2})
        self.engine: Engine = create_engine(database_url, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def dispose(self) -> None:
        """데이터베이스 연결 풀을 정리한다."""
        self.engine.dispose()
