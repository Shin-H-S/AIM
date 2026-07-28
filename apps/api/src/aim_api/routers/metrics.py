import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from aim_api.config import get_settings
from aim_api.database import get_db
from aim_api.services.metrics import collect_metrics, render_metrics

router = APIRouter(tags=["metrics"])

# 로그인 JWT가 아니라 스크레이퍼용 정적 토큰. 프로메테우스는 사용자가 아니다.
bearer_scheme = HTTPBearer(auto_error=False)

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def metrics_not_found() -> HTTPException:
    """메트릭이 꺼져 있음을 404로 감춘다.

    401을 주면 "여기 메트릭 엔드포인트가 있다"는 사실이 새어 나간다.
    """
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.get("/metrics", response_class=Response)
def read_metrics(
    session: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Response:
    """운영 메트릭을 Prometheus 텍스트 형식으로 노출한다.

    METRICS_TOKEN이 없으면 엔드포인트 자체가 없는 것처럼 동작한다(fail-closed).
    운영 현황은 공개 정보가 아니므로, 설정하지 않은 배포에서 열려 있으면 안 된다.
    """
    expected_token = get_settings().metrics_token
    if not expected_token:
        raise metrics_not_found()

    provided_token = credentials.credentials if credentials else ""
    # 상수 시간 비교 — 토큰을 한 글자씩 맞춰 나가는 공격을 막는다.
    if not secrets.compare_digest(provided_token, expected_token):
        raise metrics_not_found()

    return Response(
        content=render_metrics(collect_metrics(session)),
        media_type=PROMETHEUS_CONTENT_TYPE,
    )
