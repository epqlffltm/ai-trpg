# auth-server/accounts/tokens.py

"""
JWT 발급, 갱신, 폐기.

토큰의 생성, 서명, 검증과 폐기 목록(블랙리스트) 테이블은 simplejwt 가 제공한다.
여기서는 그 위에 이 프로젝트의 규칙을 얹는다.
    - 토큰 머리말에 키 ID(kid)를 넣는다.
    - 토큰에 세션 버전(ver)을 넣어, 사용자의 모든 세션을 한 번에 끊을 수 있게 한다.
    - refresh 토큰은 쓸 때마다 새것으로 바꾸고, 이미 폐기된 토큰이 다시 쓰이면 탈취로 본다.
"""

from dataclasses import dataclass

import jwt
from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenBackendError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken as SimpleJWTAccessToken
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from accounts.models import User

# 세션 버전을 담는 클레임 이름
VERSION_CLAIM = 'ver'


class InvalidRefreshTokenError(Exception):
    """refresh 토큰이 없거나, 위조됐거나, 만료됐거나, 이미 폐기됐다."""


@dataclass(frozen=True)
class TokenPair:
    """함께 발급되는 access 토큰과 refresh 토큰."""

    access: str
    refresh: str


class KeyIdTokenBackend(TokenBackend):
    """서명할 때 머리말에 kid 를 넣는 TokenBackend."""

    def encode(self, payload: dict) -> str:
        """
        부모의 encode 와 같은 일을 하되 headers 에 kid 를 더한다.

        검증하는 쪽은 JWKS 의 키 목록에서 kid 가 같은 키를 골라 쓴다.
        kid 가 없으면 키를 교체하는 동안 어느 키로 검증할지 알 수 없다.
        """
        jwt_payload = payload.copy()
        if self.audience is not None:
            jwt_payload['aud'] = self.audience
        if self.issuer is not None:
            jwt_payload['iss'] = self.issuer

        return jwt.encode(
            jwt_payload,
            self.prepared_signing_key,
            algorithm=self.algorithm,
            headers={'kid': settings.JWT_KEY_ID},
            json_encoder=self.json_encoder,
        )


# simplejwt 가 내부에서 만드는 것과 같은 설정으로, 클래스만 바꿔 만든다
token_backend = KeyIdTokenBackend(
    api_settings.ALGORITHM,
    api_settings.SIGNING_KEY,
    api_settings.VERIFYING_KEY,
    api_settings.AUDIENCE,
    api_settings.ISSUER,
    api_settings.JWK_URL,
    api_settings.LEEWAY,
    api_settings.JSON_ENCODER,
)


class AccessToken(SimpleJWTAccessToken):
    """kid 를 넣는 backend 를 쓰는 access 토큰."""

    @property
    def token_backend(self) -> TokenBackend:
        return token_backend


class RefreshToken(SimpleJWTRefreshToken):
    """kid 를 넣는 backend 를 쓰는 refresh 토큰."""

    # refresh 토큰에서 access 토큰을 만들 때 쓸 클래스
    access_token_class = AccessToken

    @property
    def token_backend(self) -> TokenBackend:
        return token_backend


def issue_token_pair(user: User) -> TokenPair:
    """
    사용자의 access 토큰과 refresh 토큰을 발급한다.

    로그인과 갱신이 모두 이 함수를 부른다.
    나중에 로그인이 2단계로 바뀌어도 마지막 단계에서 같은 함수를 부르면 된다.
    """
    refresh = RefreshToken()
    refresh[api_settings.USER_ID_CLAIM] = str(user.public_id)
    refresh[VERSION_CLAIM] = user.token_version
    _record_issued_refresh_token(refresh, user)

    # access 토큰은 refresh 토큰의 sub 와 ver 를 그대로 물려받는다
    return TokenPair(access=str(refresh.access_token), refresh=str(refresh))


