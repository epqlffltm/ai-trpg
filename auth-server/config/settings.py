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

from datetime import timedelta
from pathlib import Path

import environ

from config.jwt_keys import compute_key_id, derive_public_key_pem, read_private_key_pem

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


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.messages',
    'rest_framework',
    'accounts',
]

MIDDLEWARE = [
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

# Django 기본 User 대신 accounts 앱의 User 를 쓴다.
# 첫 migrate 전에 정해야 한다. 나중에 바꾸면 기존 테이블과 외래 키를 전부 다시 만들어야 한다
AUTH_USER_MODEL = 'accounts.User'

# Django REST framework
# https://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    # 인증 수단은 로그인 API 를 만들 때 JWT 로 채운다.
    # 기본값인 세션 인증과 Basic 인증은 쓰지 않으므로 비워 둔다
    'DEFAULT_AUTHENTICATION_CLASSES': [],
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
    # Authorization: Bearer <토큰> 헤더의 JWT 로 사용자를 확인한다.
    # 기본값인 세션 인증과 Basic 인증은 쓰지 않는다
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
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
    # 검증하는 서버는 aud 에 자기 이름이 있는지 확인한다
    'ISSUER': env('JWT_ISSUER', default='ai-trpg-auth'),
    'AUDIENCE': env.list('JWT_AUDIENCE', default=['ai-trpg-auth', 'ai-trpg-game']),

    # 다른 서버는 블랙리스트를 보지 않고 서명과 만료만 확인한다.
    # 그래서 탈취됐을 때 쓸 수 있는 시간을 짧게 잡는다
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),

    # 토큰의 주체는 정수 PK 가 아니라 public_id 다
    'USER_ID_FIELD': 'public_id',
    'USER_ID_CLAIM': 'sub',

    # 머리말에 kid 를 넣는 토큰 클래스. 검증할 때도 같은 클래스를 쓴다
    'AUTH_TOKEN_CLASSES': ('accounts.tokens.AccessToken',),
}

# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

# DATABASE_URL 한 줄을 Django 의 DATABASES 형식(ENGINE, NAME, USER, ...)으로 바꾼다.
# auth 계정으로 접속하면 PostgreSQL 의 기본 search_path("$user", public)에 따라
# auth 스키마가 기본 스키마가 되므로, 스키마를 여기서 따로 지정하지 않는다
DATABASES = {
    'default': env.db('DATABASE_URL'),
}


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


# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
