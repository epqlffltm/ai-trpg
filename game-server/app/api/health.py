# game-server/app/api/health.py

"""
서버 프로세스가 살아 있는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.

배포 환경의 프록시나 컨테이너 관리 도구가 주기적으로 부른다.
실패하면 관리 도구가 서버를 재시작한다.
요청을 처리할 준비가 됐는지(DB 에 닿는지)는 readiness.py 가 따로 답한다.

HEAD 도 받는다(본문 없이 같은 상태 코드). 네 서버가 같다. HEAD 로 확인하는 도구가 있다.
요청이 끝난 줄은 성공이면 debug 다(app/observability/middleware.py 의 probe_level_of).
"""

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=['health'])


class HealthResponse(BaseModel):
    status: str


@router.api_route('/health', methods=['GET', 'HEAD'], response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def check_health() -> HealthResponse:
    """
    서버 프로세스가 요청을 받을 수 있으면 200 을 돌려준다.

    DB 나 다른 서버의 상태는 보지 않는다. 그것까지 보면, DB 가 잠깐 느려졌을 때
    관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
    """
    return HealthResponse(status='ok')
