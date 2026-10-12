# auth-server/Dockerfile
# 인증 서버의 이미지. 저장소 루트의 docker-compose.yml 이 app 프로필로 띄운다.
#
# 단계 넷으로 나눈다.
#   deps    : 의존성을 깔고 소스를 담는다. 의존성(uv.lock)이 그대로면 까는 일은 캐시를 쓴다
#   static  : 관리자 화면의 정적 파일을 모은다. 여기서만 쓰고 버리는 키와 값으로 설정을 읽힌다
#   supercronic : 주기 명령을 돌리는 실행 파일을 받아 확인한다
#   runtime : 실행에 필요한 것만 담는다. root 가 아닌 사용자로 돈다
#
# 비밀(.env, JWT 개인키)은 넣지 않는다(.dockerignore). 컨테이너를 띄울 때 compose 가 넘긴다.
# 마이그레이션은 이 이미지로 따로 한 번 돈다(compose 의 auth-migrate). 서버가 뜰 때 돌리지 않는다.
# 워커(auth-mail, auth-welcome-credits)와 주기 명령(auth-cron)도 이 이미지로 따로 돈다.

FROM python:3.13-slim-trixie AS deps
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
# 바이트코드를 미리 만들어 첫 요청이 느리지 않게 한다. 캐시에서 링크하지 않고 복사한다(캐시는 이미지에 남지 않는다).
# 파이썬은 기본 이미지의 것을 쓴다. uv 가 따로 내려받지 않는다
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
# 잠금 파일과 어긋나면 실패한다(--locked). 이 서버는 패키지로 설치하지 않는다(--no-install-project)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY . .

FROM deps AS static
# 설정 파일은 읽힐 때 비밀키, DB 주소, 서명용 개인키를 요구한다. collectstatic 은 그것들을 쓰지 않는다.
# 이 명령에서만 쓰는 값과 그 자리에서 만든 키를 준다. ENV 로 두지 않는다(이미지의 설정에 남는다).
# 이 단계에서 runtime 으로 옮기는 것은 정적 파일뿐이다
RUN .venv/bin/python scripts/generate_jwt_key.py /tmp/collectstatic-only.pem \
    && SECRET_KEY=collectstatic-only \
       DATABASE_URL=postgres://unused:unused@127.0.0.1:5432/unused \
       JWT_PRIVATE_KEY_PATH=/tmp/collectstatic-only.pem \
       STATIC_ROOT=/app/staticfiles \
       .venv/bin/python manage.py collectstatic --noinput \
    && rm /tmp/collectstatic-only.pem

# 주기 명령을 돌리는 supercronic(컨테이너용 cron). compose 의 auth-cron 가 쓴다. 서버는 쓰지 않는다.
# 받은 파일을 체크섬으로 확인한다. 이미지를 만드는 PC 의 CPU(amd64, arm64)에 맞는 것을 받는다
FROM alpine:3.24 AS supercronic
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.48
RUN case "$TARGETARCH" in \
        amd64) sha256=88c1b66b94c486f972fdd1a4d1f901e3e75ff04f749cddd60c5db573e3a33c6c ;; \
        arm64) sha256=50ae8755e04fa72812d0a1bc47a112a856811cc91cce7b6c875c378a850788bc ;; \
        *) echo "supercronic 을 받을 수 없는 CPU: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && wget -q -O /supercronic "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
    && echo "$sha256  /supercronic" > /supercronic.sha256 \
    && sha256sum -c /supercronic.sha256 \
    && chmod 755 /supercronic

FROM python:3.13-slim-trixie AS runtime
# 로그를 버퍼에 모으지 않고 바로 내보낸다. 컨테이너가 죽을 때 마지막 줄이 사라지지 않는다.
# 읽기만 하는 폴더에 .pyc 를 쓰려 하지 않는다(바이트코드는 deps 에서 미리 만들었다)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/.venv/bin:$PATH \
    STATIC_ROOT=/app/staticfiles
# root 가 아닌 사용자. 번호를 고정한다. 리눅스에서 키 파일을 붙일 때 이 번호에 읽을 권한을 준다(README)
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
# 파일의 주인은 root 로 둔다. 서버는 읽기만 한다. 서버가 뚫려도 제 코드를 고쳐 쓰지 못한다
COPY --from=deps /app /app
COPY --from=static /app/staticfiles /app/staticfiles
COPY --from=supercronic /supercronic /usr/local/bin/supercronic
# 번호로 적는다. 이름은 바깥(쿠버네티스 등)에서 root 가 아닌지 확인할 수 없다
USER 10001
EXPOSE 8000
# 설정은 gunicorn.conf.py 에 있다
CMD ["gunicorn", "config.wsgi"]
