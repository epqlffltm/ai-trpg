# story-server/Dockerfile
# story 서버의 이미지. 저장소 루트의 docker-compose.yml 이 app 프로필로 띄운다.
#
# 게임 서버의 것(trpg-server/Dockerfile)과 같은 모양이다. 단계 둘로 나눈다.
#   deps    : 의존성을 깔고 소스를 담는다. 의존성(uv.lock)이 그대로면 까는 일은 캐시를 쓴다
#             공용 코드(shared/server-core, shared/ai-core, shared/conversation-core)도 여기서 의존성으로 깐다
#   runtime : 실행에 필요한 것만 담는다. root 가 아닌 사용자로 돈다
#
# 비밀(.env)은 넣지 않는다(.dockerignore). 컨테이너를 띄울 때 compose 가 넘긴다.
# 마이그레이션은 이 이미지로 따로 한 번 돈다(compose 의 story-migrate). 서버가 뜰 때 돌리지 않는다.

FROM python:3.13-slim-trixie AS deps
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
# 바이트코드를 미리 만들어 첫 요청이 느리지 않게 한다. 캐시에서 링크하지 않고 복사한다(캐시는 이미지에 남지 않는다).
# 파이썬은 기본 이미지의 것을 쓴다. uv 가 따로 내려받지 않는다
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 공용 코드(shared/server-core, shared/ai-core, shared/conversation-core). compose 가 shared 라는 이름의 빌드 범위로 넘긴다(build.additional_contexts).
# pyproject.toml 의 경로 의존(../shared/...)이 이미지 안에서도 맞게 /shared 에 둔다. 설정과 소스만 담는다.
# ai-core 의 소스에는 모델 목록의 원본(model_catalog.toml)이 함께 든다
COPY --from=shared server-core/pyproject.toml /shared/server-core/pyproject.toml
COPY --from=shared server-core/src /shared/server-core/src
COPY --from=shared ai-core/pyproject.toml /shared/ai-core/pyproject.toml
COPY --from=shared ai-core/src /shared/ai-core/src
COPY --from=shared conversation-core/pyproject.toml /shared/conversation-core/pyproject.toml
COPY --from=shared conversation-core/src /shared/conversation-core/src
COPY pyproject.toml uv.lock ./
# 잠금 파일과 어긋나면 실패한다(--locked). 테스트 도구는 넣지 않는다(--no-dev).
# 공용 코드는 .venv 안에 설치된 모양으로 넣는다(--no-editable). 실행 단계는 /shared 없이 /app 만 담는다
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --no-editable
COPY . .

FROM python:3.13-slim-trixie AS runtime
# 로그를 버퍼에 모으지 않고 바로 내보낸다. 컨테이너가 죽을 때 마지막 줄이 사라지지 않는다.
# 읽기만 하는 폴더에 .pyc 를 쓰려 하지 않는다(바이트코드는 deps 에서 미리 만들었다)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/.venv/bin:$PATH
# root 가 아닌 사용자. 번호를 고정한다(다른 서버와 같다)
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
# 파일의 주인은 root 로 둔다. 서버는 읽기만 한다. 서버가 뚫려도 제 코드를 고쳐 쓰지 못한다
COPY --from=deps /app /app
# 번호로 적는다. 이름은 바깥(쿠버네티스 등)에서 root 가 아닌지 확인할 수 없다
USER 10001
EXPOSE 8007
# 프로세스 하나로 돈다. 정리 작업과 끊긴 세션 목록 받기가 서버 안에서 돈다.
# 여럿으로 늘려도 된다(정리 작업은 다른 프로세스가 잠근 줄을 건너뛴다)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
