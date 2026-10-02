# auth-server/accounts/views.py

"""
accounts 앱의 API 뷰.

뷰는 HTTP 만 다룬다. 요청을 Serializer 로 검증하고, service 를 호출하고,
결과를 응답으로 바꾼다. 규칙과 DB 작업은 여기에 두지 않는다.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import SignupResponseSerializer, SignupSerializer
from accounts.services import DuplicateAccountError, register_user


class SignupView(APIView):
    """POST /api/v1/auth/signup"""

    # 기본 권한이 IsAuthenticated 라서, 로그인 없이 호출하는 API 는 직접 열어 줘야 한다
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data)
        # 검증에 실패하면 400 과 필드별 오류 메시지로 응답한다
        serializer.is_valid(raise_exception=True)

        try:
            user = register_user(**serializer.validated_data)
        except DuplicateAccountError:
            return Response(
                {'detail': '이미 사용 중인 아이디, 이메일 또는 닉네임입니다.'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            SignupResponseSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )