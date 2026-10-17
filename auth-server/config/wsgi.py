# auth-server/config/wsgi.py

"""
WSGI 의 입구. 요청을 받는 서버(gunicorn, runserver)가 이 파일의 application 을 불러 쓴다.

설정을 읽고 앱을 만든 뒤, 서명 키가 있는지 본다. 요청을 받는 서버는 토큰에 서명하므로 키가 없으면 뜨지 않는다(#274).
워커와 마이그레이션(manage.py 의 명령)은 이 파일을 거치지 않으므로 키 없이 뜬다.

https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from accounts.key_ring import require_signing_key

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

require_signing_key()
