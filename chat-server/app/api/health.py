# chat-server/app/api/health.py

"""
서버 프로세스가 살아 있는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.

배포 환경의 프록시나 컨테이너 관리 도구가 주기적으로 부른다. 실패하면 관리 도구가 서버를 재시작한다.
요청을 처리할 준비가 됐는지(DB 에 닿는지)는 따로 답한다(/health/ready, DB 를 붙일 때 만든다).

HEAD 도 받는다(본문 없이 같은 상태 코드). 다른 네 서버와 같다. HEAD 로 확인하는 도구가 있다.
HEAD 는 같은 함수를 따로 등록하고 API 문서에는 올리지 않는다. GET 과 한 번에 등록하면
문서에 같은 operation id 가 두 번 올라간다. 확인 요청은 문서로 알릴 API 가 아니다.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=['health'])


class HealthResponse(BaseModel):
    status: str


@router.get('/health', response_model=HealthResponse, status_code=status.HTTP_200_OK)
@router.head('/health', status_code=status.HTTP_200_OK, include_in_schema=False)
async def check_health() -> HealthResponse:
    """
    서버 프로세스가 요청을 받을 수 있으면 200 을 돌려준다.

    DB 나 다른 서버의 상태는 보지 않는다. 그것까지 보면, DB 가 잠깐 느려졌을 때
    관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
    """
    return HealthResponse(status='ok')
