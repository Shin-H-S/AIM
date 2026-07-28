"""구조화 로깅과 요청 상관관계 추적.

**왜 필요한가**: 이 저장소에는 `logging.basicConfig`도 `dictConfig`도 없었다.
그래서 `app_log_level` 설정은 정의만 되고 어디서도 읽히지 않는 죽은 값이었고,
API 쪽 `logger.info(...)` 는 루트 로거 기본 레벨 때문에 아예 출력되지 않았다.
"배포 후 품질 변화를 판단해주는" 서비스가 정작 자기 장애는 `docker logs | grep`
으로 찾아야 했다.

**상관관계**: 검사 하나가 API → Celery → Worker를 지나는데 로그를 이어 붙일
키가 없었다. request_id를 컨텍스트에 실어 그 구간의 모든 로그에 자동으로 붙인다.
Celery 태스크로도 전파돼, 사용자의 한 번의 클릭이 남긴 로그를 한 키로 모을 수 있다.

의존성을 늘리지 않으려고 JSON 포매터는 직접 쓴다 — 필요한 것은 표준 필드 몇 개와
`extra`로 넘긴 도메인 식별자(project_id, check_run_id 등)를 함께 싣는 것뿐이다.
"""

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LOG_FIELD = "request_id"

# 이 구간(HTTP 요청 하나, Celery 태스크 하나)의 상관관계 id.
request_id_var: ContextVar[str | None] = ContextVar("aim_request_id", default=None)

# LogRecord의 표준 속성. JSON 출력에서 이것들을 뺀 나머지가 호출자가 extra로
# 넘긴 도메인 필드다.
_STANDARD_RECORD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime", "taskName"}


def new_request_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def request_id_context(request_id: str) -> Iterator[str]:
    """이 블록 안에서 남는 모든 로그에 request_id를 붙인다."""
    token = request_id_var.set(request_id)
    try:
        yield request_id
    finally:
        request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """모든 레코드에 현재 구간의 request_id를 채워 넣는다.

    필터로 두면 로거를 쓰는 쪽이 request_id를 몰라도 된다 — 기존 로깅 호출을
    한 줄도 고치지 않고 상관관계가 붙는다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, REQUEST_ID_LOG_FIELD):
            record.request_id = request_id_var.get()
        return True


class JsonLogFormatter(logging.Formatter):
    """한 줄에 JSON 하나. 도메인 식별자로 검색·집계할 수 있게 한다."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # extra로 넘어온 도메인 필드(project_id, check_run_id, task_id 등)를 싣는다.
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value if is_json_safe(value) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


def is_json_safe(value: object) -> bool:
    return isinstance(value, str | int | float | bool | type(None) | list | dict)


def configure_logging(log_level: str) -> None:
    """루트 로거를 JSON 출력으로 설정한다.

    uvicorn과 Celery는 각자 로깅을 건드리므로, 여기서 루트 핸들러를 교체하고
    그들 로거는 전파(propagate)만 하게 둬 출력 형식을 하나로 맞춘다.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(RequestIdFilter())

    root_logger = logging.getLogger()
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())

    # uvicorn은 자기 핸들러를 달아 두 번 찍는다. 루트로만 흘려보낸다.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
