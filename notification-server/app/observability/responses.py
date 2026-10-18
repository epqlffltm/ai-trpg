# notification-server/app/observability/responses.py

"""
처리하지 못한 예외의 응답. 앱이 예외 처리기로 등록한다(app/main.py).

응답에는 무슨 일이 났는지 싣지 않는다. 예외의 글에는 쿼리와 내부 주소가 들어 있다. 그것은 로그에만 남는다
(middleware.py). 대신 요청의 식별자를 머리말로 돌려준다. 그 값으로 로그에서 이 요청의 기록을 찾는다.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.observability.identifiers import REQUEST_ID_HEADER
from app.observability.middleware import SCOPE_REQUEST_ID

# 서버의 잘못으로 처리하지 못했을 때의 문장. 다른 오류 응답과 같은 칸(detail)에 싣는다
SERVER_ERROR_DETAIL = '서버에서 오류가 났습니다. 잠시 후 다시 시도해 주세요.'


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """
    처리하지 못한 예외를 500 응답으로 바꾼다.

    이 응답은 요청 식별 미들웨어의 바깥에서 나간다. 그래서 식별자를 여기서 직접 머리말에 싣는다.
    미들웨어가 요청에 적어 둔 값을 읽는다.
    """
    request_id = request.scope.get(SCOPE_REQUEST_ID)
    headers = {REQUEST_ID_HEADER: request_id} if isinstance(request_id, str) else {}
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={'detail': SERVER_ERROR_DETAIL},
        headers=headers,
    )
