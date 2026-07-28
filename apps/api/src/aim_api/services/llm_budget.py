"""조사 에이전트의 LLM 지출 상한 — 예산 서킷브레이커.

**왜 필요한가**: 지금까지 비용 가드는 프로젝트당 30분 쿨다운 하나뿐이었다.
쿨다운은 한 프로젝트의 폭주만 막을 뿐, 프로젝트 수가 늘면 월 지출에 상한이
없다. 실측(ADR 0002)으로 83건에 $0.059라 계산은 가능했지만, **계산 가능한
것과 강제되는 것은 다르다.**

상한을 넘으면 조사를 멈추지 않는다 — 규칙 정책으로 강등해서 계속 결론을 낸다.
G4("조사는 절대 실패하지 않는다")의 폴백 구조가 이미 있으므로 연결만 하면 된다.
비용 때문에 장애 진단이 통째로 사라지는 쪽이 훨씬 나쁘다.

가격표를 앱에 두는 것은 언젠가 낡는다는 뜻이라, 설정으로 덮어쓸 수 있게 한다.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.agent_investigation import AgentInvestigation

logger = logging.getLogger(__name__)

# 백만 토큰당 USD. 조사 에이전트가 실제로 쓰는 모델만 담는다.
# 목록에 없는 모델은 0으로 세지 않고 아래 UNKNOWN_MODEL_RATE로 보수적으로 잡는다 —
# 모르는 모델을 공짜로 취급하면 상한이 조용히 무력화된다.
DEFAULT_MODEL_RATES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # model: (input, output)
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
}

# 가격표에 없는 모델의 단가 — 알려진 것 중 가장 비싼 쪽으로 가정한다.
UNKNOWN_MODEL_RATE_USD_PER_MTOK = (15.0, 75.0)

TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class BudgetStatus:
    daily_spend_usd: float
    monthly_spend_usd: float
    daily_limit_usd: float | None
    monthly_limit_usd: float | None

    @property
    def exhausted(self) -> bool:
        if self.daily_limit_usd is not None and self.daily_spend_usd >= self.daily_limit_usd:
            return True
        return (
            self.monthly_limit_usd is not None and self.monthly_spend_usd >= self.monthly_limit_usd
        )

    @property
    def reason(self) -> str | None:
        if self.daily_limit_usd is not None and self.daily_spend_usd >= self.daily_limit_usd:
            return (
                f"daily LLM budget reached: ${self.daily_spend_usd:.4f} "
                f"of ${self.daily_limit_usd:.2f}"
            )
        if self.monthly_limit_usd is not None and self.monthly_spend_usd >= self.monthly_limit_usd:
            return (
                f"monthly LLM budget reached: ${self.monthly_spend_usd:.4f} "
                f"of ${self.monthly_limit_usd:.2f}"
            )
        return None


def load_model_rates(settings: Settings) -> dict[str, tuple[float, float]]:
    """설정으로 가격표를 덮어쓴다. 단가는 앱보다 빨리 바뀐다."""
    override = settings.aim_agent_model_rates_json
    if not override:
        return DEFAULT_MODEL_RATES_USD_PER_MTOK

    try:
        parsed = json.loads(override)
        return {str(model): (float(rates[0]), float(rates[1])) for model, rates in parsed.items()}
    except (ValueError, TypeError, KeyError, IndexError):
        logger.warning(
            "AIM_AGENT_MODEL_RATES_JSON is not usable; falling back to the built-in rates."
        )
        return DEFAULT_MODEL_RATES_USD_PER_MTOK


def call_cost_usd(call: dict[str, Any], rates: dict[str, tuple[float, float]]) -> float:
    model = str(call.get("model", ""))
    input_rate, output_rate = rates.get(model, UNKNOWN_MODEL_RATE_USD_PER_MTOK)
    input_tokens = float(call.get("input_tokens", 0))
    output_tokens = float(call.get("output_tokens", 0))
    return (input_tokens * input_rate + output_tokens * output_rate) / TOKENS_PER_MILLION


def spend_since(
    session: Session,
    *,
    since: datetime,
    rates: dict[str, tuple[float, float]],
) -> float:
    """해당 시점 이후 조사들이 쓴 LLM 비용 합계(USD)."""
    total = 0.0
    for (llm_calls,) in session.execute(
        select(AgentInvestigation.llm_calls).where(AgentInvestigation.created_at >= since)
    ):
        for call in llm_calls or []:
            total += call_cost_usd(call, rates)
    return total


def get_budget_status(
    session: Session,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> BudgetStatus:
    runtime_settings = settings or get_settings()
    current_time = now or datetime.now(UTC)
    rates = load_model_rates(runtime_settings)

    return BudgetStatus(
        daily_spend_usd=spend_since(session, since=current_time - timedelta(days=1), rates=rates),
        monthly_spend_usd=spend_since(
            session, since=current_time - timedelta(days=30), rates=rates
        ),
        daily_limit_usd=runtime_settings.aim_agent_daily_budget_usd,
        monthly_limit_usd=runtime_settings.aim_agent_monthly_budget_usd,
    )
