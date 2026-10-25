# board-server/app/__main__.py

"""
서버를 띄운다. 주소와 포트는 설정(HOST, PORT)에서 읽는다.

    uv run python -m app

compose 와 계약 시험(contract/)이 HOST, PORT 를 넘겨 이렇게 띄운다. NestJS 로 쓰던 때와 같은 이름이다.
끄라는 신호(SIGTERM)를 받으면 받는 중이던 요청을 마저 답하고 끝난다(uvicorn).
"""

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    # 접근 로그는 끈다. 요청마다의 줄은 이 서버의 미들웨어가 공통 규격으로 남긴다(docs/observability.md).
    # 응답에 서버의 이름(server: uvicorn)을 싣지 않는다. 무엇으로 돌아가는지 알리지 않는다
    uvicorn.run(
        'app.main:app',
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_config=None,
        server_header=False,
    )


if __name__ == '__main__':
    main()
