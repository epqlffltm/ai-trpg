# auth-server/config/urls.py

"""
프로젝트 전체의 URL 진입점.

앱마다 자기 urls.py 를 갖고, 여기서는 앞부분 경로에 연결만 한다.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config import health

urlpatterns = [
    path('admin/', admin.site.urls),
    # 상태 확인. API 주소 밖에 둔다. 다른 세 서버와 같은 주소다(config/health.py)
    path('health', health.health, name='health'),
    path('health/ready', health.ready, name='health-ready'),
    # 버전을 주소에 넣는다. 응답 형식을 바꿔야 할 때 v2 를 따로 열 수 있다
    path('api/v1/auth/', include('accounts.urls')),
]

# API 목록과 그것을 보는 화면(#558). 개발(DEBUG)에서만 연다. 운영 서버는 API 의 구조를 내보이지 않는다.
# 다른 서버(FastAPI)의 /api/v1/<서버>/openapi.json, /docs 와 같은 자리다.
# 저장소의 목록은 docs/api/auth.openapi.json 이다
if settings.DEBUG:
    urlpatterns += [
        path('api/v1/auth/openapi.json', SpectacularAPIView.as_view(), name='openapi'),
        path('api/v1/auth/docs', SpectacularSwaggerView.as_view(url_name='openapi'), name='api-docs'),
    ]
