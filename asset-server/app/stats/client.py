# asset-server/app/stats/client.py

"""
chat 과 story 서버에서 작품마다의 시작 수를 받아 온다(#985).

    GET {CHAT_URL}/api/v1/chat/service/stats/character-starts
    GET {STORY_URL}/api/v1/story/service/stats/world-starts
    X-Service-Signature: 그 서버가 이 서버를 부를 때와 같은 비밀(CHAT_SERVER_SECRET, STORY_SERVER_SECRET)로 한 서명

닿지 못했거나, 시간을 넘겼거나, 2xx 가 아니거나, 모양이 틀린 답이면 StatsUnavailableError 다. 다시 시도하지 않는다.
다음 바퀴에 다시 받는다(app/stats/refresher.py). 이 모듈은 HTTP 를 부르고 답을 읽기만 한다. DB 를 모른다.
"""

import time
import uuid
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.stats.models import WorkKind

# 종류마다 부르는 주소(그 서버의 app/stats/router.py)
STARTS_PATHS = {
    WorkKind.CHARACTER: '/api/v1/chat/service/stats/character-starts',
    WorkKind.WORLD: '/api/v1/story/service/stats/world-starts',
}


class StatsUnavailableError(Exception):
    """수를 받지 못했다. 까닭(reason)은 로그에만 쓴다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ReceivedStarts(BaseModel):
    """받은 작품 하나의 수."""

    work_id: uuid.UUID
    total: int
    recent: int


class ReceivedStartsList(BaseModel):
    """받은 답. 시작한 적이 있는 작품 모두다."""

    recent_days: int
    items: list[ReceivedStarts]


@dataclass(frozen=True)
class StartsSource:
    """수를 받아 오는 곳 하나. 주소와 비밀은 설정에서 온다."""

    kind: WorkKind
    base_url: str
    secret: str
    timeout: float

    async def fetch(self, client: httpx.AsyncClient) -> ReceivedStartsList:
        """한 번 받아 온다. 받지 못하면 StatsUnavailableError 다."""
        path = STARTS_PATHS[self.kind]
        headers = {SIGNATURE_HEADER: sign(self.secret, int(time.time()), 'GET', path, b'')}
        try:
            response = await client.get(f'{self.base_url.rstrip("/")}{path}', headers=headers, timeout=self.timeout)
        except httpx.HTTPError as error:
            raise StatsUnavailableError(type(error).__name__) from error
        if not response.is_success:
            raise StatsUnavailableError(f'status {response.status_code}')
        try:
            return ReceivedStartsList.model_validate_json(response.content)
        except ValidationError as error:
            raise StatsUnavailableError('malformed') from error
