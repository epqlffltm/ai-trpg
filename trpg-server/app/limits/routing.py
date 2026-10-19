# trpg-server/app/limits/routing.py

"""
API 함수가 시도 횟수 제한을 받는 길. 앱에 꽂아 둔 것(app/main.py)을 꺼낸다.

요청마다 꺼낸다. 테스트가 제한을 바꿔 꽂으면 그 뒤의 요청부터 바뀐 것을 쓴다.
"""

from typing import Annotated

from fastapi import Depends, Request

from app.limits.setup import Limiting


def get_limiting(request: Request) -> Limiting:
    """앱에 꽂아 둔 시도 횟수 제한."""
    return request.app.state.limiting


# 시도 횟수 제한을 받는 API 가 인자의 형식으로 쓴다
Limited = Annotated[Limiting, Depends(get_limiting)]
