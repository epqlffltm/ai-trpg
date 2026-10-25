# 게시판 서버

[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)

[ai-trpg](../README.md)의 게시판 서버. 사이트가 운영하는 커뮤니티를 맡는다. 공지, 이벤트, 잡담, 시나리오 이야기 같은 글과 댓글이다. FastAPI(Python)로 만든다.
처음에는 NestJS(TypeScript)로 만들었고 FastAPI 로 다시 썼다(#785). 주소, 요청, 응답, 오류의 모양, 환경 변수의 이름, DB(`board` 스키마)는 그때와 같다. 같은 계약 시험(`contract/`)을 두 서버가 모두 통과했다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.
시나리오의 소개 페이지에 붙는 댓글(플레이한 사람들의 평)은 여기가 아니라 시나리오 쪽의 일이다.

지금은 게시판, 글, 댓글, 글마다의 댓글 수, 글 고정, 글 검색, 쓰기 횟수 제한, 글과 댓글의 신고까지 있다. 게시판 넷(공지사항, 이벤트, 자유 게시판, 시나리오 이야기)에 글을 쓰고, 글에 댓글과 답글을 단다. 글과 댓글에는 글쓴이의 닉네임이 함께 나온다.

다른 FastAPI 서버(게임, 알림, asset)와 같은 공용 코드(`shared/server-core`)를 쓴다. 토큰 검증, 끊긴 세션의 목록, DB 연결, 로그, 추적, 메트릭, 알림의 발송함이 거기에 있다.

## 목차

- [실행](#실행)
- [DB와 마이그레이션](#db와-마이그레이션)
- [API](#api)
- [알림 보내기](#알림-보내기)
- [탈퇴 받기](#탈퇴-받기)
- [구조](#구조)
- [로그와 요청 식별자](#로그와-요청-식별자)
- [추적](#추적)
- [메트릭](#메트릭)
- [CI](#ci)
- [설계 메모](#설계-메모)

## 실행

명령은 모두 `board-server` 폴더 안에서 실행한다. 파이썬 3.13 과 [uv](https://docs.astral.sh/uv/) 가 있어야 한다.

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `board` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/05-board-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트를 추가하기 전에 만든 볼륨이라면 한 번 직접 실행한다. 루트의 `.env`에 `BOARD_DB_PASSWORD`를 적고
컨테이너를 다시 만든 뒤(`docker compose up -d`), 저장소 루트에서 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/05-board-role.sql
```

### 설치와 실행

`.env` 는 저장소 루트에서 `uv run --no-project python tools/fill_env.py` 가 만들고 비밀을 채운다(DB 비밀번호, 알림 서버와 인증 서버의 서명 비밀).
손으로 만들려면 `.env.example` 을 복사해서 값을 채운다.

```powershell
cd board-server
copy .env.example .env
uv sync
uv run alembic upgrade heads
uv run python -m app
```

`.env`의 `DATABASE_URL`에 `board` 계정의 비밀번호(루트 `.env`의 `BOARD_DB_PASSWORD`)와 포트(`POSTGRES_PORT`)를 적는다.
`AUTH_JWKS_URL`은 인증 서버를 다른 포트로 띄웠을 때만 고친다.
인증 서버가 8000번, 게임 서버가 8001번을 쓰므로 8002번으로 띄운다. `http://127.0.0.1:8002/health` 가 `{"status":"ok"}` 를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8002/health/ready`가 `{"status":"ok"}`를 돌려주면 DB 까지 정상이다.

`uv run python -m app` 은 주소와 포트를 설정(`HOST`, `PORT`)에서 읽어 띄운다(`app/__main__.py`). compose 와 계약 시험도 이렇게 띄운다.
파일을 고칠 때마다 다시 띄우려면 `uv run uvicorn app.main:app --port 8002 --reload` 로 띄운다. 이때는 `HOST`, `PORT` 를 읽지 않고 uvicorn 의 인자를 쓴다.
서버는 DB 가 꺼져 있어도 뜬다. 연결은 처음 쓸 때 맺는다. 그동안 `/health/ready` 가 503 이다.

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | `postgresql://board:<비밀번호>@127.0.0.1:5432/trpg` 형식. `postgresql://` 로 적어도 서버가 비동기 드라이버의 주소(`postgresql+asyncpg://`)로 바꿔 쓴다. 바꾼 모양으로 적어도 된다 |
| `DB_SCHEMA` | `board` | 테이블이 놓이는 스키마. 테스트는 `board_test`로 고정한다 |
| `DB_POOL_SIZE` | `5` | 연결 풀이 늘 들고 있는 연결의 수 |
| `DB_MAX_OVERFLOW` | `5` | 붐빌 때 더 맺는 연결의 수. 둘의 합(10)이 이 서버의 몫이다([서버 구성](../docs/architecture/services.md)의 "DB 와 Redis 의 한도"). 공용 코드의 기본값(10)보다 작게 잡았다 |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. `http://127.0.0.1:8000/api/v1/auth/jwks` |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다. 없으면 서버가 뜨지 않는다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 믿는 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-board` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다. 하나만 적는다 |
| `HOST` | `127.0.0.1` | 서버가 듣는 주소(`python -m app`). 컨테이너에서는 `0.0.0.0` |
| `PORT` | `8002` | 서버가 듣는 포트(`python -m app`) |
| `DEBUG` | `false` | API 문서 화면(`/api/v1/board/docs`)과 목록(`/api/v1/board/openapi.json`)을 연다. 운영에서는 켜지 않는다 |

알림 서버와 탈퇴의 설정은 [알림 보내기](#알림-보내기)와 [탈퇴 받기](#탈퇴-받기)에, 로그와 수집기의 설정은 [로그와 요청 식별자](#로그와-요청-식별자)에 있다.
설정은 환경 변수, `.env`, 기본값의 차례로 읽는다(`app/core/config.py`). 함께 쓰는 칸은 공용 코드의 `server_core/settings.py` 에 있다.
값이 틀리면 서버가 뜨기 전에 멈춘다. 그 오류에는 읽은 값을 싣지 않는다.

### compose 로 모든 서버와 함께 띄우기

모든 서버를 컨테이너로 함께 띄우는 방법은 [저장소의 README](../README.md#4-모든-서버를-컨테이너로-선택)에 있다(`docker compose --profile app up -d --build`).
그때 게시판 서버에 관해 다른 것만 적는다.

- 같은 `board-server/.env` 를 쓴다. 주소(DB, 인증 서버의 공개키, 알림 서버)와 `HOST`, `PORT` 는 compose 가 덮어쓴다
- 테이블은 `board-migrate` 가 서버보다 먼저 한 번 만든다(`alembic upgrade heads`). 서버가 뜰 때 마이그레이션을 돌리지 않는다
- 알림 보내기와 끊긴 세션 목록 받기는 서버 안에서 돈다. 따로 띄울 워커가 없다
- 바깥 주소는 프록시 하나다. `http://127.0.0.1:8080/api/v1/board/...`. 게시판 서버의 포트(8002)는 열지 않는다
- 서버끼리 부르는 `/api/v1/board/service/` 는 프록시가 바깥에서 막는다(404). 인증 서버는 프록시를 거치지 않고 컨테이너 이름(`board-server:8002`)으로 부른다
- compose 의 healthcheck 가 컨테이너 안에서 10초마다 `/health/ready` 를 부른다
- 이미지(`Dockerfile`)는 게임 서버의 것과 같은 모양이다. root 가 아닌 사용자(번호 10001)로 돌고, `.env`, 테스트, 계약 시험은 넣지 않는다

### 로그인한 사용자로 불러 보기

인증 서버를 띄우고 로그인해서 받은 access 토큰을 붙여 부른다.

```
curl http://127.0.0.1:8002/api/v1/board/me -H "Authorization: Bearer <access 토큰>"
```

`{"user_id":"..."}`가 오면 인증 서버가 발급한 토큰을 이 서버가 검증한 것이다. 토큰에 닉네임이 실려 있었다면 이때 적어 둔다. 401 이 오면 둘을 본다.

- **인증 서버의 `JWT_AUDIENCE`에 `ai-trpg-board`가 있는가.** 인증 서버는 토큰에 대상의 목록을 싣고, 이 서버는 그 목록에 자기 이름이 있는지 본다.
  인증 서버의 기본값에는 들어 있다. `auth-server/.env`에 `JWT_AUDIENCE`를 직접 적어 둔 PC 라면 그 줄에 `ai-trpg-board`를 더하고 인증 서버를 다시 띄운다.
- **토큰이 그 뒤에 발급된 것인가.** 대상은 발급할 때 정해진다. 고치기 전에 받은 토큰에는 새 이름이 없다. access 토큰의 수명은 15분이다.

503 이 오면 이 서버가 인증 서버의 공개키를 구하지 못한 것이다. 인증 서버가 떠 있는지와 `AUTH_JWKS_URL`을 본다.

### 운영자

공지사항과 이벤트 게시판에는 운영자만 글을 쓴다. 운영자는 남의 글도 지울 수 있다.
누가 운영자인지는 인증 서버가 정한다(#389). 인증 서버의 Django 그룹 `operators` 에 든 계정이고, access 토큰의 `roles` 에 `"operator"` 가 실린다. 이 서버는 토큰을 읽기만 한다.

넣고 빼는 법은 인증 서버 README 의 "운영자를 넣고 빼는 법"을 따른다(관리자 화면 `/admin/` 의 회원 → 권한의 그룹).
넣은 뒤에는 그 사람이 다시 로그인하거나 토큰을 갱신해야 실린다. 뺀 것도 이미 받은 access 토큰이 끝날 때까지(15분) 통한다. 바로 막아야 하면 인증 서버에서 그 사람의 세션을 끊는다.
잘 실렸는지는 그 사람의 토큰으로 `/api/v1/board/me`를 불러 `is_operator`가 `true`인지 본다.

예전에는 이 서버의 `operators` 테이블이 운영자를 정했다. NestJS 때의 마이그레이션(`DropOperators`)이 그 테이블을 지웠고, 지금의 마이그레이션은 그 테이블을 만들지 않는다.

### 테스트와 검사

```
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

- `ruff check`: 쓰지 않는 import 나 정의되지 않은 이름 같은 문제를 실행하지 않고 찾는다. 규칙은 저장소 루트의 `ruff.toml` 이다. 다른 서버들과 같다.
- `ruff format --check`: 코드의 모양이 정해진 규칙과 맞는지 본다. 고치려면 `uv run ruff format .` 이다.
- `pytest`: `tests/` 의 테스트. 앱을 만들어 서버를 띄우지 않고 요청을 바로 넘긴다(httpx 의 `ASGITransport`). 실제 PostgreSQL 에서 돈다.
- `uv run pytest --cov`: 같은 테스트를 돌리며 지나간 줄의 비율(커버리지)도 잰다. 대상은 `app/` 이다(`pyproject.toml` 의 `[tool.coverage.run]`).

커밋하기 전에 셋을 모두 돌리고, [계약 시험](#계약-시험)도 돌린다.

`tests/` 는 HTTP 만으로는 볼 수 없는 것을 본다. 주소와 응답의 시나리오는 계약 시험이 맡는다.

| 파일 | 보는 것 |
| --- | --- |
| `test_config.py` | `postgresql://` 를 asyncpg 의 주소로 바꾸기, 주소와 포트의 기본값, 연결 풀이 이 서버의 몫(10)을 넘지 않는가, 짧은 `AUTH_SERVER_SECRET` 이면 뜨지 않기 |
| `test_errors.py` | 오류의 모양. 시험용 주소를 앱에 더해 이 서버의 거절, 라이브러리의 거절(404, 405), 입력 오류(400), 깨진 JSON, API 목록의 `InputError` 를 본다 |
| `test_auth.py` | 토큰의 닉네임 적기와 거르기, 키를 받은 적 없이 인증 서버가 죽어 있을 때의 503 |
| `test_health.py`, `test_readiness.py` | 상태 확인, HEAD, DB 에 닿지 않을 때와 3초 안에 답하지 않을 때의 503, API 문서가 기본으로 닫힌 것, 뜰 때 끊긴 세션 목록 받기가 시작되고 꺼질 때 연결이 닫히는 것 |
| `test_posts_search.py` | 검색의 시간 초과(503)와 그 뒤의 연결, 시간 초과가 아닌 DB 오류는 감추지 않기, 검색의 메트릭 |
| `test_comments.py`, `test_reports.py` | 쓰기와 신고의 메트릭, 입력 오류의 칸과 문장과 차례, 댓글과 알림이 한 트랜잭션인 것, 동시에 들어온 같은 신고(유일 제약), 줄을 직접 넣어 보는 경우들 |
| `test_withdrawal.py`, `test_service_auth.py` | 탈퇴가 한 트랜잭션인 것, 로그에 사람을 남기지 않기, 본문의 검사와 문장, 서명의 셈과 경로, 비밀이 빈 설정 |
| `test_core_rules.py` | DB 와 HTTP 없이 보는 작은 규칙(닉네임의 모양, 최근 닉네임의 기억, 기다릴 초, 시각의 모양, 알림을 받을 사람, 메트릭의 결과) |
| `test_schema_isolation.py` | `board` 계정이 다른 서버의 스키마에 닿지 못하는가([설계 메모](#설계-메모)의 "DB 계정과 스키마") |

토큰 검증, 끊긴 세션의 목록, 알림을 실제로 보내는 일처럼 공용 코드에 있는 것은 공용 코드의 테스트(`shared/server-core/tests/`)가 본다.

테스트는 개발용과 같은 DB의 `board_test` 스키마를 쓰므로 개발용 데이터(`board` 스키마)를 건드리지 않는다.
DB 주소는 환경 변수나 `.env`의 것을 그대로 읽고, 스키마와 동작을 바꾸는 값(인증 서버의 주소, 알림 서버의 주소, 서명 비밀, 로그의 수준)은 테스트가 고정한다(`tests/conftest.py`).
테스트용 스키마에도 테이블이 있어야 한다. 마이그레이션을 새로 만들거나 받으면 한 번 적용한다.

```
# PowerShell
$env:DB_SCHEMA='board_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA

# bash
DB_SCHEMA=board_test uv run alembic upgrade heads
```

테스트는 시작할 때 글, 댓글, 신고, 닉네임, 발송함을 비운다(`tests/cleaning.py`). 게시판은 마이그레이션이 넣은 것이라 두고 간다. 운영자는 토큰의 `roles` 로 흉내 낸다.

DB가 꺼져 있으면 테스트가 실패한다. 인증 서버는 띄우지 않아도 된다. 토큰은 테스트가 직접 만든 키로 서명하고,
그 공개키를 내주는 가짜 인증 서버를 앱에 꽂는다(`server_core/testing/tokens.py`).
다른 서버의 계정과 스키마(적어도 `auth`)도 DB 에 만들어져 있어야 한다. 게시판 계정이 거기에 들어가지 못하는지 테스트가 확인한다.

### 계약 시험

`contract/` 는 시나리오를 **떠 있는 서버에 HTTP 로만** 보내는 시험이다(pytest, #785). 서버의 코드를 가져오지 않는다.
그래서 같은 시험이 NestJS 로 쓰던 서버와 지금의 FastAPI 서버 둘 다에 돌았고, 둘 다 통과한 뒤에 갈아 끼웠다. 따로 된 파이썬 묶음이다(`contract/pyproject.toml`).

- 서버는 시험이 프로세스로 띄운다. 명령은 `BOARD_SERVER_COMMAND`(기본 `uv run python -m app`), 폴더는 `BOARD_SERVER_DIR`(기본 `board-server`)다(`contract/harness/server.py`).
  서버에는 서버가 원래 읽는 환경 변수만 준다(`PORT`, `HOST`, `DATABASE_URL`, `DB_SCHEMA`, `AUTH_JWKS_URL`, `AUTH_SERVER_SECRET`).
- 인증 서버는 시험이 띄우는 작은 가짜가 공개키 목록과 빈 끊긴 세션의 목록을 내준다(`contract/harness/auth.py`). 토큰은 시험의 키로 서명한다.
- DB 는 `board_test` 스키마를 쓴다(`BOARD_CONTRACT_SCHEMA` 로 바꾼다). 시험마다 글, 댓글, 신고, 닉네임, 알림의 발송함을 비운다. 시간이 흐른 것처럼 시각을 옮기는 일만 DB 로 한다.
- 사람은 시험마다 새로 만든다. 서버가 최근에 적은 닉네임을 기억해 두는 것과 섞이지 않게 한다.
- 쓰기 한도는 서버의 것 그대로다. 많이 쓰는 시험은 사람을 나누거나 DB 에 바로 넣는다.
- 보는 것: 게시판, 글, 검색, 댓글, 댓글 수, 고정, 신고, 쓰기 한도, 토큰, 글쓴이의 닉네임, 오류의 모양, health, 탈퇴 받기, 알림의 발송함에 적기.
- 보지 않는 것: 로그, 메트릭, 추적, 설정, DB 권한, OpenAPI, 검색 시간 초과, 그리고 앱의 부품을 바꿔 꽂아야 하는 경우
  (시험용 주소, 처음 키를 받지 못한 서버, DB 에 닿지 않는 health, 알림을 실제로 보내기). HTTP 만으로는 볼 수 없어서 `tests/` 가 본다(위의 표).

시험은 `DATABASE_URL` 을 환경 변수에서만 읽는다(`.env` 를 읽지 않는다). `board` 계정의 주소를 `postgresql://` 모양으로 준다. 테스트용 스키마에 마이그레이션을 먼저 적용해 둔다(위).

```
# PowerShell
cd contract; uv sync; $env:DATABASE_URL='postgresql://board:<비밀번호>@127.0.0.1:5432/trpg'; uv run pytest; Remove-Item Env:DATABASE_URL
uv run ruff check .; uv run ruff format --check .

# bash
cd contract && uv sync
DATABASE_URL=postgresql://board:<비밀번호>@127.0.0.1:5432/trpg uv run pytest
uv run ruff check . && uv run ruff format --check .
```

서버는 `board-server` 폴더에서 뜨므로 `board-server/.env` 도 읽는다. 시험이 지운 환경 변수(`NOTIFICATION_URL` 등)라도 `.env` 에 적혀 있으면 그 값이 쓰인다.

CI 는 서버를 `uv run coverage run -m app` 으로 띄워 계약 시험이 지나간 줄도 센다. `tests/` 의 것과 합쳐 하나의 커버리지로 본다([CI](#ci)).

### 패키지를 더하고 뺄 때

```
uv add 패키지이름
uv add --dev 패키지이름
uv remove 패키지이름
```

`pyproject.toml`과 `uv.lock`이 함께 바뀐다. 둘 다 커밋한다. `.venv/`는 커밋하지 않는다.
`--dev` 는 테스트와 검사에만 쓰는 것(`[dependency-groups]` 의 `dev`)이다. 이미지에는 들지 않는다(`Dockerfile` 의 `uv sync --no-dev`).
CI 는 `uv sync --locked` 로 깐다. 두 파일이 어긋나면 실패한다. 서버에 실제로 들어가는 패키지의 알려진 취약점도 CI 가 본다(pip-audit).

공용 코드(`server-core`)는 저장소 안의 경로(`../shared/server-core`)에서 editable 로 깐다(`pyproject.toml` 의 `[tool.uv.sources]`). 공용 코드를 고치면 다시 깔지 않아도 바로 보인다.
계약 시험의 패키지는 `contract/` 안에서 같은 명령으로 더하고 뺀다. 서버의 것과 따로다.

## DB와 마이그레이션

테이블 구조의 변경은 Alembic 의 마이그레이션으로 관리한다. DB 주소와 스키마는 앱과 같은 설정(`.env`)에서 읽는다(`migrations/env.py`). `alembic.ini` 에는 적지 않는다.
앱의 설정을 통째로 읽으므로 `AUTH_JWKS_URL` 같은 필수 값도 있어야 하고, `NOTIFICATION_URL` 을 적었다면 `NOTIFICATION_SECRET` 도 맞아야 한다.

```
uv run alembic upgrade heads                          # 마이그레이션 적용. 끝이 여럿이면 모두
uv run alembic check                                  # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
uv run alembic revision --autogenerate -m "설명"       # 모델과 DB 를 비교해 새 마이그레이션 만들기
uv run alembic heads                                  # 마이그레이션의 끝 보기
uv run alembic downgrade -1                           # 마지막 하나 되돌리기
```

테스트용 스키마에 적용하는 명령은 [테스트와 검사](#테스트와-검사)에 있다.

**자동으로 만든 마이그레이션은 읽어 보고 커밋한다.** 만든 파일은 ruff 가 바로 모양을 맞춘다(`alembic.ini` 의 `post_write_hooks`).
모델 파일을 새로 만들면 `migrations/env.py` 와 `tests/cleaning.py` 에서 그 모듈을 불러온다. 불러오지 않으면 Alembic 이 그 테이블을 모른다.

적용한 기록은 스키마마다 `alembic_version` 테이블에 남는다.

| 테이블 | 내용 |
| --- | --- |
| `boards` | 게시판. 주소의 이름(`slug`), 보이는 이름, 설명, 누가 쓰는가(`write_policy`), 차례 |
| `posts` | 글. 번호(순번), 게시판, 글쓴이의 ID(탈퇴했으면 비었다), 제목, 본문, 쓴 시각, 고친 시각, 지운 시각, 고정한 시각과 끝나는 시각 |
| `comments` | 댓글과 답글. 번호(순번), 글, 어느 댓글의 답글인가(`parent_id`), 글쓴이의 ID(탈퇴했으면 비었다), 내용, 쓴 시각, 고친 시각, 지운 시각 |
| `authors` | 글쓴이의 닉네임. 사람마다 한 줄. 사람의 ID, 닉네임, 이름을 바꿔 적은 시각 |
| `reports` | 글과 댓글의 신고. 번호(순번), 글이나 댓글(둘 가운데 하나), 신고한 사람의 ID(탈퇴했으면 비었다), 사유, 설명, 신고한 시각, 처리한 시각·운영자·결과 |
| `outgoing_notifications` | 알림 서버에 보낼 알림의 발송함([알림 보내기](#알림-보내기)). 칸과 규칙은 공용 코드(`server_core/notifications/models.py`)에 있다 |

마이그레이션은 하나(기준선, `migrations/versions/20261025_1446cbdea135_board_baseline.py`)에서 시작한다. NestJS(TypeORM) 때의 마지막 마이그레이션(`AllowWithdrawnAuthors`)과 같은 모양이다. 표와 칸, 제약과 색인의 이름도 그때와 같다.

- **빈 스키마**에서는 표를 모두 만들고 게시판 넷을 넣는다.
- **TypeORM 이 이미 표를 만든 스키마**(지금 스키마에 `posts` 가 있다)에서는 표를 만들지 않고 그대로 넘겨받는다. TypeORM 의 적용 기록 표(`migrations`)만 지운다. 글, 댓글, 신고, 닉네임, 발송함의 데이터는 그대로다.
  넘겨받기 전에 기록 표로 TypeORM 의 마지막 마이그레이션(`AllowWithdrawnAuthors1792600000000`)까지 적용됐는지 본다.
  뒤의 둘(`DropOperators`, `AllowWithdrawnAuthors`)이 빠졌으면 그 SQL 을 마저 한다. 그보다 앞의 것이 빠졌으면 넘겨받지 않고 멈춘다(`IncompleteTypeormSchema`, 아무것도 바꾸지 않는다).
  그 스키마가 개발용 데이터라면 표를 모두 지운 뒤 다시 적용한다.

**NestJS 때의 DB 를 쓰던 PC 에서 옮길 때.** 어디까지 적용됐는지는 저장소 루트에서 이렇게 본다. `AllowWithdrawnAuthors1792600000000`, `DropOperators1792430000000`, `AddOutgoingNotifications1792340930107` 가운데 하나면 기준선이 마저 해서 넘겨받는다.

```
docker compose exec db psql -U trpg -d trpg -c "SELECT name FROM board.migrations ORDER BY timestamp DESC LIMIT 1"
```

그다음 두 스키마에 한 번씩 적용한다.

```
# PowerShell
uv run alembic upgrade heads; $env:DB_SCHEMA='board_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA

# bash
uv run alembic upgrade heads && DB_SCHEMA=board_test uv run alembic upgrade heads
```

**기준선을 되돌리면(`downgrade base`) 표를 모두 지운다.** 넘겨받은 스키마여도 같다. 데이터가 있는 개발용 스키마에서는 쓰지 않는다. CI 는 빈 DB 에서 끝까지 되돌리고 다시 적용해 본다.

게시판은 마이그레이션이 넣는다. 게시판을 더하려면 행을 넣는 새 마이그레이션을 만든다. 이미 적용된 마이그레이션 파일은 고치지 않는다.

## API

게시판 서버의 API는 `/api/v1/board/` 아래에 놓는다. 아래 표의 경로는 `/health` 둘을 빼고 모두 그 뒤에 붙는다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버가 살아 있는지 확인 | 불필요 |
| GET | `/health/ready` | 요청을 처리할 준비가 됐는지 확인(DB 에 3초 안에 닿는가). 닿지 않으면 503 | 불필요 |
| GET | `/me` | 토큰의 주인이 누구인지 확인. `{"user_id": "...", "is_operator": false}`. 운영자인지는 토큰의 `roles` 를 읽은 것이다 | 필요 |
| GET | `/boards` | 게시판 목록. 정해 둔 차례대로 | 불필요 |
| GET | `/boards/{slug}/posts` | 한 게시판의 글 목록. 새 글부터, 본문 없이. 첫 쪽에는 고정한 글을 따로 싣는다. `?page=1&size=20` | 불필요 |
| POST | `/boards/{slug}/posts` | 글 쓰기. `{"title", "content"}`. 201 과 쓴 글 | 필요 |
| GET | `/posts` | 글 검색. `?q=고정+버그`. 제목과 본문에서 찾는다. `&board=free&page=1&size=20` | 불필요 |
| GET | `/posts/{id}` | 글 하나를 본문까지 | 불필요 |
| PATCH | `/posts/{id}` | 글 고치기. 고칠 칸만 보낸다. 글쓴이만. 운영자만 쓰는 게시판의 글은 지금 운영자인 글쓴이만 | 필요 |
| DELETE | `/posts/{id}` | 글 지우기. 글쓴이와 운영자. 운영자만 쓰는 게시판의 글은 운영자만. 204 | 필요 |
| PUT | `/posts/{id}/pin` | 글 고정하기. `{"days": 7}`(본문이 없거나 적지 않으면 7일, 365일까지). 운영자만. 204 | 필요 |
| DELETE | `/posts/{id}/pin` | 글의 고정 풀기. 운영자만. 204 | 필요 |
| GET | `/posts/{postId}/comments` | 한 글의 댓글 목록. 먼저 쓴 것부터, 답글을 붙여서. `?after=57&size=20` | 불필요 |
| POST | `/posts/{postId}/comments` | 댓글 쓰기. `{"content"}`. 답글이면 `{"content", "parent_id"}`. 201 과 쓴 댓글 | 필요 |
| PATCH | `/comments/{id}` | 댓글 고치기. `{"content"}`. 글쓴이만 | 필요 |
| DELETE | `/comments/{id}` | 댓글 지우기. 글쓴이와 운영자. 204 | 필요 |
| POST | `/posts/{id}/reports` | 글 신고하기. `{"reason", "description"}`. 201 | 필요 |
| POST | `/comments/{id}/reports` | 댓글(답글 포함) 신고하기. 201 | 필요 |
| GET | `/reports` | 열린 신고를 신고당한 것마다 묶은 목록. 오래 기다린 것부터. `?page=1&size=20`. 운영자만 | 필요 |
| GET | `/posts/{id}/reports` | 한 글에 걸린 신고 모두(처리한 것도). 최근 것부터, 설명과 신고한 사람까지. `?page=1&size=20`. 운영자만 | 필요 |
| GET | `/comments/{id}/reports` | 한 댓글에 걸린 신고 모두. `?page=1&size=20`. 운영자만 | 필요 |
| PUT | `/posts/{id}/reports/outcome` | 한 글에 걸린 열린 신고를 모두 닫기. `{"outcome": "actioned"}`. 운영자만. 204 | 필요 |
| PUT | `/comments/{id}/reports/outcome` | 한 댓글에 걸린 열린 신고를 모두 닫기. 운영자만. 204 | 필요 |
| POST | `/service/users/{userId}/withdrawal` | 탈퇴를 받는다. `{"withdrawn_at"}`. 200 `{"status": "processed"}`. 인증 서버만([탈퇴 받기](#탈퇴-받기)) | 인증 서버의 서명 |

`/health` 둘은 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다. 둘 다 HEAD 도 받는다.

글 하나는 이렇게 생겼다. 목록의 한 줄에는 `content`가 없다.

```json
{
  "id": "1234",
  "board": "free",
  "author_id": "0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b",
  "author_nickname": "모험가",
  "author_withdrawn": false,
  "title": "제목",
  "comment_count": 3,
  "pinned": false,
  "pinned_until": null,
  "content": "본문",
  "created_at": "2026-10-11T09:00:00.000Z",
  "updated_at": "2026-10-11T09:00:00.000Z"
}
```

시각은 언제나 UTC 의 밀리초까지와 `Z` 다(`app/core/times.py`). NestJS 때와 같은 모양이다.

`author_nickname`은 글쓴이의 닉네임이다. 인증 서버가 access 토큰에 실어 보낸 이름을 이 서버가 적어 둔 것이다.
이 서버가 이름을 모르는 사람(이 기능 전에 쓰고 그 뒤로 로그인한 채 들어온 적이 없는 사람)이면 `null`이다. 화면은 "알 수 없음"으로 그리면 된다.
닉네임을 바꾸면 그 사람이 로그인한 채로 이 서버를 처음 부를 때(글을 쓰지 않아도, `GET /me`만 불러도) 예전 글과 댓글에도 새 이름이 나온다. 로그인 없이 부르는 주소(목록, 읽기)는 토큰을 보지 않는다.

`author_withdrawn`은 글쓴이가 탈퇴했는지다. 탈퇴했으면 `author_id`와 `author_nickname`이 `null`이다. 화면은 "탈퇴한 사용자"로 그리면 된다([탈퇴 받기](#탈퇴-받기)).
이름을 모르는 사람(`author_nickname`만 `null`)과 가른다. 댓글도 같다. 지운 댓글은 누가 썼는지 보이지 않으므로 `false`다.

`comment_count`는 그 글의 살아 있는 댓글과 답글의 수다. 지운 것은 세지 않는다. 답글이 남아 "삭제된 댓글입니다"로 보이는 자리도 세지 않는다.
글 목록의 줄에도 실린다. 목록의 줄은 글 하나에서 `content`만 뺀 모양이다.

글 목록은 쪽 번호로 나눈다. `page`는 1 부터 10000 까지, `size`는 1 부터 50 까지다. `total`로 쪽의 수를 셈한다.

```json
{ "pinned": [ ... ], "items": [ ... ], "page": 1, "size": 20, "total": 137 }
```

`pinned`는 지금 고정되어 있는 글들이다. 나중에 고정한 것부터 온다. 첫 쪽(`page=1`)에만 싣고, 다른 쪽에서는 빈 목록이다.
고정한 글은 `items`와 `total`에 들지 않고 `size`에도 세지 않는다. 첫 쪽에는 고정한 글에 더해 `size`개의 글이 온다.

고정은 운영자가 한다(`PUT /posts/{id}/pin`). 며칠 동안인지 `days`로 정하고, 적지 않으면 7일이다. 그날이 지나면 저절로 내려가 제 번호의 자리로 돌아온다.
고정한 글의 `pinned`는 `true`고 `pinned_until`은 끝나는 시각이다. 고정이 끝났거나 푼 글은 `false`와 `null`이다.
이미 고정한 글을 다시 고정하면 기간을 새로 잡고 맨 위로 올린다. 한 게시판에 함께 고정해 둘 수 있는 글은 5개다. 넘으면 409 다.

글 검색(`GET /posts?q=`)은 제목과 본문에서 낱말을 찾는다. 결과는 글 목록과 같은 모양이고(`items`, `page`, `size`, `total`) 새 글부터 온다. `pinned`는 따로 싣지 않는다.

- 빈칸으로 낱말을 나눈다. **모든 낱말이** 제목이나 본문에 들어 있는 글이 나온다. 한 낱말은 제목에, 다른 낱말은 본문에 있어도 된다.
- 낱말의 어디에 있든 찾는다. `공지`로 `공지사항을`을 찾는다. 대소문자를 가리지 않는다.
- 낱말은 2자 이상, 5개까지, 검색어 전체는 50자까지다. `%`와 `_`는 글자로 찾는다.
- `board`를 적으면 그 게시판에서만, 적지 않으면 모든 게시판에서 찾는다. 없는 게시판이면 404 다. 줄마다 어느 게시판의 글인지(`board`) 실린다.
- 댓글에서는 찾지 않는다. 지운 글은 나오지 않는다.
- 검색 하나에 3초까지 쓴다. 넘으면 멈추고 503 으로 답한다.

제목은 100자, 본문은 20000자까지다. 제목의 앞뒤 빈칸은 떼고, 본문은 받은 그대로 저장한다. 빈칸만 적은 제목과 본문, NUL 글자는 받지 않는다.

댓글 목록은 글에 단 댓글마다 거기 달린 답글(`replies`)을 모두 붙여 돌려준다. 답글에는 답글을 달 수 없다.

```json
{
  "items": [
    {
      "id": "57",
      "post_id": "1234",
      "parent_id": null,
      "author_id": "0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b",
      "author_nickname": "모험가",
      "author_withdrawn": false,
      "content": "댓글",
      "deleted": false,
      "created_at": "2026-10-11T09:10:00.000Z",
      "updated_at": "2026-10-11T09:10:00.000Z",
      "replies": [
        { "id": "58", "post_id": "1234", "parent_id": "57", "author_id": "...", "author_nickname": "...", "author_withdrawn": false, "content": "답글", "deleted": false, "created_at": "...", "updated_at": "..." }
      ]
    }
  ],
  "next": "57"
}
```

댓글 목록은 쪽 번호가 아니라 "이것 다음 몇 개"로 이어 읽는다. `next`가 있으면 뒤에 더 있는 것이다. 그 값을 `after`에 넣어 다시 부른다. 없으면(`null`) 끝이다.
`size`는 글에 단 댓글의 수다(1 부터 50 까지). 답글은 세지 않는다.

지운 댓글은 목록에서 빠진다. 답글이 달린 댓글은 지워도 자리가 남는다. 그때는 `deleted`가 `true`고 `author_id`, `author_nickname`, `content`가 `null`이다(`author_withdrawn`은 `false`). 화면은 "삭제된 댓글입니다"로 그리면 된다.

댓글은 2000자까지다. 한 댓글에 답글은 100개까지 단다.

글과 댓글, 신고는 할 수 있는 횟수에 끝이 있다. 사람마다 따로 센다. 운영자는 걸리지 않는다.

| | 한도 |
| --- | --- |
| 글 | 10분에 5개 |
| 댓글과 답글 | 1분에 10개 |
| 신고 | 1시간에 20건 |

넘기면 429 다. 가장 먼저 쓴 것이 그 시간을 벗어나면 하나를 더 쓸 수 있고, 그때까지 남은 초가 `retry_after`다(1 이상의 정수로 올린다). 같은 값이 `Retry-After` 머리말에도 실린다.
쓰고 지워도 쓴 것으로 센다. 고치기와 지우기는 세지 않는다.

```json
{ "detail": "글을 너무 자주 쓰고 있습니다. 잠시 후 다시 시도해 주세요.", "retry_after": 142 }
```

로그인한 사람은 남의 글과 댓글을 신고한다. 사유(`reason`)는 다섯 가운데 하나다.

| `reason` | 뜻 |
| --- | --- |
| `spam` | 스팸, 광고 |
| `abuse` | 욕설, 괴롭힘 |
| `sexual` | 음란물 |
| `illegal` | 불법 정보 |
| `other` | 기타. 설명(`description`)을 꼭 적는다 |

설명은 500자까지고 적지 않아도 된다(`other`만 빼고). 받은 그대로 저장하고, 로그에는 남기지 않는다.
신고한 사람에게는 접수했다는 것만 돌려준다(`{"id", "reason", "created_at"}`). 누가 신고했는지는 운영자만 본다. 글쓴이도 보지 못한다.

- 같은 사람이 같은 것을 두 번 신고하지 못한다(409). 처리해서 닫힌 신고가 있어도 그렇다.
- 자기 글과 자기 댓글은 신고하지 못한다(403).
- 지운 글과 지운 댓글, 지운 글에 달린 댓글은 신고하지 못한다(404). 읽을 수 없는 것이다.
- 신고가 쌓여도 글을 저절로 가리지 않는다. 운영자가 본다.

운영자의 목록(`GET /reports`)은 열린 신고를 신고당한 것마다 한 줄로 묶는다. 처음 신고가 이른 것부터다.

```json
{
  "items": [
    {
      "target": { "type": "comment", "id": "57", "post_id": "1234", "deleted": false },
      "open_count": 3,
      "reasons": { "spam": 2, "abuse": 0, "sexual": 0, "illegal": 0, "other": 1 },
      "first_reported_at": "2026-10-12T09:00:00.000Z",
      "last_reported_at": "2026-10-12T09:40:00.000Z"
    }
  ],
  "page": 1, "size": 20, "total": 1
}
```

`post_id`는 글이면 그 글, 댓글이면 그 댓글이 달린 글의 번호다. `deleted`는 신고당한 것이 지금 지워져 있는지다.
신고 하나하나(설명, 신고한 사람)는 `GET /posts/{id}/reports`, `GET /comments/{id}/reports`로 본다. 처리한 신고도 나온다. 글 목록처럼 쪽으로 나눈다(`items`, `page`, `size`, `total`).

```json
{ "id": "9", "reason": "other", "description": "설명", "reporter_id": "7d0e3a52-...", "created_at": "...", "handled_at": null, "handled_by": null, "outcome": null }
```

처리(`PUT .../reports/outcome`)는 그것에 걸린 열린 신고를 한 번에 모두 닫는다. 결과(`outcome`)는 `actioned`(조치함)나 `dismissed`(문제없음)다.
처리한 시각과 운영자가 함께 남는다. 닫은 뒤에 새 신고가 오면 다시 목록에 나온다. 열린 신고가 없으면 404 다.
글을 지우는 것은 처리와 따로, 지우기 API(`DELETE /posts/{id}`)로 한다. 지운 것에 걸린 신고도 처리해야 목록에서 빠진다.

**오류는 언제나 `{"detail": "문장"}`이다.** 다른 서버들과 같은 칸 이름이다. 입력이 틀렸을 때는 어느 칸이 왜 틀렸는지를 `errors`에 더한다(`app/core/errors.py`).

```json
{ "detail": "입력이 올바르지 않습니다.", "errors": { "title": ["제목을 적어야 합니다."] } }
```

입력 오류의 상태 코드는 400 이다. 다른 FastAPI 서버들은 422 지만, 이 서버는 NestJS 때부터의 계약을 지킨다. `errors` 의 칸 이름과 문장, 문장의 차례도 그때와 같다(`app/core/checks.py`).

| 상태 | 언제 |
| --- | --- |
| 400 | 입력이 틀렸다. 모르는 칸을 보냈다. 고칠 칸을 하나도 보내지 않았다. JSON 이 깨졌다. 주소에 같은 이름의 값을 여러 번 붙였다. 답글을 달 댓글이 없거나 그것이 답글이다 |
| 401 | 로그인이 필요한데 토큰이 없거나 받아들일 수 없다 |
| 403 | 운영자만 쓰는 게시판에 썼다. 남의 글이나 댓글을 고치거나 지우려 했다. 운영자에서 내려온 뒤에 운영자만 쓰는 게시판의 제 글을 고치거나 지우려 했다. 자기 글이나 댓글을 신고했다. 운영자가 아닌데 신고를 읽거나 처리하려 했다. 운영자가 아닌데 글을 고정하거나 풀려 했다 |
| 404 | 없는 게시판, 없는 글, 없는 댓글, 지운 것, 없는 주소. 주소의 번호나 게시판 이름이 그 모양이 아니다. 처리할 신고가 없다 |
| 405 | 있는 주소에 받지 않는 메서드로 불렀다 |
| 409 | 한 댓글에 달 수 있는 답글이 다 찼다. 한 게시판에 고정할 수 있는 글이 다 찼다. 이미 신고했다 |
| 429 | 글이나 댓글을 너무 자주 썼다. 신고를 너무 자주 했다. `retry_after`(초)와 `Retry-After` 머리말이 기다릴 시간이다 |
| 500 | 서버의 잘못. 무슨 일인지는 응답에 싣지 않고 로그에 남긴다 |
| 503 | 검색이 정해 둔 시간(3초)을 넘겨 멈췄다. 인증 서버의 공개키를 구하지 못했다(아래) |

로그인이 필요한 주소는 토큰을 먼저 본다(401). 그다음이 주소의 모양(404), 본문과 주소 뒤의 값(400)이다.
다만 JSON 이 깨진 본문은 FastAPI 가 본문을 읽을 때 거절하므로 토큰을 보기 전에 400 이다.

**로그인이 필요한 API 는 인자로 요청한 사람(`Member`, `app/core/auth.py`)을 받는다.** 토큰은 `Authorization: Bearer <access 토큰>` 머리말로 보낸다. 검증은 공용 코드(`server_core/auth/`)가 한다.

| 상태 | 언제 | 응답 |
| --- | --- | --- |
| 401 | 토큰이 없거나 받아들일 수 없다 | `{"detail": "인증이 필요합니다."}`, `WWW-Authenticate: Bearer` |
| 503 | 인증 서버의 공개키를 구하지 못해 확인할 수 없다 | `{"detail": "지금은 인증을 확인할 수 없습니다. ..."}`, `Retry-After: 60` |

401 은 왜 틀렸는지 알리지 않는다. 만료든 서명이 틀렸든 끊긴 세션이든 응답이 같다. 클라이언트는 401 이면 토큰을 갱신하고, 503 이면 로그아웃시키지 않고 잠시 뒤 다시 부른다.
게임 서버와 같은 응답이다.

### API 목록(OpenAPI)

화면의 타입과 디자인 도구에 넘기는 API 목록은 [`docs/api/board.openapi.json`](../docs/api/board.openapi.json)이다(#559, [API 목록](../docs/api/README.md)).
코드에서 뽑는다. 손으로 고치지 않는다. API 를 바꾸면 저장소 루트에서 다시 뽑아 함께 커밋한다. 빠뜨리면 CI 의 `api-docs` 가 실패한다.

```
uv run --no-project python tools/export_openapi.py board
```

도구는 이 서버의 uv 환경에서 앱(`app.main`)을 불러 FastAPI 가 만드는 목록을 받는다. 다른 FastAPI 서버들과 같다.
서버를 띄우지 않고 DB 에도 닿지 않는다(필수 설정이 비어 있으면 닿지 않는 주소를 채워 넣는다). 운영 서버는 `/docs` 를 열지 않는다(`DEBUG` 를 켤 때만). 바깥에 나가는 목록은 저장소의 파일뿐이다.

목록에는 이렇게 적힌다.

- **응답의 모양**은 라우터의 `response_model`(`app/*/schemas.py` 의 Pydantic 모델)이다. 칸의 `Field(description=...)` 이 설명으로 실린다.
- **주소 뒤의 값**(`page`, `size`, `q`, `board`, `after`)은 앱이 직접 읽으므로(`app/core/query_params.py`) FastAPI 가 스스로 적지 못한다. 라우터의 `openapi_extra=query_parameters(...)` 가 모델의 칸을 쿼리 값으로, 그 입력 오류를 400 의 `InputError` 로 적는다.
- **입력 오류**는 400 의 `InputError` 로 적힌다(`app/core/errors.py` 의 `use_error_bodies`). 그 밖의 거절(401, 403, 404, 409, 429)은 목록에 적지 않는다.
- **로그인이 필요한 API** 에는 bearer 토큰(`HTTPBearer`)이 붙는다. 로그인 없이 부르는 API 에는 붙지 않는다.
- **누가 부르는가**(`x-audience`)는 도구가 주소로 정한다. `/health` 는 `infra`, `/service/` 는 `service`, 그 밖은 `user` 다. 탈퇴를 받는 주소는 앱도 `service` 로 적는다(`openapi_extra`).
  운영자의 API(고정, 신고 읽기와 처리)는 주소에 `/admin/` 이 없어 도구가 알아보지 못한다. 그래서 앱이 `openapi_extra=FOR_OPERATORS`(`app/core/auth.py`)로 `operator` 라고 적는다.
  표시는 목록에만 쓰인다. 운영자만 부르게 막는 것은 서비스가 한다.

## 알림 보내기

내 글에 댓글이 달리거나 내 댓글에 답글이 달리면 그 사람의 알림함에 알린다(#385, `app/notifications/`). 알림함은 알림 서버에 있다([알림 서버의 README](../notification-server/README.md)).

| 알림의 `kind` | 언제, 누구에게 | `payload` |
| --- | --- | --- |
| `post.commented` | 내 글에 댓글이 달렸다. 글쓴이에게 | `board_slug`, `post_id`, `post_title`, `comment_id` |
| `comment.replied` | 내 댓글에 답글이 달렸다. 그 댓글의 글쓴이에게 | 위에 더해 `parent_id`(답글을 단 댓글) |

- **자기에게는 알리지 않는다.** 자기 글에 단 댓글, 자기 댓글에 단 답글은 알림이 없다.
- **답글은 댓글의 글쓴이에게만 간다.** 글쓴이에게 "글에 댓글이 달렸다"를 또 보내지 않는다. 답글마다 둘씩 가면 시끄럽다.
- **댓글의 글은 싣지 않는다.** 댓글을 지워도 알림함에는 남기 때문이다. 화면은 글로 가서 댓글을 본다.
- **발송함에 먼저 적는다.** 댓글을 저장하는 트랜잭션에 발송함(`outgoing_notifications`)에 한 줄을 적고, 알림 서버에는 뒤에서 5초마다 보낸다.
  댓글만 남고 알림이 사라지거나, 알림만 가고 댓글이 되돌려지는 일이 없다. 알림 서버가 죽어도 댓글은 써진다.
- 열쇠(`source_key`)는 `<kind>:<댓글 번호>` 다. 다시 보내도, 서버가 여럿이어도 알림 서버에는 한 줄이다.
- 보내면 줄을 지운다. 닿지 못하면(연결 실패, 시간 초과, 401, 408, 429, 5xx) 10초부터 두 배씩 1시간까지 늘려 다시 보낸다.
  알림 서버가 받지 않으면(409, 413, 422 등) 버그라 `failed` 로 두고 다시 보내지 않는다. 7일 넘게 못 보낸 것은 지운다. 게임 서버의 발송함과 같은 규칙이다.
- 보내는 일과 서명은 공용 코드가 한다(`server_core/notifications/dispatcher.py`, `client.py`). 이 서버는 무엇을 누구에게 알릴지만 정한다(`app/notifications/outbox.py`).
  주소는 `POST /api/v1/notification/service/board/notifications` 다. 한 바퀴에 50개까지 보낸다.

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `NOTIFICATION_URL` | 없음(보내지 않음) | 알림 서버의 주소. `http://127.0.0.1:8004`. 비우면 발송함에 적기만 한다(7일이 지나면 지워진다) |
| `NOTIFICATION_SECRET` | 없음 | 요청에 서명하는 비밀. 알림 서버의 `BOARD_SERVER_SECRET` 과 같은 값, 32자 이상. `NOTIFICATION_URL` 을 적었으면 없거나 짧을 때 서버가 뜨지 않는다. 비밀값이다 |
| `NOTIFICATION_TIMEOUT_SECONDS` | `5` | 알림 서버의 답을 기다리는 시간(초, 30까지). 넘기면 다시 보낼 일이다 |

**알림 서버와 붙여 보기.** 알림 서버가 떠 있어야 한다. `tools/fill_env.py` 가 두 파일(`notification-server/.env` 의 `BOARD_SERVER_SECRET`, `board-server/.env` 의 `NOTIFICATION_SECRET`)에 같은 비밀을 채운다.
그다음 `board-server/.env` 의 `NOTIFICATION_URL` 앞의 `#` 를 지운다. 비밀을 손으로 만들려면 **저장소 루트에서** 아래를 실행한다. 값은 화면에 찍히지 않는다.
`notification-server/.env` 에 `BOARD_SERVER_SECRET` 이 이미 있으면 이 명령 대신 그 값을 `NOTIFICATION_SECRET` 으로 옮겨 적는다.

```powershell
$b = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); $s = [BitConverter]::ToString($b).Replace('-','').ToLower(); Add-Content notification-server/.env "`nBOARD_SERVER_SECRET=$s"; Add-Content board-server/.env "`nNOTIFICATION_URL=http://127.0.0.1:8004`nNOTIFICATION_SECRET=$s"; Remove-Variable s, b
```

```bash
s=$(openssl rand -hex 32); printf '\nBOARD_SERVER_SECRET=%s\n' "$s" >> notification-server/.env; printf '\nNOTIFICATION_URL=http://127.0.0.1:8004\nNOTIFICATION_SECRET=%s\n' "$s" >> board-server/.env; unset s
```

두 서버를 다시 띄우고 남의 글에 댓글을 달면 몇 초 뒤 글쓴이의 알림함(`GET /api/v1/notification/me/notifications`)에 알림이 생긴다.

**알려진 한계**
- 신고의 처리(운영자가 글이나 댓글을 내린 것)는 알리지 않는다.
- 실패로 남긴 알림을 다시 보내는 명령이 없다. 로그(`notification.rejected`)를 보고 고친 뒤 DB 에서 지운다.
- 글쓴이가 탈퇴한 글과 댓글에 달린 것은 알리지 않는다. 받을 사람이 없다([탈퇴 받기](#탈퇴-받기)).

## 탈퇴 받기

인증 서버는 탈퇴를 요청하고 7일(유예)이 지난 계정을 비운 뒤 서버마다 알린다(#603, [탈퇴 설계](../docs/architecture/withdrawal.md)). 이 서버는 그 사람의 것을 정리한다(`app/withdrawal/`).

```
POST /api/v1/board/service/users/{userId}/withdrawal
X-Service-Signature: t=<보낸 시각(초)>,v1=<서명>        (AUTH_SERVER_SECRET)
Content-Type: application/json

{"withdrawn_at": "2026-10-28T03:00:00+00:00"}
```

| 무엇 | 처리 |
| --- | --- |
| 글, 댓글(지운 것도) | 남긴다. 함께한 사람의 대화다. 글쓴이(`author_id`)만 비운다. 고친 시각(`updated_at`)은 그대로다 |
| 신고 | 남긴다. 운영의 기록이다. 신고한 사람(`reporter_id`)만 비운다. 처리한 운영자(`handled_by`)는 남긴다 |
| 닉네임(`authors`) | 지운다 |
| 그 사람에게 보낼 알림(발송함) | 지운다 |

| 답 | 뜻 |
| --- | --- |
| 200 `{"status": "processed"}` | 정리했다. 이미 했거나 이 서버가 모르는 사람이어도 같다 |
| 400 | 주소의 `userId` 가 하이픈이 있는 UUID 가 아니다, `withdrawn_at` 이 없거나 시간대가 있는 ISO 8601 시각이 아니다, 모르는 칸이 있다 |
| 401 | 서명이 없거나 맞지 않거나 5분을 넘겼다. 사용자의 토큰으로는 부를 수 없다. `AUTH_SERVER_SECRET` 이 비어 있으면 모두 401 이다 |

- **번호를 남기지 않는 까닭.** 응답의 `author_id` 는 누구나 본다. 남기면 탈퇴한 사람의 글을 한데 모을 수 있다. 그래서 비운다
- **비운 뒤.** 그 글과 댓글은 누구의 것도 아니다. 고칠 사람이 없고 운영자만 지운다. 누구나 신고한다. 달린 댓글과 답글은 알리지 않는다
- **한 트랜잭션이다.** 몇 번을 받아도 같다. 중간에 실패하면 아무것도 바뀌지 않는다. 인증 서버는 200 과 `processed` 를 받을 때까지 다시 보낸다
- **서명은 받은 바이트 그대로에 확인한다.** 본문은 받은 바이트(`request.body()`), 경로는 퍼센트 인코딩을 풀지 않은 그대로(앞부분 `/api/v1/board` 와, 있으면 쿼리까지)다(`app/core/service_auth.py`).
  서명의 셈은 공용 코드(`server_core/service_auth/signing.py`)의 것이다. 알림 서버에 보낼 때 서명하는 코드와 같다. 시각이 앞뒤 5분을 넘긴 서명은 받지 않는다
- **검사의 차례는 서명(401), 주소의 번호(400), 본문(400)이다.** 서명을 확인하기 전에는 본문의 칸이 무엇이 틀렸는지 알려 주지 않는다. NestJS 때와 같은 차례다.
  다만 JSON 이 깨진 본문은 FastAPI 가 본문을 읽을 때 거절하므로 서명을 보기 전에 400 이다(칸은 싣지 않는다)
- 쿼리는 표에 직접 닿는다(`app/withdrawal/repository.py`). 글쓴이와 신고한 사람의 칸만 바꾸고 고친 시각은 건드리지 않는다. 글쓴이를 비운 것은 글을 고친 것이 아니다
- 로그에는 정리한 수만 남긴다(`operation`: `board.withdrawal`, `blanked_posts`, `blanked_comments`, `blanked_reports`, `deleted_authors`, `deleted_notifications`). 사람은 남기지 않는다

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `AUTH_SERVER_SECRET` | 없음(받지 않음) | 인증 서버의 서명을 확인하는 비밀. 인증 서버의 `BOARD_SECRET` 과 같은 값, 32자 이상. 짧으면 서버가 뜨지 않는다. 비우면 탈퇴의 알림을 401 로 거절한다(인증 서버는 쌓아 두었다가 적은 뒤에 다시 보낸다). 비밀값이다 |

`tools/fill_env.py` 가 두 파일(`auth-server/.env` 의 `BOARD_SECRET`, `board-server/.env` 의 `AUTH_SERVER_SECRET`)에 같은 값을 채운다.

## 구조

```
app/
  __main__.py                    서버를 띄운다(uv run python -m app). 주소와 포트를 설정에서 읽는다
  main.py                        앱을 만든다(create_app). 미들웨어, 라우터, 오류의 모양, 뒤의 작업(끊긴 세션 목록, 알림 보내기)
  core/
    config.py                    설정. 공용 코드의 CoreSettings 와 NotificationSettings 에 이 서버의 칸을 더한다
    database.py                  테이블 모델의 부모(Base). 엔진과 세션은 공용 코드가 만든다
    dependencies.py              요청 하나의 DB 세션(Session)과 앱의 설정(AppSettings)
    auth.py                      로그인이 필요한 API 의 사람(Member, Actor). 토큰의 닉네임을 적는다
    errors.py                    오류 응답의 모양({"detail"}, 입력 오류 400). 이 서버의 거절(ApiError)
    checks.py                    요청의 칸을 검사하는 도구. NestJS 때와 같은 문장과 차례를 낸다
    query_params.py              주소 뒤의 값을 요청 모델로 읽는다. 같은 이름이 여러 번이면 거부한다
    ids.py                       글, 댓글, 신고의 번호. 주소의 번호를 검사하고 응답에는 글자로 싣는다
    times.py                     응답의 시각 모양(UTC 의 밀리초와 Z)
    write_limits.py              글과 댓글, 신고를 얼마나 자주 할 수 있는가. 최근의 행을 세어 본다
    service_auth.py              인증 서버가 서명한 요청만 들여보낸다(탈퇴)
    metrics.py                   게시판 서버만의 메트릭(쓰기, 신고, 검색)
  api/
    health.py                    살아 있는지 확인하는 API
    readiness.py                 준비됐는지(DB 에 닿는지) 확인하는 API
    me.py                        토큰의 주인을 돌려주는 API
  boards/
    models.py                    boards 테이블
    service.py                   게시판을 읽는다. 주소의 게시판 이름을 검사한다
    schemas.py                   게시판의 응답
    router.py                    게시판 목록의 API
  posts/
    models.py                    posts 테이블
    policy.py                    누가 쓰고 고치고 지우고 고정하는가, 몇 개까지인가, 쪽 나누기의 값
    schemas.py                   글을 쓰고 고치고 고정할 때 받는 값, 목록과 검색의 주소 값, 응답
    repository.py                글과 댓글 수를 DB 에서 읽고 쓴다. 검색의 쿼리와 시간 제한
    service.py                   글을 읽고, 쓰고, 고치고, 지우고, 고정한다
    terms.py                     검색어를 낱말로 나누고 LIKE 의 모양으로 바꾸는 셈
    search.py                    글을 검색한다(3초 제한, 메트릭)
    router.py                    글, 고정, 검색의 API
  comments/
    models.py                    comments 테이블. 댓글과 답글을 함께 둔다
    policy.py                    누가 고치고 지울 수 있는가, 어디에 답글을 달 수 있는가, "이것 다음 몇 개"로 끊어 읽는 셈
    schemas.py                   댓글을 쓰고 고칠 때 받는 값, 목록의 주소 값, 응답과 댓글을 답글과 묶는 셈
    repository.py                댓글을 DB 에서 읽고 쓴다
    service.py                   댓글을 읽고, 쓰고, 고치고, 지운다. 새 댓글의 알림을 발송함에 적는다
    router.py                    댓글의 API
  authors/
    models.py                    authors 테이블. 사람마다 닉네임 한 줄
    service.py                   토큰의 닉네임을 받아들일지 정하고 적어 둔다. 최근에 적은 것을 기억한다
  reports/
    models.py                    reports 테이블. 글의 신고와 댓글의 신고를 함께 둔다
    policy.py                    사유와 처리 결과, 누가 무엇을 신고할 수 있는가
    targets.py                   신고하는 것(글이나 댓글)을 가리키는 값
    schemas.py                   신고하고 처리할 때 받는 값, 목록의 주소 값, 응답
    errors.py                    신고를 다루다 거절할 때의 응답들
    repository.py                신고를 DB 에서 읽고 쓴다. 열린 신고를 묶는다
    service.py                   신고한다(신고한 사람의 쪽)
    reviews.py                   신고를 묶어 읽고 처리한다(운영자의 쪽)
    router.py                    신고의 API
  notifications/                 사용자의 알림함(알림 서버)에 넣기(#385)
    models.py                    발송함의 한 줄. 칸은 공용 코드에 있다
    outbox.py                    새 댓글을 누구에게 무슨 알림으로 보낼지 정해 발송함에 적는다. 탈퇴한 사람의 것을 지운다
  withdrawal/                    인증 서버가 알린 탈퇴를 받는다(#603)
    schemas.py                   본문(withdrawn_at)과 답
    repository.py                글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임을 지우는 쿼리
    service.py                   한 트랜잭션으로 정리하고 정리한 수를 로그에 남긴다
    router.py                    POST /service/users/{userId}/withdrawal
migrations/
  env.py                         Alembic 이 부르는 파일. 앱의 설정과 엔진으로 연결한다
  versions/                      마이그레이션 파일
tests/
  conftest.py                    테스트의 준비물(테스트용 설정, 공용 DB 풀, 가짜 인증 서버, 토큰, 메트릭)
  cleaning.py                    테스트가 시작할 때 테이블을 비운다
  test_*.py                      앱에 요청을 바로 넘겨 보는 테스트와 순수한 함수의 테스트
contract/
  harness/                       서버를 띄우고, 가짜 인증 서버, 토큰, 서명, DB 를 다루는 도구
  tests/                         HTTP 로만 부르는 시나리오
alembic.ini                      Alembic 의 설정. DB 주소는 적지 않는다
pyproject.toml                   의존성과 pytest, coverage, ruff 의 설정
Dockerfile                       서버의 이미지
```

라우터, 서비스, 저장소(repository), 규칙(policy)을 나누는 방식은 게임 서버와 같다.

| 파일 | 하는 일 |
| --- | --- |
| `router.py` | 주소를 받아 서비스를 부른다. 주소의 번호를 검사하고 결과를 센다 |
| `service.py` | 실제 일을 한다. 필요한 것을 DB 에서 읽어 규칙에 묻고, 안 되면 거절하고, 되면 저장한다 |
| `repository.py` | 쿼리만 한다. 저장(commit)은 서비스가 한다 |
| `policy.py` | DB 도 FastAPI 도 모르는 순수한 함수와 값. 누가 무엇을 할 수 있는가, 몇 개까지인가 |
| `schemas.py` | 요청으로 받는 값의 모양과 규칙, 응답의 모양(Pydantic 모델) |
| `models.py` | 테이블 하나의 모양(SQLAlchemy 의 모델) |

## 로그와 요청 식별자

여덟 서버가 같은 규격으로 로그를 남긴다. 규격의 전부는 [docs/observability.md](../docs/observability.md)에 있다. 여기는 이 서버에서 알아 둘 것만 적는다.
공용 코드 `shared/server-core` 의 `server_core/observability/` 를 쓴다(#588). 이 서버의 이름(`board-server`)은 설정(`app/core/config.py` 의 `service_name`)이 넘긴다. 공용 코드가 남긴 줄의 `logger` 는 `server_core.*` 다.

- 로그는 표준 오류(stderr)에 **한 줄에 JSON 하나**로 나간다. 모든 줄에 `timestamp`, `level`, `service`(`board-server`), `environment`, `version`, `message` 가 있다.
- 요청마다 식별자가 붙는다. 요청의 `X-Request-ID` 머리말이 영문자, 숫자, `.`, `_`, `-` 로 된 8~64자면 그대로 쓰고, 아니면 새 값으로 바꾼다.
  정한 값은 **모든 응답의 `X-Request-ID` 머리말**로 돌려준다. 오류가 났을 때 이 값으로 로그를 찾는다.
- 요청이 끝나면 한 줄(`http.request`)이 남는다. 주소는 실제 값이 아니라 틀로 적는다(`/api/v1/board/posts/{id}`). 머리말, 주소 뒤에 붙은 값, 본문은 적지 않는다.
- 4xx 는 `info`, 5xx 는 `error` 다. 처리하지 못한 예외는 호출 기록과 함께 로그에만 남고, 응답에는 정해진 말과 `X-Request-ID` 만 간다.
- 상태 확인(`/health`, `/health/ready`)이 끝난 줄은 성공이면 `debug`, 503 이면 `warning` 이라 운영의 로그를 메우지 않는다.
- 비밀번호, 토큰, 이메일 주소 같은 값은 로그에 넘기지 않는다. 실수로 넘겨도 나가기 직전에 한 번 더 가린다(이름이 `password`, `token` 같은 칸, 글 속의 토큰과 이메일의 모양, 주소에 든 계정과 비밀번호).
- 식별자는 로그를 찾는 데만 쓴다. 누구의 요청인지는 토큰만이 말한다.
- uvicorn 의 접근 로그는 끈다(`app/__main__.py`). 요청마다의 줄은 위의 미들웨어가 남긴다.

| `operation` | 언제 |
| --- | --- |
| `http.request` | 요청이 끝났다 |
| `board.withdrawal` | 인증 서버가 알린 탈퇴로 그 사람의 것을 정리했다(정리한 수). 사람은 남기지 않는다 |
| `notification.send` | 발송함의 알림을 보내는 한 바퀴. 못 보낸 알림마다 `notification.unavailable`(`warning`, 서명이 거절됐으면 `error`)이나 `notification.rejected`(`error`) |
| `auth.revocations_fetch` | 끊긴 세션의 목록을 받지 못했다(`warning`, `auth.revocations_unavailable`) |

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | 환경의 이름. 로그의 `environment` 칸. 운영에서는 `production` |
| `APP_VERSION` | `dev` | 배포한 코드의 버전. 로그의 `version` 칸. 운영에서는 git SHA 나 이미지 태그 |
| `LOG_LEVEL` | `info` | 이 수준부터 남긴다. `debug`, `info`, `warning`, `error` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음(보내지 않음) | span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. `http://alloy:4318` 처럼 경로 없이 적는다([추적](#추적), [메트릭](#메트릭)) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | 메트릭을 보내는 간격(밀리초, 1000 이상). 다른 서버와 같은 이름이다 |

다섯 값 모두 비밀이 아니다. 모양이 틀리면 서버가 뜨지 않는다.

**이 서버에서 다른 것.**

- 인증 서버에서 공개키와 끊긴 세션의 목록을 받을 때, 알림 서버에 알림을 보낼 때 `traceparent` 머리말로 추적을 이어 준다. 두 서버의 로그가 같은 `trace_id` 로 묶인다.
- 발송함의 알림을 보내는 한 바퀴는 작업이다. 그 바퀴의 줄에는 `request_id` 대신 `job_id` 가 붙는다. 바퀴마다 새 값이다.
- 칸을 더 실으려면 `extra` 로 넘긴다: `logger.info('…', extra={'operation': 'board.withdrawal', 'blanked_posts': 3})`.

## 추적

요청, 다른 서버를 부르는 것, 쿼리, 알림을 보내는 작업을 span 으로 남겨 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 민다. 수집기가 Tempo 에 넘긴다.
규칙과 까닭은 [관측 규격](../docs/observability.md)의 "3. 추적"에 있다. 알림 서버가 Python 의 본보기이고, 이 서버도 같은 공용 코드를 쓴다.
"붙인 것 (게시판 서버의 추적)"은 Node 로 붙였던 때의 기록이다.
주소가 비어 있으면 span 이 생기지 않고 로그는 지금과 같다.

| span | 이름 | 코드 |
| --- | --- | --- |
| 요청 | `GET /api/v1/board/posts/{id}`(메서드와 경로의 틀). 상태 확인은 걸지 않는다 | `server_core/observability/request_spans.py` |
| 다른 서버를 부르는 것 | `HTTP GET`(공개키), `HTTP POST`(알림 서버) | `server_core/observability/http_spans.py` |
| 쿼리 | `db SELECT posts`(종류와 테이블). 손으로 쓴 것은 `db SELECT` | `server_core/observability/db_spans.py` |
| 알림을 보내는 작업 | `notification.send`. 한 바퀴가 새 추적 하나다 | `server_core/notifications/dispatcher.py`(`server_core/observability/spans.py` 의 `job_span`) |

- 로그의 `trace_id` 가 span 의 trace id 와 같다. 요청의 span 에는 `request_id`, 작업의 span 에는 `job_id` 를 싣는다
- 싣지 않는 것: 주소의 경로와 뒤의 값, 머리말, 본문, SQL 의 문장과 값, 예외의 글. 쿼리가 실패하면 SQLSTATE 만 적는다
- 요청이나 작업 밖의 쿼리와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 span 을 걸지 않는다
- 보낼 알림도 지울 알림도 없던 바퀴는 그 추적을 통째로 보내지 않는다
- 받은 `traceparent` 가 "기록하지 않음"(flags `00`)이어도 남긴다
- span 은 따로 도는 스레드가 묶어서 보낸다. 서버가 꺼질 때 남은 것을 보낸다(`app/main.py` 의 `lifespan`). 수집기가 죽어 있어도 요청은 영향을 받지 않는다

## 메트릭

요청, DB, 쓰기와 신고, 검색, 알림을 보내는 작업을 세어 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 15초마다 민다. 수집기가 Prometheus 에 넘긴다.
이름과 label 은 [관측 규격](../docs/observability.md)의 "메트릭"에 있다. "붙인 것 (게시판 서버의 메트릭)"은 Node 로 붙였던 때의 기록이고, 이름과 label 은 그대로다.
주소가 비어 있으면 세기만 하고 보내지 않는다. 테스트는 `server_core/testing/metrics.py` 로 메모리에 모은다(`metrics` fixture).

| 메트릭 | label | 세는 곳 |
| --- | --- | --- |
| `http_server_requests_total`, `http_server_request_duration_seconds`, `http_server_active_requests` | `method`, `route`(경로의 틀), `status_code` | `server_core/observability/request_metrics.py`. 미들웨어의 맨 바깥이다 |
| `db_up` | 없음 | `app/api/readiness.py`. 준비 상태 확인이 본 DB |
| `db_pool_connections`, `db_pool_connections_max`, `db_pool_wait_seconds` | `state`(`idle`, `in_use`) | `server_core/observability/pool_metrics.py`. 풀은 5 + 넘칠 때 5 다 |
| `background_jobs_started_total`, `background_jobs_finished_total`, `background_jobs_running`, `background_job_duration_seconds` | `operation`(`notification.send`), `result` | `server_core/notifications/dispatcher.py` 의 한 바퀴(`measured_job`). 할 일이 없던 바퀴도 센다 |
| `board_writes_total` | `resource`(`post`, `comment`), `action`(`create`, `update`, `delete`), `result`(`success`, `rejected`, `rate_limited`) | `app/core/metrics.py` 의 `counted`. 라우터의 함수가 일을 감싼다 |
| `board_reports_total` | `target`(`post`, `comment`), `result` | 같은 `counted` |
| `board_searches_total`, `board_search_duration_seconds` | `result`(`success`, `timeout`) | `app/posts/search.py` |

- 결과는 라우터의 함수 안에서 끝난 모양이다. 답을 돌려줬으면 `success`, 429 면 `rate_limited`, 그 밖의 4xx(권한, 없는 것, 이미 신고함)면 `rejected` 다. 5xx 는 세지 않는다(요청 수의 5xx 로 본다)
- 함수가 불리기 전에 막힌 요청은 세지 않는다. 로그인하지 않은 쓰기(401), 모양이 틀린 본문(400), 모양이 틀린 주소의 번호(404)다. 요청 수의 그 상태 코드로 본다
- 검색의 그 밖의 실패(DB 가 없다)는 세지 않는다. 요청 수의 5xx 로 본다
- 계측기는 공용 코드가 열어 둔 자리(`InstrumentSet`)에 더한다(`app/core/metrics.py`). 알림 서버의 것과 같은 방식이다
- 대시보드는 Grafana 의 `board-server`(`docker/grafana/dashboards/board-server.json`), 경보는 `docker/prometheus/rules/ai-trpg.yml` 의 `board-server` 묶음이다
- 서버가 꺼질 때 모아 둔 값을 한 번 보낸다(span 과 함께)

## CI

PR 에서는 관문(`.github/workflows/ci.yml`)이 바뀐 파일을 보고 이 워크플로(`.github/workflows/board-server.yml`)를 부른다. 고르는 규칙은 `.github/scripts/changed-servers.sh` 에 있다.
`main` 푸시에서는 `board-server/`, 공용 코드(`shared/server-core/`), DB 초기화 스크립트, 워크플로 파일이 바뀐 경우에만 스스로 돈다. README 의 배지가 그 결과다.
실제 PostgreSQL을 띄우고, 로컬과 같은 초기화 스크립트로 계정과 스키마를 만든다. 다른 서버의 계정과 스키마(`auth`, `game`, `billing`)도 만든다.

1. 의존성 설치 (`uv sync --locked`): `uv.lock`과 `pyproject.toml`이 어긋나면 실패한다
2. 린트 (`uv run ruff check .`)
3. 모양 검사 (`uv run ruff format --check .`): 고치지 않고 검사만 한다
4. 의존성 취약점 검사 (`uv export` 로 잠긴 운영 의존성을 해시와 함께 뽑아 `pip-audit`): dev 와 저장소 안의 공용 코드는 뺀다. 공용 코드는 `shared.yml` 이 본다
5. 마이그레이션 끝 (`uv run alembic heads`): 끝을 찍기만 한다. 여럿이어도 실패하지 않는다
6. 마이그레이션 적용 (`uv run alembic upgrade heads`): 빈 DB 에 처음부터 모든 끝까지 적용되는지 본다
7. 마이그레이션 누락 검사 (`uv run alembic check`): 모델을 바꾸고 마이그레이션을 만들지 않았으면 실패한다
8. 마이그레이션 되돌리기 (`uv run alembic downgrade base` 뒤 다시 `upgrade heads`)
9. 테스트용 스키마에 마이그레이션 적용 (`DB_SCHEMA=board_test`)
10. 테스트 (`uv run pytest --cov --cov-report=`): 지나간 줄을 센다
11. 계약 시험의 린트와 모양 검사 (`contract/` 에서 `uv sync --locked`, ruff)
12. 계약 시험 (`contract/` 의 `uv run pytest`): 서버를 `uv run coverage run -m app` 으로 띄워 HTTP 로만 부른다. 서버가 지나간 줄은 따로 남는다
13. 지나간 줄 합치기 (`uv run coverage combine --append`): 테스트와 계약 시험의 것을 합친다
14. 커버리지 요약: 합계와 덜 지나간 파일을 작업 요약(Summary)에 적는다
15. 커버리지 기준: 합계의 줄 비율이 90% 아래면 실패한다(워크플로의 `COVERAGE_MIN`). 요약을 먼저 적으므로 실패해도 어느 파일이 덜 지나갔는지 남는다. 기준은 처음 잰 값보다 조금 낮게 잡았다. 내릴 때는 PR 에 까닭을 적는다.

API 목록이 코드와 같은지는 관문의 `api-docs` 가 본다([API 목록(OpenAPI)](#api-목록openapi)).

## 설계 메모

**설정은 pydantic-settings 로 읽고, 뜰 때 검사한다(`app/core/config.py`).** FastAPI 서버들이 함께 쓰는 칸은 공용 코드의 `CoreSettings`, 알림 서버의 칸은 `NotificationSettings` 에 있고, 이 서버는 이름과 기본값, 제 칸(`HOST`, `PORT`, `AUTH_SERVER_SECRET`)을 더한다.
값이 틀리면 앱을 만드는 데서 예외가 나고 프로세스가 끝난다. 틀린 설정으로 떠서 요청을 받다가 실패하지 않는다.
`.env`는 다른 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
오류의 글에 받은 값을 싣지 않는다(`hide_input_in_errors`). DB 주소에는 비밀번호가 들어 있다.

**환경 변수의 이름은 NestJS 때와 같다.** compose 와 계약 시험이 같은 이름으로 넘긴다. 그래서 `DATABASE_URL` 을 `postgresql://` 로 적어도 받아 asyncpg 의 주소로 바꾸고,
`HOST`, `PORT` 를 다른 FastAPI 서버처럼 uvicorn 의 인자로 받지 않고 설정에서 읽는다(`python -m app`).

**토큰은 인증 서버의 공개키로 검증만 한다.** 회원가입과 로그인은 인증 서버의 일이다. 이 서버는 인증 서버의 DB 를 보지 않고, 요청마다 인증 서버에 묻지도 않는다.
서명 방식(RS256), 서명, 만료(`exp`), 발급자(`iss`), 대상(`aud`), 토큰의 종류(`token_type`이 `access`), 세션 버전(`ver`)을 본다. 게임 서버와 같은 코드다(`server_core/auth/tokens.py`).
서명 방식은 코드에 하나만 적는다. 토큰의 머리말에 적힌 방식을 믿으면 서명이 없는 토큰(`none`)이나 공개키를 비밀키처럼 써서 만든 토큰(`HS256`)이 통과한다.

**끊긴 세션은 목록으로 안다(#274).** 인증 서버에서 세션을 끊어도(비밀번호 변경, 계정 정지) 토큰만 보면 그 access 토큰을 만료(15분)까지 받는다.
인증 서버가 끊긴 세션의 목록(`/api/v1/auth/session-revocations`)을 내주고, 이 서버가 뜨자마자 받고 그 뒤 30초마다 받아 기억한다(`server_core/auth/revocations.py`). 결제 서버, 게임 서버와 같은 규칙이다.
- 목록의 줄은 사용자(`sub` 의 SHA-256)와, 받아들이는 가장 낮은 세션 버전(`min_ver`)이다. 토큰의 세션 버전(`ver`, 없으면 0)이 그보다 낮으면 401 이다. 다른 틀린 토큰과 응답이 같다
- 끊은 뒤 30초쯤은 옛 토큰이 통한다. 요청마다 인증 서버에 묻지 않는 대가다. 다시 로그인해 받은 토큰은 버전이 올라 통한다
- 목록은 요청과 따로 받는다. 요청이 인증 서버를 기다리지 않는다. 인증 서버가 꺼져 있어도 이 서버는 뜬다
- 받지 못하면 마지막으로 받은 목록을 쓰고 경고(`error_code: auth.revocations_unavailable`, `reason` 에 종류)를 남긴다.
  한 번도 받지 못했으면 아무 세션도 끊긴 것으로 보지 않는다. 받지 못했다고 모든 토큰을 막으면 인증 서버가 잠깐 죽는 것으로 게시판 전체가 막힌다
- 한 줄이라도 모양이 틀리면 문서 전체를 받지 않는다. 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다. 문서는 8MB 까지만 읽는다

**토큰의 대상(`aud`)은 이 서버의 이름 하나다.** 인증 서버는 access 토큰 하나에 대상의 목록을 싣고, 서버마다 자기 이름(`ai-trpg-game`, `ai-trpg-board`, `ai-trpg-billing`)이 그 안에 있는지만 본다.
`JWT_AUDIENCE` 에는 이 서버의 이름 하나만 적는다. 인증 서버의 목록을 그대로 옮겨 적으면 어느 토큰도 받지 않는다.

**공개키를 기억하는 규칙은 공용 코드에 있다(`server_core/auth/jwks.py`).** 서명을 다루는 일은 PyJWT 에 맡긴다. 암호를 직접 짜지 않는다.
FastAPI 서버들과 결제 서버가 같은 규칙이다: 5분이 지나면 다시 가져온다. 모르는 키 ID(`kid`)가 오면 다시 가져온다. 다시 가져오기는 60초에 한 번만 시도한다. 실패하면 기억하던 키를 계속 쓴다.
다만 마지막으로 가져온 지 30분이 지나면 기억하던 키를 버린다. 새어 나간 키를 인증 서버가 빼도 이 서버가 그 키를 끝없이 믿지 않게 한다.
그래서 인증 서버가 잠깐 죽어도 이미 로그인한 사용자의 요청은 계속 처리하고, 가짜 `kid`를 쏟아부어도 인증 서버로 가는 요청은 60초에 한 번이다. 30분 넘게 죽어 있으면 로그인이 필요한 요청이 503 이다.

**키를 구할 수 없으면 401 이 아니라 503 이다.** 기억한 키가 하나도 없는데 인증 서버에도 닿지 않으면 토큰이 맞는지 틀린지 알 수 없다.
401 을 주면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다. 503 과 `Retry-After`로 잠시 뒤 다시 부르게 한다.

**로그인은 API 마다 인자로 받는다(`Member`).** 로그인이 필요한 라우터의 함수는 `actor: Member` 를 받고, 로그인 없이 읽는 함수(게시판, 글, 댓글, 검색)는 받지 않는다. FastAPI 의 다른 서버들과 같은 방식이다.
NestJS 때는 문지기를 앱 전체에 걸고 열어 둘 API 에 표시를 붙였다(기본으로 닫힘). 지금은 반대라 새 API 에 `Member` 를 빠뜨리면 열린다. 쓰기 API 는 서비스가 `Actor` 를 받으므로 빠뜨리면 타입이 맞지 않는다.
로그인 없이 읽는 API 는 토큰을 보내도 보지 않는다.

**사용자는 인증 서버의 `public_id`로만 가리킨다.** 토큰의 `sub`다. 이 서버는 사용자의 이름이나 이메일을 모른다. UUID 의 모양이 아니면 거부한다.

**서버는 인증 서버 없이도, DB 없이도 뜬다.** 공개키는 뜰 때가 아니라 첫 토큰이 올 때 가져온다. 끊긴 세션의 목록은 기다리지 않고 따로 받는다.
DB 는 엔진을 만들 뿐 뜰 때 연결하지 않는다. 그동안 `/health/ready` 가 503 이고, DB 가 돌아오면 다시 200 이다. NestJS 때는 뜰 때 DB 에 닿지 않으면 뜨지 않았다.
compose 에서는 `board-migrate` 가 먼저 DB 에 닿아야 하므로, DB 를 켜지 않은 것은 거기서 드러난다.

**글 번호는 순번이다.** 1, 2, 3… 으로 매긴다(`bigint`, DB 가 매긴다). 게시판의 글은 어차피 공개 목록에 나오므로 번호를 숨길 까닭이 없고,
주소가 짧고(`/posts/1234`), 번호의 차례가 곧 쓴 차례라 목록을 번호로 줄 세운다. 게임 서버의 테이블은 UUID 다. 비공개 테이블의 주소를 추측당하면 안 되기 때문이다.
대신 글이 몇 개인지가 번호로 드러난다. 응답에서는 번호를 글자로 내보낸다(`"1234"`). JavaScript 의 숫자는 큰 정수를 정확히 담지 못한다.

**게시판은 테이블에 두고, 내용은 마이그레이션이 넣는다.** 코드에 고정하면 게시판을 더할 때 코드와 DB 제약을 함께 고친다. 운영자가 화면에서 만들게 하면 관리 API 와 권한까지 만들어야 한다.
그 사이를 골랐다. 게시판을 더하는 일은 행을 넣는 마이그레이션 하나다. "운영자만 쓴다" 같은 규칙도 코드가 아니라 게시판의 칸(`write_policy`)이다.

**운영자는 토큰이 알려 준다(#389).** 인증 서버가 access 토큰의 `roles` 에 `"operator"` 를 싣고, 이 서버는 토큰을 검증할 때 함께 읽는다. 게임 서버와 같은 규칙이다.
예전에는 이 서버의 `operators` 테이블이 정했는데, 서비스마다 목록이 갈라지고(게시판에서는 운영자인데 게임에서는 아닌 사람) 권한을 볼 때마다 DB 에 물어야 해서 인증 서버 한 곳으로 옮겼다([운영자 권한](../docs/architecture/operators.md)).
대가는 권한을 뺏어도 이미 발급된 토큰이 만료될 때까지(15분) 통한다는 것이다. 급하면 인증 서버에서 세션을 끊는다(끊긴 세션은 30초쯤 안에 막힌다).
서비스는 사용자의 ID 하나 대신 요청한 사람(`Actor`: ID 와 운영자인지)을 받는다. 그래서 운영자인지 묻는 데 쿼리가 없다.

**권한의 규칙은 순수한 함수로 따로 둔다(`app/posts/policy.py`).** 쓰기는 게시판이 정한 대로, 고치기는 글쓴이만, 지우기는 글쓴이와 운영자다. 운영자만 쓰는 게시판(공지사항, 이벤트)의 글은 운영자만 지우고, 지금 운영자인 글쓴이만 고친다. 공지를 쓴 사람이 운영자에서 내려온 뒤에도 그 공지를 지우거나 고칠 수 있으면 안 된다. 다른 운영자도 남의 공지는 고치지 못한다. 글쓴이의 이름으로 다른 사람이 쓴 문장이 나가게 된다.
운영자도 남의 글은 고치지 못한다. 남의 이름으로 글을 바꿔 쓰는 일이 된다. 서비스는 필요한 것을 DB 에서 읽어 이 함수에 묻기만 한다.

**지운 글은 행을 남긴다.** 지운 시각(`deleted_at`)을 적고, 읽는 쿼리는 지운 글을 뺀다. 행을 없애면 댓글과 신고의 기록이 가리킬 곳을 잃는다.
지운 글은 없는 글과 똑같이 404 다. 되살리는 API 는 없다. 지운 글의 댓글은 읽을 수도 새로 달 수도 없다.

**글 목록은 쪽 번호로 나눈다.** 글 목록 아래에 1 2 3 … 을 두는 게시판 화면에 맞춘다. 전체 개수를 함께 돌려준다.
"이 글 다음 스무 개"로 넘기는 방식(커서)은 뒤쪽도 빠르고 읽는 사이 새 글이 올라와도 어긋나지 않지만, 몇 쪽으로 건너뛸 수 없다.
쪽 번호는 뒤로 갈수록 DB 가 건너뛰는 행이 많아진다. 그래서 볼 수 있는 쪽에 끝을 뒀다(10000쪽). 목록에는 본문을 싣지 않는다.

**고정한 글은 목록에 섞지 않고 따로 싣는다(`pinned`).** 한 목록 안에서 고정한 글을 앞에 세우는 방법도 있다. 응답의 모양이 안 바뀐다.
그러면 줄을 세우는 기준이 "고정했는가, 그다음 번호"가 되어 글 목록의 색인(`board_id, id`)을 못 탄다. 게시판의 글 전체를 줄 세운 뒤 한 쪽을 잘라야 한다.
따로 실으면 글 목록의 쿼리는 그대로고, 고정하거나 풀어도 다른 글의 쪽이 밀리지 않는다. 화면도 공지는 다르게 그리므로 따로 오는 편이 다루기 쉽다. 첫 쪽에서만 쿼리가 하나 는다.

**고정은 글의 열 둘에 적는다(`pinned_at`, `pinned_until`).** 고정한 시각과 끝나는 시각이다. 둘은 함께 있거나 함께 없다(DB 의 CHECK 가 지킨다).
고정한 글끼리는 나중에 고정한 것이 위에 온다. 그래서 고정한 시각이 필요하다. 표를 따로 두면 누가 고정했는지도 적을 수 있지만 지금은 쓸 곳이 없다.

**고정이 끝나는 것은 읽을 때 정해진다.** 끝나는 시각이 지난 글을 고정한 글로 읽지 않는다(`pinned_until > 지금`). 시각이 지난 행을 찾아 열을 비우는 작업을 돌리지 않는다.
작업을 두면 그것이 멈췄을 때 끝난 공지가 계속 붙어 있다. 읽을 때 정하면 멈출 것이 없다. 열에는 지난 시각이 남지만 응답에는 내보내지 않는다(`pinned: false`, `pinned_until: null`).
끝나는 시각은 고정할 때 정해 적는다. 기본 기간을 나중에 바꿔도 이미 고정한 글의 기한은 그대로다.

**고정하는 주소를 글 고치는 주소와 따로 둔다(`PUT`·`DELETE /posts/{id}/pin`).** 고치는 것은 글쓴이만, 고정하는 것은 운영자만 한다. `PATCH /posts/{id}`에 `pinned` 칸을 받으면 한 주소에 규칙 둘이 섞인다.
둘 다 여러 번 불러도 결과가 같아서 `POST`가 아니라 `PUT`과 `DELETE`다. 고정은 글을 고치는 것이 아니라서 고친 시각(`updated_at`)을 건드리지 않는다.

**한 게시판에 고정할 수 있는 글은 5개까지다.** 끝이 없으면 첫 쪽이 고정한 글로 덮인다. 고정이 끝난 글과 지운 글은 세지 않는다.
세고 나서 적는 사이에 다른 운영자가 고정하면 하나쯤 넘을 수 있다. 막으려면 게시판의 행을 잠가야 한다. 운영자 몇이 드물게 하는 일이라 잠그지 않았다.

**검색은 `ILIKE '%낱말%'` 로 한다. 색인을 타지 않는다.** 한국어라서 다른 길이 마땅치 않다.
PostgreSQL 의 전문 검색(`to_tsvector`)은 띄어쓰기로만 낱말을 나눠서 `공지를`과 `공지`를 다른 낱말로 본다. 조사를 떼려면 형태소를 나누는 확장이 있어야 하는데 기본 이미지에 없다.
`pg_trgm`(세 글자씩 잘라 만드는 색인)은 부분 일치를 빠르게 해 주지만 두 글자 검색어에는 쓰이지 못한다. 한국어 검색어는 `공지`, `버그`, `후기`처럼 두 글자가 많다. 확장을 깔려면 DB 초기화 스크립트와 CI 도 고쳐야 한다.
제대로 하려면 검색 엔진(Elasticsearch 와 한국어 분석기)을 따로 띄운다. 지금 규모에는 과하다.
그래서 부를 때마다 글을 훑는다. 재 보니 본문이 1,200자쯤인 글 3만 개에서 쿼리 하나가 0.45초쯤 걸린다. 검색은 쿼리 둘(한 쪽과 전체 개수)이라 1초 가까이다. 글이 수천 개일 때까지는 느낄 수 없고, 만 개를 넘기면 손봐야 한다.
그때는 색인을 더하거나 검색 엔진으로 옮긴다. 주소와 응답은 그대로 둘 수 있다.

**검색어의 `%`, `_`, `\` 는 글자로 찾는다(`app/posts/terms.py`).** `LIKE` 는 `%`를 "아무 글자나", `_`를 "아무 한 글자"로 읽는다. 그대로 넘기면 `50%`를 찾는 사람이 `500`도 받는다.
앞에 역빗금을 붙여 뜻을 없애고 `ESCAPE` 로 그 역빗금을 알려 준다. 낱말은 SQL 에 이어 붙이지 않고 값으로 넘긴다.

**낱말은 2자 이상이다.** 한 글자로 찾으면 거의 모든 글이 걸린다. 색인 없이 훑는 검색에서 가장 비싼 요청이 가장 쓸모없는 결과를 낸다.

**검색의 주소는 게시판 아래에 두지 않았다(`GET /posts?q=`).** 모든 게시판에서 찾는 것이 기본이고 게시판 하나로 좁히는 것은 고르는 값(`board`)이다.
`/boards/{slug}/posts?q=` 로 두면 전체에서 찾는 주소가 하나 더 있어야 한다.

**쓰기 횟수는 따로 세어 두지 않고 DB 의 글과 댓글을 센다(`app/core/write_limits.py`).** 횟수 제한은 보통 Redis 에 센다. 인증 서버도 그렇게 한다.
인증 서버가 세는 것은 실패한 로그인이다. DB 에 남는 행이 없어서 셀 곳이 따로 있어야 한다. 여기서 세는 것은 쓴 글이고, 그것은 `posts`에 이미 있다. 다른 곳에 한 번 더 세면 같은 숫자가 두 군데가 된다.
DB 의 행을 세면 서버를 다시 띄워도 여러 대로 늘려도 맞고, 새로 기댈 것(Redis, 그 설정, 죽었을 때의 처리)이 없다. 지운 것도 행이 남아서 "쓰고 지우고 또 쓰기"로 피하지 못한다.
값은 쓸 때마다 쿼리 하나다. 색인(`author_id, created_at`)만 읽고 끝난다. 운영자는 토큰으로 알므로 세지 않는다.
시각은 DB 의 것(`now()`)으로만 견준다. 쓴 시각을 DB 가 적으므로 서버의 시계와 견주면 둘의 차이만큼 어긋난다.

**한도는 대략 지킨다.** 세고 나서 쓰는 사이에 같은 사람의 다른 요청이 끼면 한두 개 넘을 수 있다. 정확히 막으려면 사용자마다 잠가야 한다. 도배를 막는 데에는 "대략 5개"로 충분하다.
숫자는 코드에 둔다(`app/core/write_limits.py`). 환경 변수로 빼지 않았다. 바꿀 일이 드물고, 잘못 넣으면 제한이 꺼지거나 아무도 쓰지 못한다.

**신고도 같은 방법으로 센다(1시간에 20건).** 신고는 행이 남으므로 글과 같은 함수로 센다. 세는 칸만 다르다(글쓴이 대신 신고한 사람).
한 사람이 신고로 운영자의 목록을 덮지 못하게 하는 것이 목적이다. 이미 신고한 것은 행을 만들지 않으므로 세기 전에 409 로 거절한다.

**검색은 횟수를 세지 않고 시간만 묶는다(3초).** 검색은 로그인 없이 부르고 남는 행도 없어서 위의 방법으로 셀 수 없다. 로그인 없는 요청을 IP 로 세는 것은 프록시의 일이다(nginx 의 `search` 묶음, IP 마다 초당 2번).
글 목록 같은 다른 읽기 주소도 똑같이 열려 있어서 앱에서 검색만 세는 것은 반쪽이다. 여기서는 검색 하나가 DB 를 오래 붙잡지 못하게만 한다.
제한은 트랜잭션 안에서 `SET LOCAL statement_timeout` 으로 건다. 그냥 `SET` 으로 걸면 연결에 남아서, 풀에 돌아간 그 연결을 받은 다른 요청에도 걸린다. 찾은 뒤에는 트랜잭션을 끝내 뒤의 쿼리(댓글 수, 닉네임)에는 걸리지 않게 한다.

**글의 신고와 댓글의 신고는 한 테이블에 두고, 칸 둘(`post_id`, `comment_id`) 가운데 하나만 채운다.** 두 칸 모두 외래 키다. 없는 글이나 댓글을 가리키는 신고는 DB 가 받지 않는다.
"대상의 종류 + 번호" 한 칸으로 두는 방법도 흔하다. 대상이 늘어도 칸이 늘지 않는다. 대신 외래 키를 걸 수 없어서 정합성을 코드가 지켜야 한다.
테이블을 둘로 나누면 코드가 두 벌이 되고, 운영자의 목록을 UNION 으로 합쳐야 한다. 꼭 하나만 차는 것은 DB 의 CHECK 가 지킨다(`ck_reports_one_target`).
글과 댓글의 다른 점(어느 칸을 보는가)은 한 파일과 저장소의 조건 하나에 모았다(`app/reports/targets.py`). 서비스와 라우터는 종류를 가리지 않고 그 값을 넘긴다.

**같은 사람이 같은 것을 두 번 신고하는 것은 DB 의 유일 제약이 막는다(`reporter_id, post_id`와 `reporter_id, comment_id`).** 코드도 먼저 확인하지만, 같은 신고가 동시에 둘 오면 둘 다 그 확인을 지나칠 수 있다.
그때 늦은 쪽은 저장하다 제약에 걸리고, 그것도 409 로 돌려준다. 비어 있는 칸(NULL)은 서로 겹치지 않으므로 글의 신고와 댓글의 신고가 서로를 막지 않는다.

**운영자의 목록은 신고 한 건이 아니라 신고당한 것마다 한 줄이다.** 한 글에 일곱 명이 신고하면 운영자가 볼 것은 하나다. 건수와 사유마다의 건수를 함께 싣는다.
묶는 셈은 DB 가 한다(`GROUP BY`, 사유마다 `COUNT(*) FILTER`). 처리도 그 단위로 한다. 한 문장으로 열린 신고를 모두 닫으므로 같은 묶음은 처리한 시각이 같다.
열린 신고만 담는 색인(`ix_reports_open`)이 있다. 처리한 신고는 쌓여 가지만 목록의 쿼리는 열린 것만 읽는다.

**처리한 신고의 목록은 따로 두지 않았다.** 처리한 것은 글이나 댓글 하나의 신고(`GET /posts/{id}/reports`)에서 본다. 처리 기록을 묶어 보는 목록은 묶는 기준(처리 한 번마다)이 하나 더 생겨서, 필요해질 때 더한다.

**신고와 지우기를 묶지 않았다.** "조치함"으로 처리해도 글이 저절로 지워지지 않고, 글을 지워도 신고가 저절로 닫히지 않는다.
지우지 않고 "문제없음"으로 닫는 일이 있고, 글쓴이가 스스로 지우는 일도 있다. 둘을 묶으면 그 경우마다 예외가 생긴다. 목록이 지운 것인지(`deleted`)를 알려 주므로 운영자가 닫으면 된다.

**운영자의 API 는 운영자인지를 가장 먼저 본다(403).** 다른 API 는 "없는 것인가(404)"를 먼저 본다. 글은 누구나 읽으니 숨길 것이 없다.
신고는 다르다. 무엇이 신고됐는지, 신고가 있기는 한지는 운영자만 알 일이다. 운영자가 아닌 사람에게는 없는 글에도 403 이다.
다만 입력의 검사(400)와 주소의 번호의 모양(404)은 그보다 먼저다. 그 둘은 라우터의 함수가 불리기 전에 본다.

**신고의 설명은 로그와 응답에 싣지 않는다.** 요청의 본문은 원래 로그에 남기지 않는다. 오류의 문장에도 받은 값을 넣지 않는다.

**신고가 쌓여도 저절로 가리지 않는다.** 여럿이 짜고 멀쩡한 글을 가릴 수 있다. 사람이 본다. 사용자의 제재(쓰기 정지)와 신고한 사람에게 결과를 알리는 일도 하지 않았다. 계정은 인증 서버의 것이다.

**댓글과 답글은 한 테이블에 둔다.** 답글은 `parent_id`로 댓글을 가리킨다. 깊이는 두 단까지다. 답글에는 답글을 달 수 없다.
끝없이 깊어지게 두면 목록을 읽는 쿼리와 화면이 함께 복잡해진다. 답글에 답하고 싶으면 같은 댓글 아래에 답글을 하나 더 단다.
`parent_id`는 같은 글의 댓글이어야 한다. 이 글의 주소로 다른 글의 댓글 아래에 답글을 끼워 넣을 수 없다.

**댓글 목록은 "이것 다음 몇 개"로 이어 읽는다(`app/comments/policy.py` 의 `slice_of`).** 글 목록은 쪽 번호지만 댓글은 다르게 했다.
댓글은 몇 쪽으로 건너뛸 일이 없고 위에서부터 이어 읽는다. 읽는 사이에 새 댓글이 달려도 같은 댓글이 두 번 나오거나 빠지지 않는다. 뒤쪽을 읽어도 느려지지 않는다.
더 있는지는 하나를 더 읽어 보고 안다. 전체가 몇 개인지는 세지 않는다.

**댓글 목록은 쿼리 둘로 읽는다.** 글에 단 댓글을 한 토막 읽고, 그 댓글들의 답글을 한 번에 읽는다. 댓글마다 답글을 따로 읽으면 댓글 스무 개에 쿼리가 스물한 번 나간다.
두 쿼리와 "답글이 있는가"를 묻는 조건이 모두 색인 하나(`post_id`, `parent_id`, `id`)를 탄다.

**한 댓글의 답글에는 끝이 있다(100개).** 목록이 댓글마다 답글을 모두 실어 보내기 때문이다. 끝이 없으면 한 댓글에 답글을 쏟아부어 응답을 한없이 키울 수 있다.
수는 세어 보고 넣는다. 그사이에 다른 요청이 답글을 달면 한둘 넘을 수 있다. 응답의 크기를 막으려는 끝이라 그 정도는 넘어도 된다. 정확히 지키려면 댓글의 행을 잠그고 세야 한다.

**답글이 달린 댓글을 지우면 자리를 남긴다.** 답글은 그대로 두고, 그 댓글은 누가 무엇을 썼는지 비운 채 `deleted: true`로 내보낸다.
자리까지 없애면 답글들이 무엇에 답한 것인지 알 수 없게 된다. 답글이 없는 댓글과 지운 답글은 목록에서 그냥 빠진다.
지운 댓글에는 답글을 더 달 수 없다.

**댓글 수는 적어 두지 않고 물을 때마다 센다(`app/posts/repository.py`).** 글에 숫자를 적어 두는 방법(`posts.comment_count`)도 있다. 큰 서비스가 흔히 그렇게 한다.
그러면 목록이 쿼리 하나로 끝나고 댓글 수로 줄을 세울 수 있다. 대신 댓글을 쓰고 지울 때마다 같은 트랜잭션에서 숫자를 고쳐야 하고, 동시에 달리는 댓글 때문에 글의 행을 잠가야 하고, 어긋났을 때 다시 세는 도구가 있어야 한다.
세는 쪽은 실제 행을 세므로 틀릴 수 없다. 값은 목록 한 쪽에 쿼리 하나다. 글마다 하나씩이 아니라 그 쪽의 글 번호를 모아 한 번에 센다(`GROUP BY post_id`). 댓글의 색인(`post_id, parent_id, id`)의 앞머리를 탄다.
"댓글 많은 순"이 필요해지면 적어 두는 쪽으로 옮긴다. 응답의 칸(`comment_count`)은 그대로라 화면은 모른다.
세는 쿼리는 `comments` 테이블만 읽으므로 글의 저장소에 둔다. 글이 댓글의 서비스에 기대지 않는다. 댓글의 서비스는 글이 있는지 확인하려고 글의 서비스를 쓴다.

**댓글은 로그인한 누구나 단다.** 운영자만 글을 쓰는 게시판(공지사항)의 글에도 그렇다. 글의 글쓴이라고 남의 댓글을 지울 수는 없다. 글쓴이 자신과 운영자만 지운다.

**글쓴이의 닉네임은 access 토큰에서 받아 이 서버의 표(`authors`)에 적어 둔다(`app/authors/`).** 닉네임은 인증 서버의 것이다. 길이 셋 있었다.
인증 서버에 "ID 들 → 닉네임"을 묻는 API 는 늘 최신이지만, 목록을 읽을 때마다 인증 서버를 부르고 인증 서버가 죽으면 이름이 빠진다.
인증 서버가 이름이 바뀔 때 알려 주는 길은 바로 반영되지만, 지금은 이름을 바꾸는 기능이 없어 알릴 일이 없다.
토큰에 실린 이름을 적어 두면 서버끼리 부르지 않는다. 인증 서버가 죽어도 이름이 나온다.

**이름은 사람마다 한 줄이고, 글과 댓글의 행에는 적지 않는다.** 글은 사람의 ID 만 가리킨다. 그래서 한 줄을 고치면 그 사람이 쓴 글 모두에 새 이름이 나온다.
글마다 쓸 때의 이름을 적으면 이름을 바꾼 뒤 같은 사람이 글마다 다른 이름으로 보인다.
응답에는 `author_id`를 그대로 두고 `author_nickname`을 더했다. 이미 쓰는 칸의 모양을 바꾸지 않는다.

**이름은 글을 쓸 때가 아니라 로그인한 요청마다 받는다(`app/core/auth.py` 의 `get_member`).** 이름을 바꾸고 게시판에 들어오기만 해도 반영된다.
요청마다 DB 에 쓰지 않는다. 최근에 적은 이름을 프로세스의 메모리에 기억해 두고, 다를 때만 적는다. 기억에 없으면 한 번 적는데, DB 도 이름이 같으면 행을 고치지 않는다(`IS DISTINCT FROM`).
기억은 1만 명까지이고 넘으면 통째로 비운다. 서버를 다시 띄우거나 여러 대로 늘려도 틀리지 않는다. 한 번 더 적을 뿐이다.
토큰의 검증(공용 코드)에는 넣지 않았다. 검증은 들여보낼지만 정한다.

**토큰의 이름은 한 번 더 본다(`app/authors/service.py` 의 `read_nickname`).** 서명된 값이라 꾸며 낼 수는 없지만 화면에 그대로 나간다. 제어 문자, 보이지 않는 글자, 빈칸뿐인 이름, 50자를 넘는 이름은 적지 않는다.
인증 서버의 규칙(한글·영문·숫자·밑줄, 20자)보다 넓게 받는다. 인증 서버가 규칙을 넓혔는데 여기만 그대로면 새 이름이 조용히 버려진다.
받아들일 수 없는 이름이어도 토큰은 받는다. 이름 때문에 로그인을 막지 않는다. 이름이 없는 토큰(이 클레임이 생기기 전에 발급한 것)도 같다. 적어 둔 이름을 지우지 않는다.

**이름을 바꾸는 기능이 생기면 인증 서버가 이 서버에 알리게 한다(#146).** 이름을 바꾸면 옛 이름이 풀린다. 다른 사람이 그 이름을 가져갔는데 바꾼 사람이 이 서버에 오지 않았다면 잠시 둘이 같은 이름으로 보인다.
탈퇴는 인증 서버가 알린다([탈퇴 받기](#탈퇴-받기), #603). 탈퇴한 사람의 글은 남기고, `author_id`와 `author_nickname`을 비운 채 "탈퇴한 사용자"로 보인다(`author_withdrawn`).
닉네임은 로그에 남기지 않는다. 사람은 ID 로만 적는다.

**제목과 본문은 받은 글자 그대로 저장한다.** HTML 로 해석하지도 태그를 지우지도 않는다. 화면이 글자로 그리면 된다.
서버가 태그를 지우면 코드를 설명하는 글이 망가지고, 지우는 규칙에 구멍이 하나만 있어도 뚫린다.

**오류 응답의 모양은 `{"detail": "문장"}`으로 통일한다(`app/core/errors.py`).** 인증 서버, 게임 서버, 결제 서버와 같은 칸 이름이다. 화면이 오류를 읽는 코드를 서버마다 따로 짜지 않는다.
`detail`에는 이 서버가 적은 문장만 내보낸다. FastAPI 나 Starlette 가 만든 거절의 글(`Not Found` 같은 상태 코드의 이름)은 상태 코드에 맞는 문장으로 바꾼다. 깨진 JSON 은 파서의 글을 싣지 않고 400 의 기본 문장이다.
뜻밖의 예외는 500 으로 답하고 예외의 글은 로그에만 남긴다(`server_core/observability/responses.py`). HTTP API 의 오류 표준(RFC 9457)은 쓰지 않았다. 서버들 중 아무도 쓰지 않는다. `detail`은 그 표준의 칸 이름이기도 해서 나중에 옮기기는 쉽다.

**입력의 검사는 NestJS 때의 결과를 그대로 낸다(`app/core/checks.py`).** 화면은 `errors` 의 칸 이름과 문장을 그대로 보여 준다. 그래서 무엇을 거부하는지뿐 아니라 문장과 그 차례까지 같아야 한다.
Pydantic 의 기본 검사 대신 칸마다 규칙을 그때의 차례대로 적고, 빈칸과 글자 수, 주소의 수는 JavaScript 의 셈을 따른다. 모르는 칸이 오면 조용히 버리지 않고 맨 앞에 `property 칸 should not exist` 로 알린다.
칸 이름을 잘못 적은 클라이언트가 왜 반영이 안 되는지 알 수 있다. 글쓴이를 본문으로 보내도(`author_id`) 거부된다. 글쓴이는 토큰에서만 안다.
주소 뒤의 값은 앱이 직접 읽는다(`app/core/query_params.py`). FastAPI 는 같은 이름을 여러 번 보내면 마지막 값만 남기는데, NestJS 때는 그것을 400 으로 거부했다. 그 계약을 지킨다.

**주소의 글 번호와 게시판 이름은 모양을 먼저 본다(`app/core/ids.py`, `app/boards/service.py`).** 모양이 아니면 DB 에 묻지 않고 404 다. 숫자가 아닌 값을 번호 칸에 묻거나 주소로 들어온 NUL 글자를 그대로 물으면 DB 가 오류를 내고, 그것은 500 이 된다.

**본문의 크기에 앱이 따로 끝을 두지 않는다.** NestJS(Express)는 JSON 본문을 100KB 까지만 받았다. FastAPI 에는 그런 기본값이 없다.
가장 긴 칸(본문 20000자)은 검사가 막는다. 바깥에서 오는 요청은 앞의 프록시(nginx)가 막는다. `/api/v1/board/` 에는 `client_max_body_size` 를 따로 적지 않아 nginx 의 기본(1MB)이다.

**준비됐는지 묻는 API 는 예외를 던지지 않는다.** 준비되지 않았다는 것은 오류가 아니라 그 API 의 답이다. 상태 코드만 503 으로 바꾸고 `{"status": "unavailable"}`을 돌려준다.
예외로 던지면 오류 응답의 모양으로 바뀐다. 관리 도구가 읽는 주소라 답의 모양을 지킨다.

**`/health`는 프로세스가 살아 있는지만, `/health/ready`는 DB 에 닿는지를 본다.** 살아 있는지에 DB 까지 넣으면, DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
준비됐는지가 실패하면 관리 도구는 재시작하지 않고 요청만 잠시 보내지 않는다.
확인 전체를 3초로 묶는다(`app/api/readiness.py` 의 `READINESS_TIMEOUT_SECONDS`). 연결된 채 멈춘 DB 나, 풀이 가득 차 연결을 기다리는 동안에도 확인이 매달리지 않는다.
왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다. 로그에도 오류의 종류만 남긴다.

**표와 칸, 제약과 색인의 이름은 NestJS(TypeORM) 때와 같다.** 같은 `board` 스키마를 그대로 넘겨받기 때문이다. 모델은 이름을 규칙(`NAMING_CONVENTION`)으로 짓지 않고 그때의 이름(`pk_posts`, `fk_posts_board`)을 `conv()` 로 그대로 적는다.
발송함만 공용 코드의 모델을 쓴다. 이름이 사람이 읽을 수 있어야 DB 의 오류 글에서 무엇이 걸렸는지 안다.

**DB 계정과 스키마는 이 서버의 것만 쓴다.** `board` 계정으로 `board` 스키마만 쓴다. 다른 서버(`auth`, `game`, `billing` 등)의 스키마에는 들어갈 수 없다.
약속이 아니라 DB 권한으로 지키고, 테스트가 확인한다(`tests/test_schema_isolation.py`): 남의 스키마에 들어갈 권한(`USAGE`)이 없고, 테이블과 스키마를 만들 권한이 없고, 스키마 이름을 직접 붙여 불러도 권한 없음이 난다. 남의 스키마는 DB 에서 읽어 오므로 새 서버가 생겨도 검사에 든다.
권한을 잘못 넓히면(`GRANT USAGE ON SCHEMA game TO board`) 이 테스트가 실패한다.

**ORM 은 SQLAlchemy 2(비동기)와 asyncpg 다.** 다른 FastAPI 서버들과 같다. 엔진과 세션, 연결 풀의 메트릭은 공용 코드(`server_core/database.py`)가 만든다.
저장소(`repository.py`)는 커밋하지 않는다. 언제 커밋할지는 서비스가 안다. 글쓴이를 비우거나 고정하는 쿼리는 그 칸만 바꾸고 고친 시각을 건드리지 않는다.

**테이블은 마이그레이션으로만 바꾼다.** 서버가 뜨면서 마이그레이션을 돌리지 않는다. 서버가 여러 대면 동시에 돌린다. compose 는 `board-migrate` 를 서버보다 먼저 한 번 돌린다.

**스키마는 연결의 `search_path`로 정한다.** 코드와 마이그레이션에 스키마 이름을 적지 않는다. 연결할 때마다 설정의 스키마로 맞춘다.
그래서 같은 마이그레이션이 `board`에도 `board_test`에도 적용되고, 테스트는 설정만 바꿔 테스트용 스키마를 쓴다. 스키마 이름은 모양을 검사한다(영문 소문자로 시작하고 소문자, 숫자, 밑줄).

**서버와 마이그레이션이 같은 함수로 연결한다.** `migrations/env.py` 는 앱과 같은 설정으로 공용 코드의 `create_engine` 을 부른다. 따로 적으면 서버는 한 스키마를 보는데 마이그레이션은 다른 스키마에 테이블을 만드는 일이 생긴다.

**테스트는 같은 DB의 다른 스키마(`board_test`)에서 돈다.** 게임 서버와 같은 방식이다. 테스트용 DB를 새로 만들려면 계정에 DB를 만드는 권한을 줘야 한다.
테스트의 설정이 테스트용 스키마가 아니면 테스트가 멈춘다(`tests/conftest.py`). 설정을 잘못 건드려 개발용 데이터에서 테스트가 도는 일을 막는다.
동작을 바꾸는 값은 테스트가 고정한다. 개발자의 `.env`에 무엇이 적혀 있든 결과가 같아야 한다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다(httpx 의 `ASGITransport`).** 네트워크의 포트를 열지 않아 빠르고, 포트가 겹칠 일이 없다. DB 연결의 풀 하나를 모든 테스트가 함께 쓴다.
HTTP 의 시나리오는 계약 시험이 진짜 프로세스를 띄워 본다. 둘을 합쳐 커버리지를 잰다.

**기본으로 듣는 주소는 `127.0.0.1`이다.** 모든 주소에서 들으면 개발하는 컴퓨터에서 띄운 서버가 같은 공유기의 다른 기기에 열린다. 컨테이너에서는 `HOST=0.0.0.0`으로 바꾼다.

**앱은 한 함수가 만든다(`create_app`).** 주소의 앞부분, 미들웨어, 오류의 모양을 거기서 건다. 서버를 띄울 때와 테스트가 같은 함수를 부른다. 테스트는 설정과 DB 풀, 인증 서버로 가는 클라이언트만 바꿔 넣는다.

**응답에 서버의 이름을 싣지 않는다.** uvicorn 의 `server` 머리말을 끈다(`app/__main__.py`). 어떤 프레임워크로 만들었는지 알려 줄 이유가 없다.

**린트와 모양 검사는 ruff 하나로 한다.** 저장소 루트의 `ruff.toml` 을 다른 파이썬 서버들과 함께 쓴다. 계약 시험은 따로 된 묶음이라 그 폴더의 설정으로 본다.

**셈과 연결은 공용 코드에 둔다.** 토큰 검증, 끊긴 세션, 로그, 추적, 메트릭, 알림의 발송함을 서버마다 따로 짜면 규칙이 갈라진다(인증 서버가 죽었을 때 어디는 막히고 어디는 통한다).
이 서버에 남은 것은 게시판의 일과, NestJS 때와 같은 결과를 내기 위한 것(입력의 문장, 주소 값 읽기, 서명 머리말 읽기, 시각의 모양, 400 의 입력 오류)이다.
