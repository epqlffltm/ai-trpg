# auth-server/config/settings.py

"""
인증 서버의 Django 설정.

비밀값과 환경마다 달라지는 값(SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL)은
코드에 적지 않고 auth-server/.env 또는 환경 변수에서 읽는다.
필수 값이 없으면 서버가 기동을 거부한다.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import re
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from config.jwt_keys import compute_key_id, derive_public_key_pem, read_private_key_pem
from config.mail_backends import forbid_debug_in_production, require_real_mailer_in_production
from observability.formatter import ServiceInfo
from observability.setup import SERVICE_NAME, logging_settings

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# 환경 변수
# https://django-environ.readthedocs.io/

env = environ.Env()

# auth-server/.env 를 읽어 환경 변수로 올린다.
# 이미 설정된 환경 변수는 덮어쓰지 않으므로, 배포 환경에서는 .env 없이
# 컨테이너의 환경 변수만으로 동작한다
environ.Env.read_env(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/

# 기본값을 두지 않는다. 값이 없으면 ImproperlyConfigured 로 기동이 실패한다
SECRET_KEY = env('SECRET_KEY')

# 적지 않으면 False. 설정을 빠뜨렸을 때 안전한 쪽으로 동작하게 한다
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])


# 관측(로그)
# 규격은 저장소 루트의 docs/observability.md 에 있다

# 이 서버가 도는 환경의 이름. 로그의 environment 칸에 들어간다.
# development, test, staging, production 처럼 적는다. 기록을 가를 때 쓴다.
# production 이면 DEBUG 와, 터미널에 메일을 출력하는 개발용 방식을 막는다(아래의 Email)
APP_ENVIRONMENT = env('APP_ENVIRONMENT', default='development')

# 이 서버의 버전. 로그의 version 칸에 들어간다. 배포할 때 git SHA 나 이미지의 버전을 넣는다
APP_VERSION = env('APP_VERSION', default='dev')

# 이 수준부터 로그를 남긴다. debug, info, warning, error 중 하나다
LOG_LEVEL = env('LOG_LEVEL', default='info')

# 이 값들은 로그의 모든 줄에 실린다. 줄바꿈이나 빈칸이 든 값을 받지 않는다
if not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', APP_ENVIRONMENT):
    raise ImproperlyConfigured('APP_ENVIRONMENT 는 영문 소문자로 시작하고 영문 소문자, 숫자, 밑줄, 붙임표만 씁니다.')
if not re.fullmatch(r'[A-Za-z0-9._+-]{1,64}', APP_VERSION):
    raise ImproperlyConfigured('APP_VERSION 은 영문, 숫자, 점, 밑줄, 더하기, 붙임표로 64자까지 씁니다.')
if LOG_LEVEL not in ('debug', 'info', 'warning', 'error'):
    raise ImproperlyConfigured("LOG_LEVEL 은 'debug', 'info', 'warning', 'error' 중 하나여야 합니다.")

# DEBUG 가 켜져 있으면 예외의 응답에 호출 기록과 설정값이 실린다. 운영에서는 뜨지 않게 한다
forbid_debug_in_production(DEBUG, APP_ENVIRONMENT)

# 로그를 공통 규격의 JSON 으로 건다. Django 의 기본 함수 대신 식별자를 붙이는 일까지 하는 함수를 쓴다
LOGGING_CONFIG = 'observability.setup.configure'
LOGGING = logging_settings(
    ServiceInfo(service=SERVICE_NAME, environment=APP_ENVIRONMENT, version=APP_VERSION),
    LOG_LEVEL,
)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 외부 패키지
    'rest_framework',
    # 발급한 refresh 토큰과 폐기 목록을 DB 에 기록한다
    'rest_framework_simplejwt.token_blacklist',
    # 이 프로젝트의 앱
    'accounts',
]

MIDDLEWARE = [
    # 요청마다 식별자(request_id, trace_id)를 걸고, 끝나면 한 줄을 남긴다. 응답에 X-Request-ID 를 돌려준다.
    # 맨 앞에 둔다. 다른 미들웨어가 남기는 로그에도 식별자가 붙는다
    'observability.middleware.RequestLoggingMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# 사용자 모델
# https://docs.djangoproject.com/en/6.1/topics/auth/customizing/#substituting-a-custom-user-model

# Django 기본 User 대신 accounts 앱의 User 를 쓴다.
# 첫 migrate 전에 정해야 한다. 나중에 바꾸면 기존 테이블과 외래 키를 전부 다시 만들어야 한다
AUTH_USER_MODEL = 'accounts.User'


# Django REST framework
# https://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    # 시도 횟수 제한에 걸렸을 때의 429 응답을 한 모양으로 맞춘다. 나머지는 DRF 의 기본 처리에 넘긴다
    'EXCEPTION_HANDLER': 'accounts.exception_handlers.handle_exception',
    # Authorization: Bearer <토큰> 헤더의 JWT 로 사용자를 확인한다.
    # simplejwt 의 인증 클래스에 세션 버전 확인을 더한 것이다.
    # 기본값인 세션 인증과 Basic 인증은 쓰지 않는다
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'accounts.authentication.SessionVersionJWTAuthentication',
    ],
    # 기본을 "인증된 사용자만" 으로 둔다.
    # 공개 API 는 뷰에서 AllowAny 를 직접 적어야 열린다.
    # 권한 설정을 빠뜨린 뷰가 열려 있는 것보다 닫혀 있는 쪽이 안전하다
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # 서버 간 통신과 프론트 모두 JSON 만 쓴다
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}


# JWT
# https://django-rest-framework-simplejwt.readthedocs.io/en/latest/settings.html

# 개인키는 파일로 두고 .env 에는 경로만 적는다. PEM 은 여러 줄이라 .env 값으로 넣기 불편하다.
# 상대 경로는 auth-server 폴더를 기준으로 한다
JWT_PRIVATE_KEY_PATH = BASE_DIR / env('JWT_PRIVATE_KEY_PATH', default='keys/jwt-private.pem')

_jwt_private_key_pem = read_private_key_pem(JWT_PRIVATE_KEY_PATH)

# 공개키. JWKS 로 내보내고, 인증 서버 자신도 토큰을 검증할 때 쓴다
JWT_PUBLIC_KEY_PEM = derive_public_key_pem(_jwt_private_key_pem)

# 토큰 머리말의 kid 와 JWKS 의 kid 에 같은 값이 들어간다
JWT_KEY_ID = compute_key_id(JWT_PUBLIC_KEY_PEM)

SIMPLE_JWT = {
    # 비대칭 서명. 개인키는 이 서버만 갖고, 다른 서버는 공개키로 검증만 한다.
    # 대칭키(HS256)를 여러 서버가 공유하면 검증만 해야 할 서버도 토큰을 만들 수 있다
    'ALGORITHM': 'RS256',
    'SIGNING_KEY': _jwt_private_key_pem,
    'VERIFYING_KEY': JWT_PUBLIC_KEY_PEM,

    # 누가 발급했고(iss) 누구에게 쓰라고 발급했는지(aud).
    # 검증하는 서버는 aud 에 자기 이름이 있는지 확인한다.
    # 토큰 하나에 모든 서버의 이름을 싣는다. 프론트는 토큰 하나로 모든 서버를 부른다.
    # 서버가 늘면 여기에 이름을 더한다. .env 에 JWT_AUDIENCE 를 적어 둔 곳은 그 줄도 함께 고쳐야 한다
    'ISSUER': env('JWT_ISSUER', default='ai-trpg-auth'),
    'AUDIENCE': env.list(
        'JWT_AUDIENCE',
        default=['ai-trpg-auth', 'ai-trpg-game', 'ai-trpg-board', 'ai-trpg-billing'],
    ),

    # 다른 서버는 블랙리스트를 보지 않고 서명과 만료만 확인한다.
    # 그래서 탈취됐을 때 쓸 수 있는 시간을 짧게 잡는다
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),

    # 이 기간 안에 한 번이라도 접속하면 로그인이 유지된다.
    # refresh 토큰은 쓸 때마다 새것으로 바뀌고 기간도 다시 시작한다
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),

    # 토큰의 주체는 정수 PK 가 아니라 public_id 다
    'USER_ID_FIELD': 'public_id',
    'USER_ID_CLAIM': 'sub',

    # 머리말에 kid 를 넣는 토큰 클래스. 검증할 때도 같은 클래스를 쓴다
    'AUTH_TOKEN_CLASSES': ('accounts.tokens.AccessToken',),
}

# refresh 토큰 쿠키를 HTTPS 에서만 보낼지.
# 적지 않으면 True. 로컬 개발은 HTTP 라서 .env 에서 false 로 둔다
REFRESH_COOKIE_SECURE = env.bool('REFRESH_COOKIE_SECURE', default=True)


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

# DATABASE_URL 한 줄을 Django 의 DATABASES 형식(ENGINE, NAME, USER, ...)으로 바꾼다.
# auth 계정으로 접속하면 PostgreSQL 의 기본 search_path("$user", public)에 따라
# auth 스키마가 기본 스키마가 되므로, 스키마를 여기서 따로 지정하지 않는다
DATABASES = {
    'default': env.db('DATABASE_URL'),
}

# 테스트에서만 가벼운 비밀번호 해셔를 쓰는 실행기. manage.py test 에만 적용된다
TEST_RUNNER = 'config.test_runner.FastHasherTestRunner'

# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        # 비밀번호가 아이디, 이메일, 닉네임과 비슷하면 거부한다.
        # 기본값은 first_name, last_name 을 보는데 이 프로젝트의 User 에는 그 필드가 없다
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'user_attributes': ('username', 'email', 'nickname'),
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = 'static/'


# 서버 앞에 선, 우리가 운영하는 프록시(nginx, 로드밸런서)의 수.
# 요청을 보낸 쪽의 IP 를 알아낼 때 X-Forwarded-For 헤더를 어디까지 믿을지 정한다(accounts/client_ip.py).
# 0 이면 헤더를 보지 않는다. 프록시가 없는데 1 이상으로 두면 누구나 IP 를 지어낼 수 있고,
# 프록시가 있는데 0 으로 두면 모든 요청이 프록시의 IP 로 보여 한 사람의 시도가 모두를 막는다
TRUSTED_PROXY_COUNT = env.int('TRUSTED_PROXY_COUNT', default=0)


# Redis
# 없어도 서비스가 도는 보조 장치(시도 횟수)만 둔다. 죽어 있으면 제한 없이 통과시킨다
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/0')

# 시도 횟수 제한을 켤지. 테스트 실행기가 끈다(config/test_runner.py)
ATTEMPT_LIMITS_ENABLED = True

# Redis 키의 앞머리. 같은 Redis 를 다른 서버와 함께 쓰므로 서버 이름을 붙인다
ATTEMPT_LIMIT_KEY_PREFIX = 'auth:attempts'


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

# SMTP_HOST 가 있으면 그 메일 서버로 실제로 보낸다.
# 없으면 보내지 않고 터미널에 출력한다. 메일 설정 없이도 개발과 CI 가 돌게 하기 위해서다.
# Django 기본 console 백엔드는 한글 본문을 base64 로 출력해 읽을 수 없어서
# 읽을 수 있게 출력하는 백엔드를 쓴다
smtp_host = env('SMTP_HOST', default='')

# 운영에서는 터미널에 출력하는 방식을 쓸 수 없다. 그 출력에는 받는 사람의 주소와 인증 코드가 그대로 찍힌다
require_real_mailer_in_production(smtp_host, APP_ENVIRONMENT)

if smtp_host:
    MAILERS = {
        'default': {
            'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
            'OPTIONS': {
                'host': smtp_host,
                # 587 은 STARTTLS 로 암호화하는 제출용 포트다
                'port': env.int('SMTP_PORT', default=587),
                'username': env('SMTP_USER'),
                'password': env('SMTP_PASSWORD'),
                'use_tls': True,
                # 메일 서버가 응답하지 않을 때 워커가 무한정 기다리지 않게 한다(초)
                'timeout': env.int('SMTP_TIMEOUT', default=10),
            },
        },
    }
else:
    MAILERS = {
        'default': {
            'BACKEND': 'config.mail_backends.ReadableConsoleEmailBackend',
        },
    }

# 보안 이벤트 요약 메일(manage.py send_security_digest)을 받을 운영자의 주소. 쉼표로 여러 개를 적는다.
# 비어 있으면 요약 메일을 보내지 않는다. 사건은 관리자 화면에서만 볼 수 있다
SECURITY_DIGEST_TO = env.list('SECURITY_DIGEST_TO', default=[])

# 메일을 언제 보내는가.
#   outbox: 발송함(DB)에 적어 두고 워커(manage.py send_outgoing_mail)가 보낸다
#   inline: 요청을 처리하는 자리에서 바로 보낸다. 워커 없이 개발할 때와 테스트에서만 쓴다.
#           메일 서버를 기다리는 시간이 응답 시간에 그대로 드러나므로 운영에서는 쓰지 않는다
# 실제 메일 서버를 쓰면 outbox, 터미널 출력이면 inline 이 기본값이다
MAIL_DELIVERY = env('MAIL_DELIVERY', default='outbox' if smtp_host else 'inline')
if MAIL_DELIVERY not in ('outbox', 'inline'):
    raise ImproperlyConfigured("MAIL_DELIVERY 는 'outbox' 또는 'inline' 이어야 합니다.")

# 메일의 보내는 사람 주소
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='AI TRPG <no-reply@localhost>')

# 비밀번호 재설정 메일의 링크가 가리키는 프론트 화면.
# 인증 서버의 주소가 아니다. 링크는 화면을 열기만 하고, 변경은 그 화면이 API 에 POST 로 요청한다
PASSWORD_RESET_URL = env('PASSWORD_RESET_URL', default='http://localhost:5173/reset-password')
