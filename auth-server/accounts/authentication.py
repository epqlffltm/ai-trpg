# auth-server/accounts/authentication.py

"""
인증 서버 자신의 API 가 쓰는 인증 클래스.

simplejwt 의 JWTAuthentication 은 서명과 만료를 확인하고 사용자를 찾는다.
여기에 세션 버전 확인을 더한다.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from accounts.tokens import VERSION_CLAIM


class SessionVersionJWTAuthentication(JWTAuthentication):
    """모든 세션을 끊은 뒤에는, 그 전에 발급된 access 토큰을 받지 않는다."""

    def get_user(self, validated_token):
        """
        부모가 찾은 사용자의 세션 버전과 토큰의 버전을 비교한다.

        다른 서버는 인증 서버에 묻지 않으므로 이 확인을 할 수 없고,
        옛 access 토큰은 만료(15분)까지 그쪽에서 통한다.
        인증 서버는 어차피 사용자를 DB 에서 읽으므로 추가 비용 없이 바로 막는다.
        """
        user = super().get_user(validated_token)
        if validated_token.get(VERSION_CLAIM) != user.token_version:
            raise AuthenticationFailed('세션이 만료되었습니다.', code='session_revoked')
        return user