def _record_issued_refresh_token(refresh: RefreshToken, user: User) -> None:
    """
    발급한 refresh 토큰을 기록한다. 폐기는 이 기록에 표시를 붙이는 방식으로 한다.

    토큰 원문은 저장하지 않는다. 폐기 여부는 토큰 ID(jti)만으로 판단할 수 있고,
    원문을 저장하면 DB 를 읽을 수 있는 사람이 남의 세션을 그대로 쓸 수 있다.
    """
    OutstandingToken.objects.create(
        user=user,
        jti=refresh[api_settings.JTI_CLAIM],
        token='',
        created_at=refresh.current_time,
        expires_at=datetime_from_epoch(refresh['exp']),
    )


def rotate_refresh_token(raw_refresh_token: str) -> TokenPair:
    """
    refresh 토큰을 폐기하고 새 토큰 쌍을 발급한다.

    이미 폐기된 토큰이 들어오면 탈취로 본다. 정상 사용자와 공격자 중 한쪽이
    옛 토큰을 쓴 것이므로, 누가 진짜인지 가리지 않고 그 사용자의 모든 세션을 끊는다.
    """
    claims = _decode_refresh_claims(raw_refresh_token)

    with transaction.atomic():
        issued = _lock_issued_token(claims)
        user = issued.user
        reused = _is_revoked(issued)
        if reused:
            # 이 변경은 아래에서 예외를 내기 전에 커밋되어야 한다.
            # 그래서 예외를 트랜잭션 블록 밖에서 낸다
            revoke_all_sessions(user)
        else:
            _ensure_session_is_current(user, claims)
            _revoke(issued)
            token_pair = issue_token_pair(user)

    if reused:
        raise InvalidRefreshTokenError
    return token_pair


def revoke_refresh_token(raw_refresh_token: str) -> None:
    """
    refresh 토큰 하나를 폐기한다. 로그아웃에 쓴다.

    유효하지 않은 토큰이면 InvalidRefreshTokenError 를 낸다.
    """
    claims = _decode_refresh_claims(raw_refresh_token)
    with transaction.atomic():
        _revoke(_lock_issued_token(claims))


def revoke_all_sessions(user: User) -> None:
    """
    사용자의 세션 버전을 올려 이미 발급된 토큰을 전부 무효로 만든다.

    토큰을 하나씩 찾아 폐기하지 않는다. 버전이 다른 토큰은 검증에서 걸러진다.
    읽어서 더한 뒤 저장하면 동시 요청에서 증가가 유실되므로 DB 에서 직접 더한다.
    """
    User.objects.filter(pk=user.pk).update(token_version=F('token_version') + 1)
    user.refresh_from_db(fields=['token_version'])


def _decode_refresh_claims(raw_refresh_token: str) -> dict:
    """서명, 만료, 발급자, 대상을 검증하고 refresh 토큰의 내용을 돌려준다."""
    try:
        claims = token_backend.decode(raw_refresh_token)
    except TokenBackendError as exc:
        raise InvalidRefreshTokenError from exc

    # access 토큰을 refresh 자리에 넣는 것을 막는다
    if claims.get(api_settings.TOKEN_TYPE_CLAIM) != RefreshToken.token_type:
        raise InvalidRefreshTokenError
    return claims


def _lock_issued_token(claims: dict) -> OutstandingToken:
    """
    발급 기록을 잠그고 가져온다.

    같은 refresh 토큰으로 요청 두 개가 동시에 들어오면, 잠금 없이는 둘 다
    "아직 폐기되지 않음" 을 보고 각자 새 토큰을 받는다. 행을 잠가 한 번에 하나만 지나가게 한다.
    """
    try:
        return (
            OutstandingToken.objects
            .select_for_update()
            .select_related('user')
            .get(jti=claims.get(api_settings.JTI_CLAIM), user__isnull=False)
        )
    except OutstandingToken.DoesNotExist as exc:
        raise InvalidRefreshTokenError from exc


def _is_revoked(issued: OutstandingToken) -> bool:
    return BlacklistedToken.objects.filter(token=issued).exists()


def _revoke(issued: OutstandingToken) -> None:
    BlacklistedToken.objects.get_or_create(token=issued)


def _ensure_session_is_current(user: User, claims: dict) -> None:
    """비활성 계정이거나, 모든 세션을 끊기 전에 발급된 토큰이면 거부한다."""
    if not user.is_active:
        raise InvalidRefreshTokenError
    if claims.get(VERSION_CLAIM) != user.token_version:
        raise InvalidRefreshTokenError