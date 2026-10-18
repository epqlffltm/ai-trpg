# 알림 서버

사람에게 보내는 알림을 모아 두는 서버다(#385). 다른 서버가 알림을 넣고, 사용자는 자기 알림함을 읽는다.

다른 서버가 서명한 요청으로 알림을 넣고(서버끼리), 사용자가 access 토큰으로 자기 알림함을 읽는다.

## 실행

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `notification` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/06-notification-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트를 추가하기 전에 만든 볼륨이라면 한 번 직접 실행한다. 루트의 `.env`에 `NOTIFICATION_DB_PASSWORD`를 적고
컨테이너를 다시 만든 뒤(`docker compose up -d`), 저장소 루트에서 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/06-notification-role.sql
```

### 설치와 실행

파이썬 3.13 과 [uv](https://docs.astral.sh/uv/) 가 있어야 한다.

```powershell
cd notification-server
copy .env.example .env
uv sync
uv run alembic upgrade heads
uv run uvicorn app.main:app --port 8004 --reload
```

`.env`의 `DATABASE_URL`에 `notification` 계정의 비밀번호(루트 `.env`의 `NOTIFICATION_DB_PASSWORD`)와
포트(`POSTGRES_PORT`)를 적는다.

인증 서버 8000, 게임 서버 8001, 게시판 서버 8002, 결제 서버 8003 이므로 8004 번으로 띄운다.
`http://127.0.0.1:8004/health` 가 `{"status":"ok"}` 를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8004/health/ready` 가 `{"status":"ok"}` 를 돌려주면 DB 까지 연결된 것이다.

### compose 로 모든 서버와 함께 띄우기

개발 중에는 위처럼 PC 에서 직접 띄운다. 모든 서버를 컨테이너로 함께 띄우는 방법은 [저장소의 README](../README.md#4-모든-서버를-컨테이너로-선택)에 있다(`docker compose --profile app up -d --build`).
그때 알림 서버에 관해 다른 것만 적는다.

- 같은 `notification-server/.env` 를 쓴다. 주소(DB, 인증 서버의 공개키)만 compose 가 덮어쓴다. 끊긴 세션 목록의 주소는 공개키 주소 옆이라 따로 적지 않는다
- 테이블은 `notification-migrate` 가 서버보다 먼저 한 번 만든다. 마이그레이션에는 서명 비밀을 주지 않는다
- 보관 기간이 지난 알림 지우기는 서버 안에서 돈다. 따로 띄울 워커나 cron 이 없다
- 바깥 주소는 프록시 하나다. `http://127.0.0.1:8080/api/v1/notification/...`. 알림 서버의 포트(8004)는 열지 않는다
- 서버끼리 부르는 `/api/v1/notification/service/` 는 프록시가 바깥에서 막는다(404). 알림을 넣는 서버는 프록시를 거치지 않고 컨테이너 이름(`notification-server:8004`)으로 부른다
- `/health` 는 `/api/v1/` 밖이라 바깥에서 열리지 않는다. compose 의 healthcheck 가 컨테이너 안에서 `/health/ready` 를 부른다
- 이미지(`Dockerfile`)는 게임 서버의 것과 같은 모양이다. root 가 아닌 사용자(번호 10001)로 돌고, `.env` 와 테스트는 넣지 않는다

## 설정

환경 변수나 `notification-server/.env` 에서 읽는다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | DB 접속 주소(`postgresql+asyncpg://notification:…@127.0.0.1:5432/trpg`). 적지 않으면 서버가 뜨지 않는다 |
| `DB_SCHEMA` | `notification` | 테이블이 놓이는 스키마. 테스트는 `notification_test`로 고정한다 |
| `DEBUG` | `false` | API 문서 화면(`/api/v1/notification/docs`)을 켠다 |
| `APP_ENVIRONMENT` | `development` | 로그의 `environment` 칸. 동작은 바꾸지 않는다 |
| `APP_VERSION` | `dev` | 로그의 `version` 칸. 배포할 때 git SHA 나 이미지의 버전을 넣는다 |
| `LOG_LEVEL` | `info` | 이 수준부터 로그를 남긴다(`debug`, `info`, `warning`, `error`) |
| `NOTIFICATION_RETENTION_DAYS` | `30` | 알림을 지우기 전까지 두는 날 수. 받은 시각부터 센다 |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. 여기서 받은 키로 서명된 토큰을 믿는다 |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-notification` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다 |
| `GAME_SERVER_SECRET` | 비어 있음 | 게임 서버가 넣는 요청의 서명 비밀. 비우면 게임 서버의 알림을 받지 않는다(401). 32자 이상, 다른 비밀과 달라야 한다 |
| `BILLING_SERVER_SECRET` | 비어 있음 | 결제 서버의 것. 규칙은 위와 같다 |
| `BOARD_SERVER_SECRET` | 비어 있음 | 게시판 서버의 것. 규칙은 위와 같다 |

서명 비밀이 짧거나 서로 같으면 서버가 뜨지 않는다. 비밀은 로그와 오류에 싣지 않는다.

## 상태 확인

| 주소 | 무엇을 보나 | 답 |
| --- | --- | --- |
| `GET /health` | 프로세스가 살아 있는가. DB 는 보지 않는다 | 200 `{"status":"ok"}` |
| `GET /health/ready` | DB 에 3초 안에 닿는가 | 200 `{"status":"ok"}`, 닿지 않으면 503 `{"status":"unavailable"}` |

둘 다 HEAD 도 받는다. 503 에는 원인을 싣지 않는다(오류 문구에 DB 의 주소와 계정이 들어 있다). 원인은 로그에 오류의 종류만 남긴다.

## 알림함(사용자)

인증 서버가 발급한 access 토큰(`Authorization: Bearer …`)으로 부른다. 누구의 알림함인지는 토큰의 `sub` 로만 정한다.
주소나 쿼리로 사용자 번호를 받지 않는다. 남의 알림함을 부를 길이 없다.

| 메서드 | 주소 | 무엇을 | 답 |
| --- | --- | --- | --- |
| GET | `/api/v1/notification/me/notifications?before=&limit=` | 내 알림을 최근 것부터 | 200 `{"items": [...], "next_before": 41}` |
| GET | `/api/v1/notification/me/notifications/unread-count` | 읽지 않은 알림의 수 | 200 `{"unread": 3}` |
| POST | `/api/v1/notification/me/notifications/{id}/read` | 알림 하나를 읽음으로 | 200 알림 하나. 없거나 남의 것이면 404 |
| POST | `/api/v1/notification/me/notifications/read-all` | 본문 `{"up_to": 57}`: 그 번호까지 읽지 않은 것을 모두 읽음으로 | 200 `{"read": 4}` |

알림 하나는 이렇게 생겼다. 넣은 서버가 붙인 열쇠(`source_key`)와 받는 사람은 싣지 않는다.

```json
{"id": 57, "source": "game", "kind": "scenario.sanctioned", "payload": {"scenario_id": "…"}, "created_at": "2026-10-18T09:00:00Z", "read_at": null}
```

- **쪽은 번호로 넘긴다.** `limit`(1~100, 기본 20)개를 읽고, 다음 쪽이 있으면 `next_before` 를 준다. 그 값을 `before` 로 다시 부른다.
  `OFFSET` 이 아니라 색인(`user_id`, `id DESC`)을 따라 읽으므로 쪽을 몇 개 넘겨도 느려지지 않는다. 그 사이에 새 알림이 들어와도 쪽이 밀리지 않는다.
  한 개를 더 읽어 다음 쪽이 있는지 안다. 꼭 `limit` 개가 남았을 때 빈 쪽을 한 번 더 부르지 않는다.
- **읽음은 처음 읽은 시각이다.** 다시 읽음으로 해도 바뀌지 않는다(200).
- **모두 읽음은 화면이 받은 번호까지만이다.** "지금까지 전부"로 하면, 목록을 받은 뒤에 막 들어와 화면에 보이지도 않은 알림까지 읽음이 된다.
- **남의 알림 번호는 404 다.** 없는 알림과 같은 답이다. 남의 알림이 있는지 알리지 않는다.
- 토큰이 없거나 틀렸거나 끊긴 세션의 것이면 401, 인증 서버의 공개키를 구할 수 없으면 503(`Retry-After`)이다.

### 토큰 검증

게임 서버의 것(`app/auth/jwks.py`, `tokens.py`, `revocations.py`, `dependencies.py`)을 그대로 가져왔다. 규칙의 설명은
[게임 서버의 토큰 검증](../game-server/README.md#토큰-검증)에 있다. 다른 점은 알림 서버가 누구인지(`sub`)만 읽는다는 것이다
(성인 등급과 역할은 읽지 않는다).

- 공개키: 처음 필요할 때 가져와 5분 기억한다. 모르는 `kid` 면 다시 가져오되 60초에 한 번만. 30분 넘게 못 가져오면 버리고 503.
- 끊긴 세션: 서버가 뜨자마자, 그 뒤 30초마다 인증 서버의 목록을 받는다. `ver` 가 그 사람의 `min_ver` 보다 낮은 토큰은 401.
- 토큰의 대상(`aud`)에 `ai-trpg-notification` 이 있어야 한다. 인증 서버의 `JWT_AUDIENCE` 기본값에 이 이름이 있다.
  인증 서버의 `.env` 에 `JWT_AUDIENCE` 를 적어 둔 PC 는 그 줄에도 이 이름을 더한다.

## 알림 넣기(서버끼리)

다른 서버가 부르는 주소다. 사용자의 토큰으로는 부를 수 없다. 그 서버의 서명으로 확인한다.

```
POST /api/v1/notification/service/{source}/notifications
X-Service-Signature: t=<보낸 시각(초)>,v1=<서명>
Content-Type: application/json

{"source_key": "scenario-sanction:42", "user_id": "<받는 사람의 public_id>", "kind": "scenario.sanctioned", "payload": {"scenario_id": "…"}}
```

| 답 | 뜻 |
| --- | --- |
| 201 `{"id": 7, "status": "created"}` | 새로 넣었다 |
| 200 `{"id": 7, "status": "existing"}` | 같은 알림이 이미 있다(다시 보낸 것). 같은 `id` 다 |
| 401 | 서명이 없거나, 틀렸거나, 5분을 넘겼거나, 남의 주소의 것이거나, 그 서버의 비밀이 설정에 없다. 이유는 나누지 않는다 |
| 409 `{"detail": {"code": "key_reused", "source_key": "…"}}` | 같은 열쇠로 다른 알림(받는 사람, `kind`, `payload` 중 하나가 다르다)을 넣으려 했다 |
| 413 | 본문이 16KB 를 넘는다 |
| 422 | 본문의 모양이 틀렸다 |

- `source` 는 넣는 서버의 이름이다: `game`, `billing`, `board`. 모르는 이름도 401 이다(404 가 아니다. 어느 이름이 있는지 알리지 않는다).
- **서명은 결제 서버와 같은 모양이다.** `HMAC-SHA256(비밀, "<시각>.<메서드>\n<주소>\n<본문>")` 의 16진수. 주소는 호스트를 뺀 경로다.
  주소까지 서명하므로 한 서버의 서명을 다른 서버의 주소에 붙여 쓸 수 없다. 시각이 앞뒤 5분을 넘긴 서명은 받지 않는다.
  본문은 보내는 바이트 그대로에 서명한다. JSON 을 한 번 만들어 서명하고 그것을 보낸다.
- **본문은 서명을 확인한 뒤에 읽는다.** 서명을 확인하려면 본문 전체가 있어야 해서, 그 전에 크기(16KB)부터 자른다.
- **받는 칸:** `source_key`(1~128자, 빈칸 없는 ASCII), `user_id`(UUID), `kind`(점으로 나눈 소문자, 64자까지),
  `payload`(JSON 객체, 빈칸 없이 줄여 2048바이트까지). 모르는 칸이 오면 422 다(넣는 서버의 오타를 조용히 버리지 않는다).
  `payload` 의 상한이 DB 의 상한(4096바이트)의 절반인 까닭은 DB 가 jsonb 를 글자로 바꿀 때 쉼표와 쌍점 뒤에 빈칸을 넣기 때문이다.
- **같은 알림은 한 줄이다.** 넣는 서버는 답을 못 받으면 같은 `source_key` 로 다시 보낸다. 동시에 같은 열쇠가 여럿 와도
  DB 가 하나만 넣는다(`INSERT … ON CONFLICT DO NOTHING`). 먼저 찾아보고 없으면 넣는 방식은 동시에 온 둘이 모두 "없다"를 본다.
- **받은 시각은 이 서버의 시계다.** 넣는 서버가 적은 시각을 믿지 않는다.
- 로그에는 넣은 서버, `kind`, 알림의 `id`, 결과(`created`, `existing`)만 남긴다(`operation`: `notification.put`). 받는 사람과 `payload` 는 남기지 않는다.

## 보관 기간

받은 지 30일(`NOTIFICATION_RETENTION_DAYS`)이 지난 알림은 지운다. 읽었는지는 보지 않는다. 일 자체의 기록(시나리오, 결제)은 그 일을 맡은 서버에 남는다.

- 서버 안의 정리 작업(`app/notifications/retention.py`)이 뜨자마자, 그 뒤 한 시간마다 한 바퀴 돈다.
- 한 바퀴에 1,000줄씩 많아야 20묶음을 지운다. 묶음마다 저장한다. 밀린 것은 다음 바퀴에 마저 지운다.
  한 번에 몇십만 줄을 지우면 그동안 줄들을 잠그고 트랜잭션이 길어진다.
- 서버가 여럿이어도 된다. 다른 서버가 잠근 줄은 건너뛴다(`SKIP LOCKED`).
- 한 바퀴가 통째로 실패하면(DB 가 없다) `error` 한 줄(`job.failed`)을 남기고 다음 바퀴를 기다린다.

## 로그

[관측 규격](../docs/observability.md)을 따른다. 게임 서버의 `app/observability/` 를 그대로 가져왔다.

- 로그는 한 줄에 하나의 JSON 이다(`service`: `notification-server`). 표준 오류로 나간다.
- 요청마다 `X-Request-ID` 를 걸고 응답에 돌려준다. 요청이 끝나면 한 줄(`http.request`)을 남긴다. 주소는 틀(`/api/v1/notification/me/notifications/{notification_id}/read`)로 적고 실제 번호와 쿼리는 적지 않는다.
- 인증 서버를 부를 때 `traceparent` 로 추적을 이어 준다.
- 처리하지 못한 예외는 내부를 드러내지 않는 500 이다. 원인은 로그에 남는다. DB 주소, 토큰 같은 것은 로그에서도 가린다.

| `operation` | 언제 |
| --- | --- |
| `http.request` | 요청이 끝났다 |
| `notification.put` | 다른 서버가 알림을 넣었다(`source`, `kind`, `notification_id`, `outcome`) |
| `notification.prune` | 보관 기간이 지난 알림을 지웠다(`deleted`, `retention_days`). 지운 것이 없으면 `debug` |
| `auth.revocations_fetch` | 끊긴 세션의 목록을 받지 못했다(`warning`, `auth.revocations_unavailable`) |

## DB

DB 인스턴스는 다른 서버와 같고, 계정과 스키마는 따로다. 알림 서버는 `notification` 계정으로 `notification`
스키마(테스트는 `notification_test`)만 쓴다. 다른 서버의 스키마에 닿지 못하는 것을 테스트(`tests/test_schema_isolation.py`)가 확인한다.

### 테이블

| 테이블 | 한 줄은 | 마이그레이션 |
| --- | --- | --- |
| `notifications` | 사람 하나에게 간 알림 하나(#385) | `20261018_3f9a1c7e5b2d_notifications.py` |

`notifications` 의 칸과 규칙(`app/notifications/models.py`):

| 칸 | 뜻 |
| --- | --- |
| `id` | 차례대로 오르는 번호. 목록의 커서로 쓴다 |
| `user_id` | 받는 사람. 인증 서버의 `public_id`(토큰의 `sub`)다. 이 서버는 회원 정보를 갖지 않는다 |
| `source` | 넣은 서버(`game`, `billing`, `board` 등). 소문자로 시작하고 소문자, 숫자, `_`, `-` 만 쓴다 |
| `source_key` | 넣은 서버가 알림마다 붙인 열쇠(128자까지). `(source, source_key)` 가 같으면 한 줄이다 |
| `kind` | 무슨 일인가(`scenario.sanctioned` 처럼 점으로 나눈 소문자). 화면이 이것을 보고 글을 고른다 |
| `payload` | 그 일의 값(JSON 객체, 4096바이트까지). 글은 싣지 않는다 |
| `created_at` | 이 서버가 받은 시각 |
| `read_at` | 읽은 시각. 읽지 않았으면 비어 있다. `created_at` 보다 앞일 수 없다 |

- **글을 저장하지 않는다.** 무슨 일인지(`kind`)와 값(`payload`)만 적고 글은 화면이 만든다. 문구를 고칠 때 저장된 알림을
  고치지 않아도 되고, 넣는 서버가 사람에게 보일 문장을 만들지 않는다. 게임 서버의 이벤트(`type` + `payload`)와 같은 방식이다.
- **같은 알림은 한 줄이다.** 넣는 서버는 받았다는 답을 못 받으면 같은 열쇠로 다시 보낸다. DB 의 유일 제약이 두 번 적히는 것을 막는다.
- **색인은 셋이다.** 내 알림함(`user_id`, `id DESC`), 읽지 않은 수(읽지 않은 줄만 담는 부분 색인), 보관 기간이 지난 것 찾기(`created_at`).

### 마이그레이션

```powershell
cd notification-server
uv run alembic upgrade heads                          # 개발용 스키마에 적용
$env:DB_SCHEMA = 'notification_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA   # 테스트용 스키마에 적용
uv run alembic check                                  # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
uv run alembic revision --autogenerate -m "설명"       # 모델과 DB 를 비교해 새 마이그레이션 만들기
```

DB 주소와 스키마는 앱과 같은 설정(`.env`)에서 읽는다. `alembic.ini` 에는 적지 않는다.
어디까지 적용했는지 적는 표(`alembic_version`)도 스키마마다 따로 있다.

## 테스트

테스트는 실제 PostgreSQL 의 `notification_test` 스키마에서 돈다. `.env`의 `DATABASE_URL`을 그대로 쓴다.
테스트용 스키마에 마이그레이션을 먼저 적용한다(위의 "마이그레이션"). 테스트는 시작할 때마다 테이블을 비운다.

```powershell
cd notification-server
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
