# chat-server/app/billing/router.py

"""
결제 서버의 일이 실패했을 때의 응답. 앱에 한 번 등록한다(app/main.py).

  - 가격 목록을 받지 못했고 받아 둔 것도 없다(PriceListUnavailable): 503 prices_unavailable, Retry-After.
    모델 목록과 모델 고르기가 쓴다. 사용자의 잘못이 아니다. 결제 서버가 돌아오면 다음 요청에서 다시 묻는다.
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.billing.price_list import PriceListUnavailable

logger = logging.getLogger(__name__)

# 가격 목록을 받지 못했을 때 다시 해 볼 때까지의 시간(초). 화면이 이만큼 뒤에 다시 부른다
PRICES_RETRY_AFTER_SECONDS = 30


async def handle_prices_unavailable(request: Request, error: PriceListUnavailable) -> JSONResponse:
    """가격 목록을 받지 못했으면 503 이다. 까닭(unreachable, status_401 …)은 응답에 싣지 않고 로그에 남긴다."""
    logger.warning('결제 서버의 가격 목록을 받지 못했다', extra={'reason': error.reason})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            'detail': '지금은 모델의 값을 알 수 없습니다. 잠시 후 다시 시도해 주세요.',
            'code': 'prices_unavailable',
        },
        headers={'Retry-After': str(PRICES_RETRY_AFTER_SECONDS)},
    )
