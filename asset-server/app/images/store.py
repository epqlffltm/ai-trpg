# asset-server/app/images/store.py

"""
그림 저장소(#566). 로컬과 CI 는 SeaweedFS(object-store), staging 은 S3 다. 둘 다 S3 의 API 로 부른다.

  - put: 그림을 그림의 id 로 넣는다. 형식(Content-Type)을 객체에 적는다. nginx 는 저장소가 준 형식을 내보낸다.
  - presigned_get: 그림을 60초 동안 받을 수 있는 주소. nginx 가 그 주소로 받아 캐시하고 내준다
    (docs/architecture/asset-server.md 의 "그림"). 키는 이 서버만 갖는다.

저장소의 주소는 compose 가 준다(IMAGE_STORE_ENDPOINT). nginx 는 그 주소가 저장소의 것일 때만 따라간다.
그래서 compose 밖에서 띄운 서버(127.0.0.1:8333)가 만든 주소는 nginx 가 받지 않는다.

닿지 못하거나 저장소가 거절하면 ImageStoreUnavailableError 다(503). 답의 본문(XML)은 싣지 않는다.
설정에 저장소가 없으면 UnconfiguredImageStore 를 쓴다. 올리기는 503 이다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from app.images.sigv4 import Credentials, amz_date, authorization_header, presigned_url, sha256_hex

# 서명한 주소가 사는 시간(초). nginx 가 곧바로 받아 가므로 짧게 둔다
PRESIGNED_SECONDS = 60


class ImageStoreUnavailableError(Exception):
    """저장소에 닿지 못했거나, 저장소가 거절했거나, 저장소가 설정되지 않았다."""


@dataclass(frozen=True)
class StoreLocation:
    """저장소의 주소와 버킷. origin 은 스킴과 호스트(포트 포함)다(http://object-store:8333)."""

    origin: str
    bucket: str

    def path(self, key: str) -> str:
        """그 키의 객체의 경로(/<버킷>/<키>)."""
        return f'/{self.bucket}/{key}'

    def host(self) -> str:
        """서명에 넣는 호스트. origin 의 스킴을 뺀 것이다."""
        return httpx.URL(self.origin).netloc.decode()


class ImageStore(Protocol):
    """그림 저장소의 모양. 테스트는 가짜(tests/images.py)를 쓴다."""

    async def put(self, key: str, data: bytes, content_type: str, now: datetime) -> None:
        """그림을 넣는다. 실패하면 ImageStoreUnavailableError."""
        ...

    def presigned_get(self, key: str, now: datetime) -> str:
        """그림을 잠깐 받을 수 있는 주소. 저장소가 없으면 ImageStoreUnavailableError."""
        ...


def put_headers(
    credentials: Credentials, location: StoreLocation, key: str, data: bytes, content_type: str, now: datetime
) -> dict[str, str]:
    """넣는 요청의 머리말. 서명(Authorization)까지 든다."""
    payload_hash = sha256_hex(data)
    headers = {
        'content-type': content_type,
        'host': location.host(),
        'x-amz-content-sha256': payload_hash,
        'x-amz-date': amz_date(now),
    }
    authorization = authorization_header(credentials, 'PUT', location.path(key), headers, payload_hash, now)
    return {**headers, 'authorization': authorization}


@dataclass(frozen=True)
class S3ImageStore:
    """S3 의 API 를 부르는 저장소. client 는 앱이 함께 쓰는 httpx 클라이언트다."""

    client: httpx.AsyncClient
    credentials: Credentials
    location: StoreLocation
    timeout: float

    async def put(self, key: str, data: bytes, content_type: str, now: datetime) -> None:
        """그림을 넣는다. 닿지 못하거나 2xx 가 아니면 ImageStoreUnavailableError."""
        headers = put_headers(self.credentials, self.location, key, data, content_type, now)
        url = self.location.origin + self.location.path(key)
        try:
            response = await self.client.put(url, content=data, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as error:
            raise ImageStoreUnavailableError from error
        if not response.is_success:
            raise ImageStoreUnavailableError(f'저장소가 {response.status_code} 로 답했다')

    def presigned_get(self, key: str, now: datetime) -> str:
        """그림을 60초 동안 받을 수 있는 주소."""
        location = self.location
        return presigned_url(
            self.credentials, location.origin, location.host(), location.path(key), PRESIGNED_SECONDS, now
        )


@dataclass(frozen=True)
class UnconfiguredImageStore:
    """저장소가 설정되지 않은 서버(IMAGE_STORE_ENDPOINT 가 비었다). 무엇을 하든 ImageStoreUnavailableError 다."""

    async def put(self, key: str, data: bytes, content_type: str, now: datetime) -> None:
        """넣을 곳이 없다."""
        raise ImageStoreUnavailableError('저장소가 설정되지 않았다')

    def presigned_get(self, key: str, now: datetime) -> str:
        """받을 곳이 없다."""
        raise ImageStoreUnavailableError('저장소가 설정되지 않았다')
