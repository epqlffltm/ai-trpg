# chat-server/app/assets/client.py

"""
asset 서버를 부른다(asset-server/README.md 의 "다른 서버에 내주기").

    GET {ASSET_URL}/api/v1/asset/service/chat/characters/{id}/latest
    GET {ASSET_URL}/api/v1/asset/service/chat/personas/{id}
    X-Service-Signature: 이 서버의 비밀(ASSET_SECRET)로 한 서명(server_core/service_auth/signing.py)
    Authorization: Bearer <사용자의 토큰>  누구를 위해 가져가는지. asset 서버가 쓸 수 있는 사람인지 본다

답을 셋으로 나눈다. 부르는 쪽(app/conversations/service.py)이 사용자에게 무엇이라 답할지 고른다.
  - 404: 없거나, 남의 것이거나, 쓸 수 없다 -> AssetNotFoundError
  - 403 adult_content_required: 주인인데 등급을 쓸 수 없다 -> AssetAdultRequiredError
  - 그 밖(닿지 못함, 시간 초과, 401, 5xx, 모양이 틀린 답) -> AssetUnavailableError. 사용자의 잘못이 아니다
다시 시도하지 않는다. 사람이 기다리는 요청이라 실패를 바로 알리고, 사람이 다시 누른다.
이 모듈은 HTTP 를 부르고 답을 읽기만 한다. DB 를 모른다.
"""

import time
import uuid

import httpx
from pydantic import BaseModel, ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.assets.schemas import CharacterCopy, PersonaCopy

# asset 서버의 주소의 머리. 이 서버의 이름(chat)까지다. 주소까지 서명하므로 남의 이름으로 부를 수 없다
SERVICE_PATH = '/api/v1/asset/service/chat'

# 주인인데 등급을 쓸 수 없다는 답의 code(asset-server 의 app/ratings.py)
ADULT_CONTENT_REQUIRED = 'adult_content_required'


class AssetNotFoundError(Exception):
    """asset 서버가 없다고(쓸 수 없다고) 답했다."""


class AssetAdultRequiredError(Exception):
    """asset 서버가 성인 확인이 필요하다고 답했다(자기 캐릭터인데 등급을 쓸 수 없다)."""


class AssetUnavailableError(Exception):
    """asset 서버를 쓸 수 없다. 설정이 없거나, 닿지 못했거나, 알 수 없는 답이다."""


def character_path(character_id: uuid.UUID) -> str:
    """캐릭터의 마지막 판을 가져오는 주소."""
    return f'{SERVICE_PATH}/characters/{character_id}/latest'


def persona_path(persona_id: uuid.UUID) -> str:
    """페르소나의 사본을 가져오는 주소."""
    return f'{SERVICE_PATH}/personas/{persona_id}'


def signed_headers(secret: str, token: str, path: str, now: float) -> dict[str, str]:
    """서명과 사용자의 토큰을 실은 머리말. GET 이라 본문은 비어 있다."""
    return {SIGNATURE_HEADER: sign(secret, int(now), 'GET', path, b''), 'Authorization': f'Bearer {token}'}


def is_adult_required(response: httpx.Response) -> bool:
    """403 이고 code 가 adult_content_required 인가."""
    if response.status_code != httpx.codes.FORBIDDEN:
        return False
    try:
        return response.json().get('code') == ADULT_CONTENT_REQUIRED
    except (ValueError, AttributeError):
        return False


def read_answer[Model: BaseModel](response: httpx.Response, model: type[Model]) -> Model:
    """답을 그 모양으로 읽는다. 200 이 아니거나 모양이 틀리면 위의 셋 가운데 하나로 바꿔 던진다."""
    if response.status_code == httpx.codes.NOT_FOUND:
        raise AssetNotFoundError
    if is_adult_required(response):
        raise AssetAdultRequiredError
    if response.status_code != httpx.codes.OK:
        raise AssetUnavailableError(f'asset 서버가 {response.status_code} 로 답했다')
    try:
        return model.model_validate_json(response.content)
    except ValidationError as error:
        raise AssetUnavailableError('asset 서버의 답의 모양이 틀렸다') from error


class AssetClient:
    """asset 서버를 부르는 것 하나. 앱에 하나 붙여 둔다(app.state.asset). 테스트는 가짜로 바꾼다."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, secret: str, timeout: float) -> None:
        self.http = http
        self.base_url = base_url.rstrip('/')
        self.secret = secret
        self.timeout = timeout

    async def get(self, path: str, token: str) -> httpx.Response:
        """서명한 GET 을 보낸다. 설정이 없거나 닿지 못하면 AssetUnavailableError."""
        if not self.base_url:
            raise AssetUnavailableError('ASSET_URL 이 없다')
        headers = signed_headers(self.secret, token, path, time.time())
        try:
            return await self.http.get(self.base_url + path, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as error:
            raise AssetUnavailableError(f'asset 서버에 닿지 못했다({type(error).__name__})') from error

    async def fetch_character(self, token: str, character_id: uuid.UUID) -> CharacterCopy:
        """그 사람이 쓸 수 있는 캐릭터의 마지막 판."""
        return read_answer(await self.get(character_path(character_id), token), CharacterCopy)

    async def fetch_persona(self, token: str, persona_id: uuid.UUID) -> PersonaCopy:
        """그 사람의 페르소나의 사본."""
        return read_answer(await self.get(persona_path(persona_id), token), PersonaCopy)
