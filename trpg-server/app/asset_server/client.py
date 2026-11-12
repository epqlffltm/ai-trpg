# trpg-server/app/asset_server/client.py

"""
asset 서버를 부른다(asset-server/README.md 의 "다른 서버에 내주기"). 장면 그림과 제작자의 캐릭터 그림(#983)을
맡기고 받고 지운다.

    POST   {ASSET_URL}/api/v1/asset/service/trpg/images              그린(올린) 사람의 토큰으로 맡긴다. 201 과 그림의 id
    GET    {ASSET_URL}/api/v1/asset/service/trpg/images/{id}/kept    이 서버가 맡긴 그림의 바이트. 서명만으로 받는다
    DELETE {ASSET_URL}/api/v1/asset/service/trpg/images/{id}         그린 사람의 토큰으로 지운다. 204
    X-Service-Signature: 이 서버의 비밀(ASSET_SECRET)로 한 서명(server_core/service_auth/signing.py). 본문까지 서명한다

  - 받기(kept)는 사용자의 토큰을 보내지 않는다. 테이블의 사람 누구에게 보일지는 이 서버가 정한다(테이블에 앉았는가)
  - 404 는 AssetNotFoundError, 그 밖(닿지 못함, 시간 초과, 401, 5xx, 모양이 틀린 답)은 AssetUnavailableError 다
  - 맡길 때 asset 이 그림을 받지 않으면(너무 크다 413, 받지 않는 형식 415, 열 수 없다 422) ImageRejectedError 다.
    AssetUnavailableError 의 한 갈래라, 까닭을 나누지 않는 쪽(장면 그림)은 그대로 실패로 다룬다
다시 시도하지 않는다. 이 모듈은 HTTP 를 부르고 답을 읽기만 한다. DB 를 모른다.
"""

import time
import uuid
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError
from server_core.service_auth.signing import SIGNATURE_HEADER, sign

# asset 서버의 주소의 머리. 이 서버의 이름(trpg)까지다. 주소까지 서명하므로 남의 이름으로 부를 수 없다
SERVICE_PATH = '/api/v1/asset/service/trpg'


class AssetNotFoundError(Exception):
    """asset 서버가 없다고 답했다(지웠거나, 이 서버가 맡긴 것이 아니다)."""


class AssetUnavailableError(Exception):
    """asset 서버를 쓸 수 없다. 설정이 없거나, 닿지 못했거나, 알 수 없는 답이다."""


class ImageRejectedError(AssetUnavailableError):
    """asset 서버가 그림을 받지 않았다. code 는 까닭이다(image_too_large, image_format, image_unreadable)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# asset 서버가 그림을 받지 않은 답과 그 까닭
REJECTED_CODES: dict[int, str] = {
    httpx.codes.REQUEST_ENTITY_TOO_LARGE: 'image_too_large',
    httpx.codes.UNSUPPORTED_MEDIA_TYPE: 'image_format',
    httpx.codes.UNPROCESSABLE_ENTITY: 'image_unreadable',
}


class KeptImage(BaseModel):
    """맡긴 그림의 답. id 만 읽는다."""

    model_config = ConfigDict(extra='ignore')

    id: uuid.UUID


@dataclass(frozen=True)
class ImageContent:
    """받은 그림의 바이트와 형식(image/png 같은 것)."""

    data: bytes
    mime_type: str


def images_path(image_id: uuid.UUID | None = None) -> str:
    """장면 그림을 맡기는(지우는) 주소."""
    return f'{SERVICE_PATH}/images' if image_id is None else f'{SERVICE_PATH}/images/{image_id}'


def kept_path(image_id: uuid.UUID) -> str:
    """이 서버가 맡긴 그림의 바이트를 받는 주소."""
    return f'{images_path(image_id)}/kept'


def signed_headers(secret: str, path: str, now: float, method: str, body: bytes, token: str | None) -> dict[str, str]:
    """서명을 실은 머리말. 토큰이 있으면 함께 싣는다(그린 사람을 위해 맡기고 지울 때)."""
    headers = {SIGNATURE_HEADER: sign(secret, int(now), method, path, body)}
    if token is not None:
        headers['Authorization'] = f'Bearer {token}'
    if body:
        headers['Content-Type'] = 'application/octet-stream'
    return headers


def read_content(response: httpx.Response) -> ImageContent:
    """그림의 답을 읽는다. 404 는 AssetNotFoundError, 그 밖의 답이나 그림이 아닌 형식은 AssetUnavailableError."""
    if response.status_code == httpx.codes.NOT_FOUND:
        raise AssetNotFoundError
    if response.status_code != httpx.codes.OK:
        raise AssetUnavailableError(f'asset 서버가 그림을 내주지 않았다({response.status_code})')
    mime_type = response.headers.get('content-type', '').split(';')[0].strip()
    if not mime_type.startswith('image/') or not response.content:
        raise AssetUnavailableError('asset 서버가 그림이 아닌 것을 내줬다')
    return ImageContent(data=response.content, mime_type=mime_type)


class AssetClient:
    """asset 서버를 부르는 것 하나. 앱에 하나 붙여 둔다(app.state.asset). 테스트는 가짜로 바꾼다."""

    def __init__(self, http: httpx.AsyncClient, base_url: str, secret: str, timeout: float) -> None:
        self.http = http
        self.base_url = base_url.rstrip('/')
        self.secret = secret
        self.timeout = timeout

    async def send(self, method: str, path: str, token: str | None, body: bytes = b'') -> httpx.Response:
        """서명한 요청을 보낸다. 설정이 없거나 닿지 못하면 AssetUnavailableError."""
        if not self.base_url:
            raise AssetUnavailableError('ASSET_URL 이 없다')
        headers = signed_headers(self.secret, path, time.time(), method, body, token)
        try:
            return await self.http.request(
                method, self.base_url + path, headers=headers, content=body or None, timeout=self.timeout
            )
        except httpx.HTTPError as error:
            raise AssetUnavailableError(f'asset 서버에 닿지 못했다({type(error).__name__})') from error

    async def keep_image(self, token: str, data: bytes) -> uuid.UUID:
        """
        그림을 그 사람의 그림으로 맡기고 그림의 id 를 받는다.

        그림을 받지 않으면 ImageRejectedError, 그 밖에 201 이 아니면 AssetUnavailableError.
        """
        response = await self.send('POST', images_path(), token, data)
        if response.status_code in REJECTED_CODES:
            raise ImageRejectedError(REJECTED_CODES[response.status_code])
        if response.status_code != httpx.codes.CREATED:
            raise AssetUnavailableError(f'asset 서버가 그림을 받지 않았다({response.status_code})')
        try:
            return KeptImage.model_validate_json(response.content).id
        except ValidationError as error:
            raise AssetUnavailableError('asset 서버의 답의 모양이 틀렸다') from error

    async def fetch_kept(self, image_id: uuid.UUID) -> ImageContent:
        """이 서버가 맡긴 그림의 바이트. 사용자의 토큰 없이 서명만으로 받는다."""
        return read_content(await self.send('GET', kept_path(image_id), None))

    async def discard_image(self, token: str, image_id: uuid.UUID) -> None:
        """그 사람의 그림을 지운다. 204 가 아니면 AssetUnavailableError."""
        response = await self.send('DELETE', images_path(image_id), token)
        if response.status_code != httpx.codes.NO_CONTENT:
            raise AssetUnavailableError(f'asset 서버가 그림을 지우지 않았다({response.status_code})')
