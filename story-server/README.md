# story 서버

하나의 세계관 안에서 여러 인물을 만나고, 장소를 옮기고, 이벤트를 겪고, 한 사람에게 고백해 엔딩을 보는 이야기를 맡는 서버다(#591).
규칙은 [story 서버 설계](../docs/architecture/story.md)에 있다. 캐릭터 하나와의 1:1 대화는 chat 서버가 맡는다.
둘이 함께 쓰는 것과 나눈 선은 [chat 서버 설계의 story-server 와 나눈 선](../docs/architecture/chat-server.md#story-server-와-나눈-선)에 있다.

**지금은 뼈대다(#591).** 공용 코드 `shared/server-core` 위에 설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증, Alembic, 테스트만 있다.
세계관과 세션, 장면의 인물, 시각, 조건과 효과, 고백과 엔딩이 차례로 붙는다([만드는 순서](../docs/architecture/story.md#만드는-순서)).

정해 둔 값: 포트 `8007`, 토큰의 대상 `ai-trpg-story`, DB 계정과 스키마 `story`(테스트는 `story_test`), 주소 `/api/v1/story/`.

**대화의 핵심은 chat 과 함께 쓴다.** 대화 트리, 다시 생성과 분기, 요약, 기억, 스트리밍한 답을 저장하는 흐름은
chat 서버에서 옮긴 공용 코드 `shared/conversation-core` 를 두 서버가 함께 쓴다(이 서버는 세션을 만들 때부터). 표는 서버마다 따로 둔다(이 서버는 `story` 스키마).

## 실행

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `story` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/10-story-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트가 생기기 전에 만든 볼륨이라면 한 번 직접 실행한다. 저장소 루트에서 `uv run --no-project python tools/fill_env.py` 로
루트 `.env`의 `STORY_DB_PASSWORD`와 `story-server/.env`를 채우고, 컨테이너를 다시 만든 뒤(`docker compose up -d`) 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/10-story-role.sql
```

뼈대 때 계정을 손으로 만들었다면(`CREATE ROLE story ...`) 위의 스크립트는 돌리지 않는다("이미 있다"로 멈춘다).
`tools/fill_env.py` 가 `story-server/.env` 에 적어 둔 비밀번호를 루트 `.env` 의 `STORY_DB_PASSWORD` 로 옮겨 적으므로 계정과 그대로 맞는다.

### 설치와 실행

파이썬 3.13 과 [uv](https://docs.astral.sh/uv/) 가 있어야 한다.

```powershell
cd story-server
copy .env.example .env
uv sync
uv run alembic upgrade heads
uv run uvicorn app.main:app --port 8007 --reload
```

`.env`의 `DATABASE_URL`에 `story` 계정의 비밀번호(루트 `.env`의 `STORY_DB_PASSWORD`)와 포트(`POSTGRES_PORT`)를 적는다.

인증 서버 8000, 게임 서버 8001, 게시판 서버 8002, 결제 서버 8003, 알림 서버 8004, chat 서버 8005, asset 서버 8006, story 서버 8007 이다.
`http://127.0.0.1:8007/health` 가 `{"status":"ok"}` 를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8007/health/ready` 가 `{"status":"ok"}` 를 돌려주면 DB 까지 연결된 것이다.

compose(`docker compose --profile app`)로 띄우면 같은 `story-server/.env` 를 쓰고 주소(DB, 인증 서버의 공개키)만 compose 가 덮어쓴다.
바깥 주소는 프록시 하나(`http://127.0.0.1:8080/api/v1/story/...`)가 되고 story 서버의 포트는 열지 않는다.
이미지(`Dockerfile`)는 chat, asset 서버의 것과 같은 모양이다(공용 코드를 `/shared` 에서 깐다). root 가 아닌 사용자(번호 10001)로 돌고, `.env` 와 테스트는 넣지 않는다.

## 설정

환경 변수나 `story-server/.env` 에서 읽는다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | DB 접속 주소(`postgresql+asyncpg://story:…@127.0.0.1:5432/trpg`). 적지 않으면 서버가 뜨지 않는다 |
| `DB_SCHEMA` | `story` | 테이블이 놓이는 스키마. 테스트는 `story_test`로 고정한다 |
| `DEBUG` | `false` | API 문서 화면(`/api/v1/story/docs`)을 켠다 |
| `APP_ENVIRONMENT` | `development` | 로그의 `environment` 칸. 동작은 바꾸지 않는다 |
| `APP_VERSION` | `dev` | 로그의 `version` 칸. 배포할 때 git SHA 나 이미지의 버전을 넣는다 |
| `LOG_LEVEL` | `info` | 이 수준부터 로그를 남긴다(`debug`, `info`, `warning`, `error`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음(보내지 않음) | span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. `http://alloy:4318` 처럼 경로 없이 적는다([추적](#추적), [메트릭](#메트릭)) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | 메트릭을 보내는 간격(밀리초, 1000 이상) |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. 여기서 받은 키로 서명된 토큰을 믿는다 |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-story` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다 |

DB 의 연결 풀(`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`)처럼 FastAPI 서버들이 함께 쓰는 칸은 공용 코드의 설정(`server_core.settings.CoreSettings`)에 있다.
결제 서버를 부를 때의 비밀(결제 쪽은 `STORY_SERVER_SECRET`, 가격 이름의 머리 `story`)과 asset 서버에서 세계관의 판을 가져올 때의 비밀은 그 길을 만들 때 더한다.
환경 변수는 다른 서버와 같은 이름을 쓰고 머리(`STORY_`)를 붙이지 않는다. 머리는 다른 서버의 설정에 들어가는 값(`STORY_SERVER_SECRET`)에만 붙인다.

## 상태 확인

| 주소 | 무엇을 보나 | 답 |
| --- | --- | --- |
| `GET /health` | 프로세스가 살아 있는가. DB 는 보지 않는다 | 200 `{"status":"ok"}` |
| `GET /health/ready` | DB 에 3초 안에 닿는가 | 200 `{"status":"ok"}`, 닿지 않으면 503 `{"status":"unavailable"}` |

둘 다 HEAD 도 받는다. 503 에는 원인을 싣지 않는다(오류 문구에 DB 의 주소와 계정이 들어 있다). 원인은 로그에 오류의 종류만 남긴다.
`/health` 는 `/api/v1/` 밖이라 프록시가 바깥에 열지 않는다.

## API

| 방법 | 주소 | 하는 일 | 인증 |
| --- | --- | --- | --- |
| GET | `/api/v1/story/me` | 토큰의 주인(`{"user_id"}`, 인증 서버의 `public_id`). 토큰 검증이 이어졌는지 보는 가장 작은 주소다(게임 서버의 `GET /me` 와 같다) | access 토큰 |

**스트리밍(정한 것).** 말을 보내는 주소는 chat 과 같이 바로 SSE(`text/event-stream`)로 답한다. 응답에 `X-Accel-Buffering: no` 를 싣고
15초마다 하트비트를 보낸다. 끊겨도 서버는 생성을 끝까지 저장하고, 앱은 다시 들어와 저장된 말을 읽는다.
여러 인물의 말은 한 번의 호출에서 말 조각으로 받는다([한 번의 말](../docs/architecture/story.md#한-번의-말)). 그 주소를 만들 때 공용 코드의 `StreamRoutes` 로 span 과 요청 메트릭에서 뺀다.

### 토큰 검증

공용 코드 `shared/server-core` 의 것(`server_core/auth/`)을 쓴다(#588). 알림 서버와 같다. 규칙의 설명은
[게임 서버의 토큰 검증](../trpg-server/README.md#토큰-검증)에 있다. 토큰의 주인(`CurrentUser`)에는 성인 등급(`adult_content`)과
운영자(`is_operator`)도 실린다. 성인 등급의 세계관을 거를 때 쓴다(`allowed_ratings`, 세션을 만들 때 한 번).

- 공개키: 처음 필요할 때 가져와 5분 기억한다. 모르는 `kid` 면 다시 가져오되 60초에 한 번만. 30분 넘게 못 가져오면 버리고 503.
- 끊긴 세션: 서버가 뜨자마자, 그 뒤 30초마다 인증 서버의 목록을 받는다. `ver` 가 그 사람의 `min_ver` 보다 낮은 토큰은 401.
- 토큰의 대상(`aud`)에 `ai-trpg-story` 가 있어야 한다. 인증 서버의 `JWT_AUDIENCE` 기본값에 이미 있다(#597).
  인증 서버의 `.env` 에 `JWT_AUDIENCE` 를 적어 둔 PC 는 그 줄에도 이 이름을 더한다.

## 로그

[관측 규격](../docs/observability.md)을 따른다. 공용 코드 `shared/server-core` 의 `server_core/observability/` 를 쓴다(#588).
이 서버의 이름(`story-server`)은 설정(`app/core/config.py` 의 `service_name`)이 넘긴다. 공용 코드가 남긴 줄의 `logger` 는 `server_core.*` 다.

- 로그는 한 줄에 하나의 JSON 이다(`service`: `story-server`). 표준 오류로 나간다.
- 요청마다 `X-Request-ID` 를 걸고 응답에 돌려준다. 요청이 끝나면 한 줄(`http.request`)을 남긴다. 주소는 경로의 틀로 적고 실제 값과 쿼리는 적지 않는다.
- 인증 서버를 부를 때 `traceparent` 로 추적을 이어 준다. span 을 내보내면 그 호출의 span 이 부모가 된다.
- 처리하지 못한 예외는 내부를 드러내지 않는 500 이다. 원인은 로그에 남는다. DB 주소, 토큰 같은 것은 로그에서도 가린다.

| `operation` | 언제 |
| --- | --- |
| `http.request` | 요청이 끝났다 |
| `auth.revocations_fetch` | 끊긴 세션의 목록을 받지 못했다(`warning`, `auth.revocations_unavailable`) |

## 추적

요청, 인증 서버를 부르는 것, 쿼리를 span 으로 남겨 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 민다. 수집기가 Tempo 에 넘긴다.
규칙과 까닭은 [관측 규격](../docs/observability.md)의 "3. 추적"에 있다. 주소가 비어 있으면 span 이 생기지 않고 로그는 지금과 같다.

| span | 이름 | 코드 |
| --- | --- | --- |
| 요청 | `GET /api/v1/story/me`(메서드와 경로의 틀). 상태 확인은 걸지 않는다 | `server_core/observability/request_spans.py` |
| 인증 서버를 부르는 것 | `HTTP GET` | `server_core/observability/http_spans.py` |
| 쿼리 | `db SELECT worlds`(종류와 테이블). 손으로 쓴 것은 `db SELECT` | `server_core/observability/db_spans.py` |
| 뒤의 작업 | 작업의 이름. 한 바퀴가 새 추적 하나다 | `server_core/observability/spans.py` 의 `job_span` |

- 로그의 `trace_id` 가 span 의 trace id 와 같다. 요청의 span 에는 `request_id`, 작업의 span 에는 `job_id` 를 싣는다
- 싣지 않는 것: 주소의 경로와 뒤의 값, 머리말, 본문, SQL 의 문장과 값, 예외의 글. 쿼리가 실패하면 SQLSTATE 만 적는다
- 요청이나 작업 밖의 쿼리와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 span 을 걸지 않는다
- 뒤의 작업을 감싸는 틀(`job_span`, `job_scope`, `measured_job`)은 아직 쓰는 곳이 없다. 요약과 임베딩을 서버 안의 바퀴(loops)로 돌릴 때 쓴다(chat 과 같다). 테스트는 `tests/jobs.py` 의 바퀴로 본다
- span 은 따로 도는 스레드가 묶어서 보낸다. 서버가 꺼질 때 남은 것을 보낸다(5초 안). 수집기가 죽어 있어도 요청은 영향을 받지 않는다

## 메트릭

요청, DB, 뒤의 작업을 세어 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 15초마다 민다. 수집기가 Prometheus 에 넘긴다.
이름과 label 은 [관측 규격](../docs/observability.md)의 "메트릭"에 있다. 주소가 비어 있으면 세기만 하고 보내지 않는다.

| 메트릭 | label | 세는 곳 |
| --- | --- | --- |
| `http_server_requests_total`, `http_server_request_duration_seconds`, `http_server_active_requests` | `method`, `route`(경로의 틀), `status_code` | `server_core/observability/request_metrics.py`. 미들웨어의 맨 바깥이다 |
| `db_up` | 없음 | `app/api/readiness.py`. 준비 상태 확인이 본 DB |
| `db_pool_connections`, `db_pool_connections_max`, `db_pool_wait_seconds` | `state`(`idle`, `in_use`) | `server_core/observability/pool_metrics.py`. 풀은 `DB_POOL_SIZE` + 넘칠 때 `DB_MAX_OVERFLOW` 다(기본 5 + 10) |
| `background_jobs_started_total`, `background_jobs_finished_total`, `background_jobs_running`, `background_job_duration_seconds` | `operation`, `result` | `server_core/observability/metrics.py` 의 `measured_job`. 아직 쓰는 작업이 없다 |

- 계측기는 공용 코드(`server_core/observability/metrics.py`)에 한 묶음으로 있다. 이 서버만의 계측기가 생기면 `InstrumentSet` 으로 더한다(알림 서버의 `app/notifications/metrics.py`).
  테스트는 `server_core/testing/metrics.py` 로 메모리에 모아 이름, 단위, label 을 본다(`metrics` fixture)
- 보내는 길은 공용 코드의 테스트가 가짜 수집기로 본다. 이 서버가 꺼질 때 이 서버의 이름으로 보내는지는 `tests/test_tracing_setup.py` 가 본다
- 대시보드는 `docker/grafana/dashboards/story-server.json`(한눈에, 요청, DB 연결), 경보는 `docker/prometheus/rules/ai-trpg.yml` 의 `story-server` 묶음(`StoryDatabaseUnreachable`, `StoryServerErrors`)이다.
  요청 수와 DB, 연결 풀, 요청과 쿼리의 span 이 Prometheus 와 Tempo 에 들어오는지는 관문 CI 의 `stack` 이 본다

## DB

DB 인스턴스는 다른 서버와 같고, 계정과 스키마는 따로다. story 서버는 `story` 계정으로 `story`
스키마(테스트는 `story_test`)만 쓴다. 다른 서버의 스키마에 닿지 못하는 것을 테스트(`tests/test_schema_isolation.py`)가 확인한다.

아직 테이블이 없다. 세계관과 세션의 테이블이 생기면 `migrations/env.py` 와 `tests/cleaning.py` 에서 그 모듈을 불러온다.

### 마이그레이션

```powershell
cd story-server
uv run alembic upgrade heads                          # 개발용 스키마에 적용
$env:DB_SCHEMA = 'story_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA   # 테스트용 스키마에 적용
uv run alembic check                                  # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
uv run alembic revision --autogenerate -m "설명"       # 모델과 DB 를 비교해 새 마이그레이션 만들기
```

DB 주소와 스키마는 앱과 같은 설정(`.env`)에서 읽는다. `alembic.ini` 에는 적지 않는다.
어디까지 적용했는지 적는 표(`alembic_version`)도 스키마마다 따로 있다.

## 테스트

테스트는 실제 PostgreSQL 의 `story_test` 스키마에서 돈다. `.env`의 `DATABASE_URL`을 그대로 쓴다.
테스트용 스키마에 마이그레이션을 먼저 적용한다(위의 "마이그레이션"). 테스트는 시작할 때마다 테이블을 비운다.

```powershell
cd story-server
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

CI 는 `.github/workflows/story-server.yml` 이다. 린트, 모양, 의존성 취약점, 마이그레이션(적용, 누락, 되돌리기), 테스트와 커버리지(95% 이상)를 본다.
PR 에서는 관문(`ci.yml`)이 바뀐 파일을 보고(`changed-servers.sh`) 이 워크플로를 부른다.
