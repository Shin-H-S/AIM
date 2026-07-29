"""FastAPI의 OpenAPI 스키마를 저장소에 스냅샷으로 내보낸다.

**왜 파일로 커밋하나**: 프런트의 API 타입은 이 스냅샷에서 생성된다. 스냅샷이
저장소에 있으면 CI가 두 개의 드리프트를 각각 잡을 수 있다 —

1. 백엔드를 바꾸고 스냅샷을 재생성하지 않으면 python job이 diff로 실패한다.
2. 스냅샷을 바꾸고 타입을 재생성하지 않으면 web job이 diff로 실패한다.

그 결과 백엔드 스키마 변경은 프런트 타입 변경으로 강제 전파되고, 프런트가
낡은 필드를 쓰고 있으면 tsc가 컴파일 에러로 드러낸다. 지금까지는 3,300줄의
수기 타입이 백엔드와 조용히 어긋날 수 있었다.

출력은 정렬·들여쓰기를 고정해 재생성이 결정적이게 한다 — diff 기반 가드는
바이트 단위 재현성이 전제다.
"""

import json
import sys
from pathlib import Path

from aim_api.main import app

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"


def main() -> int:
    schema = app.openapi()
    rendered = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if "--check" in sys.argv:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(
                "docs/api/openapi.json is stale. The API surface changed — regenerate with:\n"
                "  uv run python scripts/export_openapi.py\n"
                "  pnpm --filter @aim/web generate:api",
                file=sys.stderr,
            )
            return 1
        print("openapi.json matches the application.")
        return 0

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
