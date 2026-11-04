# story-server/app/assets/client.py

"""
asset 서버를 부른다(asset-server/README.md 의 "다른 서버에 내주기"). chat 서버의 것과 같은 모양이다.

    GET {ASSET_URL}/api/v1/asset/service/story/worlds/{id}/latest
    GET {ASSET_URL}/api/v1/asset/service/story/personas/{id}
    GET {ASSET_URL}/api/v1/asset/service/story/shortcuts          토큰의 주인의 단축어(#981)
    POST, DELETE {ASSET_URL}/api/v1/asset/service/story/images[/{id}]  만든 장면 그림을 맡기고 지운다(#983)
    X-Service-Signature: 이 서버의 비밀(ASSET_SECRET)로 한 서명(server_core/service_auth/signing.py)
    Authorization: Bearer <사용자의 토큰>  누구를 위해 가져가는지. asset 서버가 쓸 수 있는 사람인지 본다

답을 셋으로 나눈다. 부르는 쪽(app/conversations/service.py)이 사용자에게 무엇이라 답할지 고른다.
  - 404: 없거나, 남의 비공개거나, 게시한 적이 없거나, 볼 수 없는 등급이다 -> AssetNotFoundError
  - 403 adult_content_required: 주인인데 등급을 쓸 수 없다 -> AssetAdultRequiredError
  - 그 밖(닿지 못함, 시간 초과, 401, 5xx, 모양이 틀린 답, 모르는 형식의 판) -> AssetUnavailableError.
    사용자의 잘못이 아니다
다시 시도하지 않는다. 사람이 기다리는 요청이라 실패를 바로 알리고, 사람이 다시 누른다.
이 모듈은 HTTP 를 부르고 답을 읽기만 한다. DB 를 모른다.
"""

import time
import uuid

import httpx
from pydantic import BaseModel, ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

from app.assets.schemas import KeptImage, PersonaCopy, ShortcutListCopy, WorldCopy

# asset 서버의 주소의 머리. 이 서버의 이름(story)까지다. 주소까지 서명하므로 남의 이름으로 부를 수 없다
SERVICE_PATH = '/api/v1/asset/service/story'

# 주인인데 등급을 쓸 수 없다는 답의 code(asset-server 의 app/ratings.py)
ADULT_CONTENT_REQUIRED = 'adult_content_required'


class AssetNotFoundError(Exception):
    """asset 서버가 없다고(쓸 수 없다고) 답했다."""


class AssetAdultRequiredError(Exception):
    """asset 서버가 성인 확인이 필요하다고 답했다(자기 세계관인데 등급을 쓸 수 없다)."""


class AssetUnavailableError(Exception):
    """asset 서버를 쓸 수 없다. 설정이 없거나, 닿지 못했거나, 알 수 없는 답이다."""


def world_path(world_id: uuid.UUID) -> str:
    """세계관의 마지막 판을 가져오는 주소."""
    return f'{SERVICE_PATH}/worlds/{world_id}/latest'


def persona_path(persona_id: uuid.UUID) -> str:
    """계정 페르소나의 사본을 가져오는 주소."""
    return f'{SERVICE_PATH}/personas/{persona_id}'


def images_path(image_id: uuid.UUID | None = None) -> str:
    """장면 그림을 맡기는(지우는) 주소."""
    return f'{SERVICE_PATH}/images' if image_id is None else f'{SERVICE_PATH}/images/{image_id}'


def shortcuts_path() -> str:
    """토큰의 주인의 단축어를 가져오는 주소."""
    return f'{SERVICE_PATH}/shortcuts'


def signed_headers(
    secret: str, token: str, path: str, now: float, method: str = 'GET', body: bytes = b''
) -> dict[str, str]:
    """서명과 사용자의 토큰을 실은 머리말. 본문까지 서명한다(GET 이면 비어 있다)."""
    return {SIGNATURE_HEADER: sign(secret, int(now), method, path, body), 'Authorization': f'Bearer {token}'}


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

    async def send(self, method: str, path: str, token: str, body: bytes = b'') -> httpx.Response:
        """서명한 요청을 보낸다. 설정이 없거나 닿지 못하면 AssetUnavailableError."""
        if not self.base_url:
            raise AssetUnavailableError('ASSET_URL 이 없다')
        headers = signed_headers(self.secret, token, path, time.time(), method, body)
        if body:
            headers['Content-Type'] = 'application/octet-stream'
        try:
            return await self.http.request(
                method, self.base_url + path, headers=headers, content=body or None, timeout=self.timeout
            )
        except httpx.HTTPError as error:
            raise AssetUnavailableError(f'asset 서버에 닿지 못했다({type(error).__name__})') from error

    async def get(self, path: str, token: str) -> httpx.Response:
        """서명한 GET 을 보낸다."""
        return await self.send('GET', path, token)

    async def fetch_world(self, token: str, world_id: uuid.UUID) -> WorldCopy:
        """그 사람이 쓸 수 있는 세계관의 마지막 판."""
        return read_answer(await self.get(world_path(world_id), token), WorldCopy)

    async def fetch_persona(self, token: str, persona_id: uuid.UUID) -> PersonaCopy:
        """그 사람의 계정 페르소나의 사본."""
        return read_answer(await self.get(persona_path(persona_id), token), PersonaCopy)

    async def fetch_shortcuts(self, token: str) -> ShortcutListCopy:
        """그 사람의 단축어들."""
        return read_answer(await self.get(shortcuts_path(), token), ShortcutListCopy)

    async def keep_image(self, token: str, data: bytes) -> uuid.UUID:
        """만든 그림을 그 사람의 그림으로 맡기고 그림의 id 를 받는다. 201 이 아니면 AssetUnavailableError."""
        response = await self.send('POST', images_path(), token, data)
        if response.status_code != httpx.codes.CREATED:
            raise AssetUnavailableError(f'asset 서버가 그림을 받지 않았다({response.status_code})')
        try:
            return KeptImage.model_validate_json(response.content).id
        except ValidationError as error:
            raise AssetUnavailableError('asset 서버의 답의 모양이 틀렸다') from error

    async def discard_image(self, token: str, image_id: uuid.UUID) -> None:
        """그 사람의 그림을 지운다. 204 가 아니면 AssetUnavailableError."""
        response = await self.send('DELETE', images_path(image_id), token)
        if response.status_code != httpx.codes.NO_CONTENT:
            raise AssetUnavailableError(f'asset 서버가 그림을 지우지 않았다({response.status_code})')
