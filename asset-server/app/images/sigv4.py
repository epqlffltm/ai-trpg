# asset-server/app/images/sigv4.py

"""
S3 의 요청 서명(AWS Signature Version 4)을 만든다(#566). 네트워크도 시계도 모른다. 받은 값으로 계산만 한다.

그림 저장소(로컬은 SeaweedFS, staging 은 S3)에 두 가지를 한다. 둘 다 같은 서명이다.
  - 넣기(PutObject): 머리말 Authorization 에 서명을 싣는다(authorization_header).
  - 내주기: GetObject 를 서명한 주소를 nginx 에 넘긴다(presigned_url). nginx 는 그 주소를 따라가기만 한다.

SDK(boto3)를 쓰지 않는 까닭: 쓰는 것이 이 둘뿐이고, boto3 는 동기라 스레드로 돌려야 하며 크다(유저 결정, 2026-10-22).
AWS 문서의 예시 값으로 시험한다(tests/test_sigv4.py).

주소는 경로 방식(https://<호스트>/<버킷>/<키>)이다. SeaweedFS 와 S3 의 지역 주소가 함께 받는다.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

ALGORITHM = 'AWS4-HMAC-SHA256'
SERVICE = 's3'
# 본문을 서명하지 않는다는 표시. 서명한 주소(GET)는 본문이 없다
UNSIGNED_PAYLOAD = 'UNSIGNED-PAYLOAD'


@dataclass(frozen=True)
class Credentials:
    """서명에 쓰는 키와 지역."""

    access_key_id: str
    secret_access_key: str
    region: str


def sha256_hex(data: bytes) -> str:
    """바이트의 SHA-256(16진수)."""
    return hashlib.sha256(data).hexdigest()


def amz_date(now: datetime) -> str:
    """서명에 쓰는 시각(UTC, 20130524T000000Z)."""
    return now.strftime('%Y%m%dT%H%M%SZ')


def scope(now: datetime, region: str) -> str:
    """서명의 범위(날짜/지역/s3/aws4_request)."""
    return f'{now.strftime("%Y%m%d")}/{region}/{SERVICE}/aws4_request'


def uri_encode(value: str, keep_slash: bool = False) -> str:
    """AWS 의 URI 인코딩. 영문자, 숫자, - _ . ~ 만 그대로 둔다. 경로에서는 / 도 둔다."""
    return quote(value, safe='-_.~/' if keep_slash else '-_.~')


def canonical_query(params: dict[str, str]) -> str:
    """정렬하고 인코딩한 쿼리."""
    return '&'.join(f'{uri_encode(key)}={uri_encode(value)}' for key, value in sorted(params.items()))


def canonical_request(method: str, path: str, query: dict[str, str], headers: dict[str, str], payload_hash: str) -> str:
    """서명할 요청의 정규 모양. headers 의 이름은 소문자다."""
    names = sorted(headers)
    lines = [
        method,
        uri_encode(path, keep_slash=True),
        canonical_query(query),
        *[f'{name}:{headers[name].strip()}' for name in names],
        '',
        ';'.join(names),
        payload_hash,
    ]
    return '\n'.join(lines)


def string_to_sign(request: str, now: datetime, region: str) -> str:
    """서명할 글."""
    return '\n'.join([ALGORITHM, amz_date(now), scope(now, region), sha256_hex(request.encode())])


def hmac_sha256(key: bytes, message: str) -> bytes:
    """HMAC-SHA256."""
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


def signing_key(secret_access_key: str, now: datetime, region: str) -> bytes:
    """그날, 그 지역의 s3 에 쓰는 서명 키."""
    key = hmac_sha256(f'AWS4{secret_access_key}'.encode(), now.strftime('%Y%m%d'))
    for part in (region, SERVICE, 'aws4_request'):
        key = hmac_sha256(key, part)
    return key


def signature(credentials: Credentials, request: str, now: datetime) -> str:
    """정규 요청의 서명(16진수)."""
    key = signing_key(credentials.secret_access_key, now, credentials.region)
    return hmac.new(key, string_to_sign(request, now, credentials.region).encode(), hashlib.sha256).hexdigest()


def authorization_header(
    credentials: Credentials, method: str, path: str, headers: dict[str, str], payload_hash: str, now: datetime
) -> str:
    """머리말 Authorization 의 값. headers 에는 host, x-amz-date, x-amz-content-sha256 이 들어 있어야 한다."""
    request = canonical_request(method, path, {}, headers, payload_hash)
    credential = f'{credentials.access_key_id}/{scope(now, credentials.region)}'
    signed = ';'.join(sorted(headers))
    proof = signature(credentials, request, now)
    return f'{ALGORITHM} Credential={credential},SignedHeaders={signed},Signature={proof}'


def presigned_query(credentials: Credentials, host: str, path: str, expires: int, now: datetime) -> dict[str, str]:
    """GET 을 서명한 주소의 쿼리. 서명(X-Amz-Signature)까지 든다."""
    query = {
        'X-Amz-Algorithm': ALGORITHM,
        'X-Amz-Credential': f'{credentials.access_key_id}/{scope(now, credentials.region)}',
        'X-Amz-Date': amz_date(now),
        'X-Amz-Expires': str(expires),
        'X-Amz-SignedHeaders': 'host',
    }
    request = canonical_request('GET', path, query, {'host': host}, UNSIGNED_PAYLOAD)
    return {**query, 'X-Amz-Signature': signature(credentials, request, now)}


def presigned_url(credentials: Credentials, origin: str, host: str, path: str, expires: int, now: datetime) -> str:
    """GET 을 서명한 주소. origin 은 스킴과 호스트(http://object-store:8333), host 는 그 호스트(포트 포함)다."""
    query = canonical_query(presigned_query(credentials, host, path, expires, now))
    return f'{origin}{uri_encode(path, keep_slash=True)}?{query}'
