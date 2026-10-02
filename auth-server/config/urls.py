# auth-server/config/urls.py

"""
프로젝트 전체의 URL 진입점.

앱마다 자기 urls.py 를 갖고, 여기서는 앞부분 경로에 연결만 한다.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # 버전을 주소에 넣는다. 응답 형식을 바꿔야 할 때 v2 를 따로 열 수 있다
    path('api/v1/auth/', include('accounts.urls')),
]