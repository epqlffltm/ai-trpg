# auth-server/support/permissions.py

"""
운영자만 여는 주소의 권한. 운영자인지는 토큰의 roles 가 아니라 지금의 그룹으로 본다(accounts/roles.py).
인증 서버가 그 그룹을 가지고 있어, 운영자에서 빼면 토큰의 수명(15분)을 기다리지 않고 바로 막힌다.

운영자가 아니면 404 다. 다른 서버의 운영자 API 와 같다(403 이면 운영자의 주소가 있다는 것이 드러난다).
"""

from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from accounts.roles import OPERATOR_ROLE, roles_of


class IsOperator(BasePermission):
    """로그인했고 운영자의 그룹에 든 계정만. 로그인하지 않았으면 401, 운영자가 아니면 404 다."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if OPERATOR_ROLE not in roles_of(user):
            raise NotFound('Not Found')
        return True
