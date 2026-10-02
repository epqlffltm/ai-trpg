# auth-server/accounts/tokens.py

"""
JWT 발급.

토큰의 생성, 서명, 검증은 simplejwt 가 한다. 여기서는 두 가지만 덧붙인다.
  1. 토큰 머리말에 키 ID(kid)를 넣는다. simplejwt 는 kid 를 넣지 않는다.
  2. 발급을 함수 하나로 감싼다. 로그인 흐름이 바뀌어도 발급 코드는 그대로 쓴다.
"""

import jwt
from django.conf import settings
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken as SimpleJWTAccessToken

from accounts.models import User


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


def issue_access_token(user: User) -> str:
    """
    사용자의 access 토큰을 발급해 문자열로 돌려준다.

    로그인 뷰가 토큰을 직접 만들지 않고 이 함수를 부른다.
    나중에 로그인이 2단계로 바뀌어도 마지막 단계에서 같은 함수를 부르면 된다.
    """
    return str(AccessToken.for_user(user))