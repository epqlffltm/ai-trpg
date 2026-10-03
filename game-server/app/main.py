# game-server/app/main.py

"""
게임 서버의 시작점. FastAPI 앱을 만들고 라우터를 붙인다.

    uv run uvicorn app.main:app --port 8001 --reload
"""

from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings

# 이 서버의 API 가 놓이는 주소. 인증 서버는 /api/v1/auth 를 쓴다
API_PREFIX = '/api/v1/game'


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    FastAPI 앱을 만들어 돌려준다.

    모듈을 불러올 때 바로 만들지 않고 함수로 둔다.
    테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title='AI TRPG 게임 서버',
        # API 문서 화면은 개발할 때만 연다. 운영 서버에서는 API 의 구조를 내보이지 않는다
        docs_url=f'{API_PREFIX}/docs' if settings.debug else None,
        redoc_url=None,
        openapi_url=f'{API_PREFIX}/openapi.json' if settings.debug else None,
    )

    # 살아 있는지 확인하는 주소는 API 주소 밖에 둔다. 프록시와 관리 도구가 부르는 것이라 버전이 없다
    app.include_router(health.router)

    return app


app = create_app()
