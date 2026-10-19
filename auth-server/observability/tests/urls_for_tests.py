# auth-server/observability/tests/urls_for_tests.py

"""
요청 식별 미들웨어의 테스트가 쓰는 주소들. 실제 서버에는 붙지 않는다.

테스트가 설정의 ROOT_URLCONF 를 이 파일로 바꿔서 쓴다(override_settings).
"""

from django.http import HttpResponse, JsonResponse
from django.urls import path

from accounts.models import User

# 예외의 글에 든, 응답과 로그에 실리면 안 되는 값
SECRET_IN_ERROR = 'postgres://auth:super-secret@db.internal:5432/trpg'


def ok(request, thing_id: str) -> HttpResponse:
    """잘 끝나는 뷰."""
    return JsonResponse({'status': 'ok'})


def broken(request, thing_id: str) -> HttpResponse:
    """처리하지 못한 예외를 내는 뷰."""
    raise RuntimeError(f'connect failed: {SECRET_IN_ERROR}')


def users(request) -> HttpResponse:
    """DB 를 읽는 뷰. 요청의 span 아래에 쿼리의 span 이 놓이는지 본다(test_tracing_requests.py)."""
    return JsonResponse({'count': User.objects.count()})


urlpatterns = [
    path('things/<str:thing_id>', ok, name='thing'),
    path('broken/<str:thing_id>', broken, name='broken'),
    path('users', users, name='users'),
]
