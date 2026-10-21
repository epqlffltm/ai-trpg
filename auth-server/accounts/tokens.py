# auth-server/accounts/tokens.py

"""
JWT 발급, 갱신, 폐기.

토큰의 생성, 서명, 검증과 폐기 목록(블랙리스트) 테이블은 simplejwt 가 제공한다.
여기서는 그 위에 이 프로젝트의 규칙을 얹는다.
    - 토큰 머리말에 키 ID(kid)를 넣고, 검증할 때는 그 kid 의 공개키를 고른다(키 교체, #21).
    - 토큰에 세션 버전(ver)을 넣어, 사용자의 모든 세션을 한 번에 끊을 수 있게 한다.
    - access 토큰에 닉네임(nickname)을 넣어, 다른 서버가 인증 서버를 부르지 않고 글쓴이의 이름을 알게 한다.
    - access 토큰에 성인용 내용을 볼 수 있는지(adult_content)를 넣는다(#336, 게임 서버의 #59).
    - access 토큰에 역할(roles)을 넣는다. 운영자면 ["operator"](#389, docs/architecture/operators.md).
    - 다시 동의할 필수 항목이 남은 사람의 access 토큰은 대상(aud)이 인증 서버뿐이다(#450). 다른 서버의 API 는 막히고,
      인증 서버에서 동의를 마친 뒤 갱신하면 모든 서버의 이름이 다시 실린다.
      탈퇴를 요청해 유예 중인 사람도 같다(#603). 취소한 뒤 갱신하면 다시 실린다.
    - refresh 토큰은 쓸 때마다 새것으로 바꾸고, 이미 폐기된 토큰이 다시 쓰이면 탈취로 본다.
"""

from dataclasses import dataclass
from datetime import datetime

import jwt
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenBackendError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken as SimpleJWTAccessToken
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from accounts.age import korean_today
from accounts.consents import pending_items
from accounts.identity_status import identity_status_of
from accounts.key_ring import current_key_ring
from accounts.models import User
from accounts.roles import roles_of
from accounts.withdrawal_schedule import withdrawal_scheduled_at

# 세션 버전을 담는 클레임 이름
VERSION_CLAIM = 'ver'
# 닉네임을 담는 클레임 이름. OpenID Connect 의 표준 클레임 이름을 따른다
NICKNAME_CLAIM = 'nickname'
# 성인용 내용을 볼 수 있는지를 담는 클레임 이름. 참이나 거짓이다. 이 클레임이 없는 옛 토큰은 거짓으로 본다
ADULT_CONTENT_CLAIM = 'adult_content'
# 역할을 담는 클레임 이름. 글자의 목록이다. 일반 사용자는 빈 목록이고, 이 클레임이 없는 옛 토큰도 일반 사용자로 본다
ROLES_CLAIM = 'roles'


class InvalidRefreshTokenError(Exception):
    """refresh 토큰이 없거나, 위조됐거나, 만료됐거나, 이미 폐기됐다."""


@dataclass(frozen=True)
class TokenPair:
    """
    함께 발급되는 access 토큰과 refresh 토큰.

    consents_pending 은 다시 동의할 필수 항목이고, withdrawal_scheduled_at 은 탈퇴를 요청한 계정을 비울 시각이다.
    둘 중 하나라도 있으면 access 토큰의 대상이 인증 서버뿐이다.
    """

    access: str
    refresh: str
    consents_pending: tuple[str, ...] = ()
    withdrawal_scheduled_at: datetime | None = None


class KeyIdTokenBackend(TokenBackend):
    """서명할 때 머리말에 kid 를 넣고, 검증할 때 kid 로 공개키를 고르는 TokenBackend."""

    def encode(self, payload: dict) -> str:
        """
        부모의 encode 와 같은 일을 하되, 지금의 서명 키로 서명하고 headers 에 그 키의 kid 를 더한다.

        검증하는 쪽은 JWKS 의 키 목록에서 kid 가 같은 키를 골라 쓴다.
        kid 가 없으면 키를 교체하는 동안 어느 키로 검증할지 알 수 없다.
        """
        jwt_payload = payload.copy()
        # 토큰이 대상을 정해 두었으면 그대로 둔다(audience_for). 정하지 않은 토큰(refresh)은 설정의 목록이다
        if self.audience is not None and 'aud' not in jwt_payload:
            jwt_payload['aud'] = self.audience
        if self.issuer is not None:
            jwt_payload['iss'] = self.issuer

        key_ring = current_key_ring()
        return jwt.encode(
            jwt_payload,
            key_ring.signing_key_pem,
            algorithm=self.algorithm,
            headers={'kid': key_ring.signing_key_id},
            json_encoder=self.json_encoder,
        )

    def get_verifying_key(self, token) -> str:
        """
        토큰 머리말의 kid 로 검증할 공개키를 고른다. 부모의 decode 가 부른다.

        키를 교체하는 동안에는 옛 키로 서명한 refresh 토큰(14일)도 검증해야 한다. 하나의 키로는 안 된다.
        모르는 kid 이거나 kid 가 없으면 거부한다. 검증 목록에서 뺀 키로 서명한 토큰이다.
        머리말을 읽지 못하는 토큰은 jwt 의 오류가 나고, 부모의 decode 가 "Token is invalid" 로 바꾼다.
        """
        public_key_pem = current_key_ring().verification_key(jwt.get_unverified_header(token).get('kid'))
        if public_key_pem is None:
            raise TokenBackendError('알 수 없는 키로 서명된 토큰입니다.')
        return public_key_pem


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

    @property
    def access_token(self) -> AccessToken:
        """
        이 refresh 토큰에서 access 토큰을 만든다. 발급 시각(iat)을 refresh 토큰의 것으로 맞춘다.

        simplejwt 는 만료(exp)만 refresh 토큰의 시각에서 세고, iat 는 access 토큰을 만든 때로 둔다.
        그 사이에 초가 바뀌면 access 토큰의 수명이 899 초로 보이고 두 토큰의 발급 시각이 어긋난다.
        """
        access = super().access_token
        access.set_iat(at_time=self.current_time)
        return access


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
    pending = tuple(pending_items(user))
    scheduled = withdrawal_scheduled_at(user)
    access = _access_token_for(refresh, user)
    access['aud'] = audience_for(pending, scheduled)
    return TokenPair(
        access=str(access), refresh=str(refresh), consents_pending=pending, withdrawal_scheduled_at=scheduled
    )


def audience_for(consents_pending: tuple[str, ...], withdrawal_scheduled: datetime | None = None) -> list[str]:
    """
    access 토큰의 대상(aud). 다시 동의할 필수 항목이 있거나 탈퇴의 유예 중이면 인증 서버뿐이고,
    아니면 설정의 모든 서버다.

    탈퇴의 유예(#603)도 같은 길이다. 그동안 다른 서버를 쓰지 못하고, 인증 서버에서 취소한 뒤 갱신하면 돌아온다.

    약관의 판이 오르면(중요한 변경) 동의하기 전까지 서비스를 쓰지 못하게 한다(#450). 다른 서버를 고치지 않는다.
    다른 서버는 aud 에 자기 이름이 있는지 보므로 이 토큰을 받지 않는다(401).
    인증 서버는 받는다. 그 사람은 /me 와 /me/consents 로 동의를 마치고,
    /refresh 로 모든 서버의 이름이 실린 토큰을 받는다.
    이미 나간 access 토큰은 수명(15분)까지 통한다. 판을 올린 뒤 길어야 15분이다.
    """
    if consents_pending or withdrawal_scheduled is not None:
        return [settings.JWT_OWN_AUDIENCE]
    return list(api_settings.AUDIENCE)


def _access_token_for(refresh: RefreshToken, user: User) -> AccessToken:
    """
    refresh 토큰에서 access 토큰을 만들고 닉네임을 싣는다.

    access 토큰은 refresh 토큰의 sub 와 ver 를 그대로 물려받는다.
    닉네임은 access 토큰에만 싣는다. refresh 토큰은 인증 서버만 읽으므로 이름이 필요 없다.
    갱신할 때마다 이 함수가 DB 의 닉네임을 다시 읽어 싣는다.
    이름이 바뀌면 늦어도 access 토큰의 수명(15분) 뒤에는 새 이름이 실린다.
    토큰은 서명만 되고 암호화되지 않아 누구나 읽는다.
    닉네임은 남에게 보이라고 만든 이름이라 실어도 된다(이메일은 싣지 않는다).

    성인용 내용을 볼 수 있는지도 갱신할 때마다 오늘(한국 날짜) 기준으로 다시 정한다.
    본인인증을 마친 사람이 만 19세가 되는 해의 1월 1일을 지났으면 참이다. 인증한 뒤나 그날이 온 뒤의 첫 갱신부터 실린다.
    참, 거짓만 싣는다. 생일이나 나이는 싣지 않는다.

    역할도 갱신할 때마다 그룹을 다시 읽어 싣는다. 운영자에서 빼면 늦어도 15분 뒤에는 빠진다.
    """
    access = refresh.access_token
    access[NICKNAME_CLAIM] = user.nickname
    access[ADULT_CONTENT_CLAIM] = identity_status_of(user, korean_today()).adult_content
    access[ROLES_CLAIM] = roles_of(user)
    return access


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

    끊는 것은 그 토큰이 지금 세대(세션 버전)의 것일 때뿐이다(#272). 이미 한 번 끊은 뒤의 세대라면
    그 사건은 처리됐고, 지금 살아 있는 세션은 그 뒤에 새로 로그인한 것이다. 옛 토큰을 다시 보낼 때마다
    또 끊으면, 옛 토큰을 가진 사람이 만료(14일)까지 남을 몇 번이고 로그아웃시킬 수 있다. 그때는 거부만 한다.
    """
    claims = _decode_refresh_claims(raw_refresh_token)

    with transaction.atomic():
        issued = _lock_issued_token(claims)
        user = issued.user
        reused = _is_revoked(issued)
        if reused:
            if _is_current_generation(user, claims):
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
    끊은 시각도 같은 문장에서 적는다. 다른 서버에 내주는 끊긴 세션 목록이 이 시각으로 고른다(session_revocations.py).
    """
    User.objects.filter(pk=user.pk).update(token_version=F('token_version') + 1, sessions_revoked_at=timezone.now())
    user.refresh_from_db(fields=['token_version', 'sessions_revoked_at'])


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
            OutstandingToken.objects.select_for_update()
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
    if not _is_current_generation(user, claims):
        raise InvalidRefreshTokenError


def _is_current_generation(user: User, claims: dict) -> bool:
    """토큰이 지금 세션 버전에서 발급된 것인가. 모든 세션을 끊은 뒤에는 그 전의 토큰이 지난 세대다."""
    return claims.get(VERSION_CLAIM) == user.token_version
