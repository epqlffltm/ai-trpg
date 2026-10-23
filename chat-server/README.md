# chat 서버

캐릭터 하나와의 1:1 대화를 맡는 서버다(#590). 설계는 [docs/architecture/chat-server.md](../docs/architecture/chat-server.md)에 있다.
여러 인물이 나오는 story 는 story-server 가 맡는다(#591).

공용 코드 `shared/server-core` 위에 설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증이 있고(#590),
[대화](#대화)를 시작하고 읽는 길이 있다(만드는 순서 1). 한 번의 말(만드는 순서 2)의 첫 조각으로 [모델 목록](#모델-목록)과 대화의 모델이 있다.
결제 서버의 가격과 홀드, 스트리밍이 다음으로 붙는다([만드는 순서](../docs/architecture/chat-server.md#만드는-순서)).

정해 둔 값: 포트 `8005`, 토큰의 대상 `ai-trpg-chat`, DB 계정과 스키마 `chat`(테스트는 `chat_test`), 주소 `/api/v1/chat/`.

**대화의 핵심은 `app/conversation/` 에 모은다.** story-server 를 만들 때 파일째 `shared/conversation-core` 로 옮긴다.
그래서 이 폴더는 앱의 다른 코드(`app.*`)를 가져오지 않는다(`tests/test_conversation_boundary.py`). chat 만의 것(캐릭터 하나, 호감도, 그림)은 이 폴더 밖에 둔다.

## 실행

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `chat` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/09-chat-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트가 생기기 전에 만든 볼륨이라면 한 번 직접 실행한다. 루트의 `.env`에 `CHAT_DB_PASSWORD`를 적고
컨테이너를 다시 만든 뒤(`docker compose up -d`), 저장소 루트에서 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/09-chat-role.sql
```

초기화 스크립트, compose(`chat-migrate`, `chat-server`), 프록시의 `/api/v1/chat/`(스트리밍 경로의 버퍼링 끄기), 관문 CI, `.env` 도구는 인프라 쪽이 이 PR 에 얹는다.

### 설치와 실행

파이썬 3.13 과 [uv](https://docs.astral.sh/uv/) 가 있어야 한다.

```powershell
cd chat-server
copy .env.example .env
uv sync
uv run alembic upgrade heads
uv run uvicorn app.main:app --port 8005 --reload
```

`.env`의 `DATABASE_URL`에 `chat` 계정의 비밀번호(루트 `.env`의 `CHAT_DB_PASSWORD`)와 포트(`POSTGRES_PORT`)를 적는다.

인증 서버 8000, 게임 서버 8001, 게시판 서버 8002, 결제 서버 8003, 알림 서버 8004, chat 서버 8005, asset 서버 8006, story 서버 8007 이다.
`http://127.0.0.1:8005/health` 가 `{"status":"ok"}` 를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8005/health/ready` 가 `{"status":"ok"}` 를 돌려주면 DB 까지 연결된 것이다.

compose 로 함께 띄울 때도 같은 `chat-server/.env` 를 쓴다. 주소(DB, 인증 서버의 공개키)만 compose 가 덮어쓴다.
바깥 주소는 프록시 하나(`http://127.0.0.1:8080/api/v1/chat/...`)이고 chat 서버의 포트는 열지 않는다.
이미지(`Dockerfile`)는 asset, 알림 서버의 것과 같은 모양이다(공용 코드를 `/shared` 에서 깐다). root 가 아닌 사용자(번호 10001)로 돌고, `.env` 와 테스트는 넣지 않는다.

## 설정

환경 변수나 `chat-server/.env` 에서 읽는다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | DB 접속 주소(`postgresql+asyncpg://chat:…@127.0.0.1:5432/trpg`). 적지 않으면 서버가 뜨지 않는다 |
| `DB_SCHEMA` | `chat` | 테이블이 놓이는 스키마. 테스트는 `chat_test`로 고정한다 |
| `DEBUG` | `false` | API 문서 화면(`/api/v1/chat/docs`)을 켠다 |
| `APP_ENVIRONMENT` | `development` | 로그의 `environment` 칸. 동작은 바꾸지 않는다 |
| `APP_VERSION` | `dev` | 로그의 `version` 칸. 배포할 때 git SHA 나 이미지의 버전을 넣는다 |
| `LOG_LEVEL` | `info` | 이 수준부터 로그를 남긴다(`debug`, `info`, `warning`, `error`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음(보내지 않음) | span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. `http://alloy:4318` 처럼 경로 없이 적는다([추적](#추적), [메트릭](#메트릭)) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | 메트릭을 보내는 간격(밀리초, 1000 이상) |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. 여기서 받은 키로 서명된 토큰을 믿는다 |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-chat` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다 |
| `ASSET_URL` | 비어 있음(부르지 않음) | asset 서버의 주소(`http://127.0.0.1:8006`). 대화를 시작할 때 캐릭터의 판과 페르소나의 사본을 가져온다([asset 서버의 다른 서버에 내주기](../asset-server/README.md#다른-서버에-내주기)). 비우면 대화를 시작하지 못한다(503) |
| `ASSET_SECRET` | 비어 있음 | asset 서버에 보내는 요청에 서명하는 비밀. `asset-server/.env` 의 `CHAT_SERVER_SECRET` 과 같은 값. `ASSET_URL` 을 적었으면 32자 이상이어야 뜬다. 비밀값이다 |
| `ASSET_TIMEOUT_SECONDS` | `5` | asset 서버를 한 번 부르는 시간의 상한(초, 30 까지). 대화를 시작하는 사람이 기다린다 |
| `BILLING_URL` | 비어 있음(받지 않음) | 결제 서버의 주소(`http://127.0.0.1:8003`). 모델의 값을 가격 목록에서 읽고, 말 한 번에 홀드를 건다([모델 목록](#모델-목록)). 비우면 모델은 값 없이 보이고 말은 공짜다 |
| `BILLING_SECRET` | 비어 있음 | 결제 서버에 보내는 요청에 서명하는 비밀. `billing-server/.env` 의 `CHAT_SERVER_SECRET` 과 같은 값. `BILLING_URL` 을 적었으면 32자 이상이어야 뜬다. 비밀값이다 |
| `BILLING_TIMEOUT_SECONDS` | `5` | 결제 서버를 한 번 부르는 시간의 상한(초, 10 까지). 게임 서버와 같다 |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ZAI_API_KEY`, `DEEPINFRA_API_KEY` | 비어 있음 | 모델 목록의 창구마다의 키. 비밀값이다. 키가 없는 창구의 모델로 말을 보내면 503 `provider_unavailable` 이다. 공급자가 내주는 값이라 `tools/fill_env.py` 가 만들지 않는다. 게임 서버와 다른 키(사용 한도를 따로 거는 키)를 권한다 |
| `OPENAI_BASE_URL` 등 `*_BASE_URL` | 게임 서버와 같다 | 창구의 주소. `LLM_BASE_URL` 은 모델 목록의 `local` 창구 모델에만 쓴다(지금은 없다) |
| `LLM_TIMEOUT_SECONDS` | `120` | 모델을 한 번 부르는 시간의 상한(초, 600 까지). 흘려 받는 답이 다 올 때까지다 |
| `CHAT_OUTPUT_LIMIT` | `1024` | 말 한 번의 답의 길이의 상한(토큰). 가격표의 출력 단계(`o0`)가 약속하는 길이다 |
| `CHAT_CONTEXT_CHARS` | `12000` | 모델에 보내는 지난 말의 양의 상한(글자). 최근 말부터 채운다. 가격표의 입력 단계(`i0`)가 약속하는 양이다 |
| `CHAT_TEMPERATURE` | `0.9` | 글의 다양함(0~2). 받지 않는 모델에는 보내지 않는다 |
| `SUMMARY_MODEL` | 비어 있음(요약하지 않음) | [굴리는 요약](#굴리는-요약)의 모델(모델 목록의 이름표). 싼 모델을 쓴다. 사용자에게 팔지 않는(꺼 둔) 모델도 된다. 원가는 서비스가 낸다 |
| `SUMMARY_AFTER_MESSAGES` | `8` | 창 밖으로 밀려난 말이 마지막 요약 뒤로 이만큼(2~200) 쌓이면 요약한다 |
| `REDIS_URL` | 비어 있음(메모리로 셈) | [요청 수 제한](#요청-수-제한)을 세는 Redis(`redis://redis:6379/2`, DB 2 가 chat 의 몫). 비우면 서버 안의 메모리로 센다(서버가 하나일 때만 맞다) |
| `REDIS_TIMEOUT_SECONDS` | `0.5` | Redis 를 한 번 부르는 시간의 상한. 넘으면 막지 않고 통과시킨다 |
| `LIMITS_ENABLED` | `true` | 요청 수 제한을 켠다(테스트가 끈다) |
| `LIMIT_KEY_PREFIX` | `chat:limit` | Redis 의 키의 앞부분 |
| `GENERATION_LIMIT`, `GENERATION_WINDOW_SECONDS` | `20`, `60` | 모델을 부르는 요청을 한 사람이 이 시간(초) 안에 이만큼까지 |
| `WRITE_LIMIT`, `WRITE_WINDOW_SECONDS` | `120`, `60` | 모델을 부르지 않는 쓰기를 한 사람이 이 시간(초) 안에 이만큼까지 |
| `CHAT_SUGGESTIONS` | `true` | [다음 답 추천](#다음-답-추천). 답 끝에 선택지 셋을 같은 호출에서 받는다. 출력이 조금 는다. 끄면 카드에 지시를 넣지 않는다 |

`tools/fill_env.py` 가 `ASSET_SECRET` 과 `BILLING_SECRET` 을 짝(asset 서버, 결제 서버의 `CHAT_SERVER_SECRET`)과 같은 값으로 채운다.
compose 는 서버에 두 주소를 주고, 마이그레이션(`chat-migrate`)에서는 두 주소와 비밀을 비운다(설정의 검사가 "주소는 있고 비밀이 없다"로 막지 않게).
서버만 쓰는 설정을 더해 그 검사가 마이그레이션에도 걸리면 `chat-migrate` 에서 같이 비운다.
환경 변수는 다른 서버와 같은 이름을 쓰고 머리(`CHAT_`)를 붙이지 않는다. 머리는 다른 서버의 설정에 들어가는 값(`CHAT_SERVER_SECRET`)에만 붙인다.

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
| GET | `/api/v1/chat/me` | 토큰의 주인(`{"user_id"}`, 인증 서버의 `public_id`). 토큰 검증이 이어졌는지 보는 가장 작은 주소다(게임 서버의 `GET /me` 와 같다) | access 토큰 |
| GET | `/api/v1/chat/models` | 대화에 고를 수 있는 [모델](#모델-목록)들과 말 한 번의 값(`{free, items}`). 켜져 있고 은퇴하지 않았고 결제 서버가 팔고 있는 것만. 회사, 이름표 순서. 가격 목록을 받지 못하면 503 `prices_unavailable` | access 토큰 |
| POST | `/api/v1/chat/conversations` | [대화](#대화) 시작. 201. `{character_id, start?, persona_id?, model?}`. 대화 하나(읽기와 같은 모양)를 돌려준다 | access 토큰 |
| GET | `/api/v1/chat/conversations` | 내 대화의 목록(`{items, total}`). 최근에 말한 것부터. `limit`, `offset`, `character_id`(asset 서버의 캐릭터 id) | access 토큰 |
| GET | `/api/v1/chat/conversations/{id}` | 대화 하나. 가져온 판과 페르소나, 시작 상황, 모델, 지금 가지의 말들(첫 말부터, 말마다 `alternatives` 와 `suggestions`), 가지 끝의 [상태](#장소와-소지품)(`state`), 답을 쓰는 중인지(`generating`) | access 토큰 |
| POST | `/api/v1/chat/conversations/{id}/messages` | [말 보내기](#한-번의-말). `{content, edit_of?}`. 바로 SSE 로 답한다(`turn`, `delta`, `done` 또는 `failed`). `edit_of` 는 [내 말 고치기](#고치기) | access 토큰 |
| POST | `/api/v1/chat/conversations/{id}/actions` | [행동](#장소와-소지품). 이동 `{kind: "move", place}`, 쓰기 `{kind: "use", item}`, 건네기 `{kind: "give", item, words?}`, 시간 보내기 `{kind: "wait"}`. 바로 SSE 로 반응을 받는다. 할 수 없으면 422(`no_map`, `place_not_found`, `already_there`, `not_connected`, `item_not_found`, `not_held`) | access 토큰 |
| GET, POST | `/api/v1/chat/conversations/{id}/notes` | [기억 메모](#기억-메모)들(먼저 쓴 것부터), 더하기 `{text}`(201). 가득 차면 409 `notes_full` | access 토큰 |
| GET | `/api/v1/chat/conversations/{id}/summary` | 지금 가지의 [굴리는 요약](#굴리는-요약)(읽기만, `{text, covered_up_to, created_at}`). 아직 없으면 `null` | access 토큰 |
| PATCH, DELETE | `/api/v1/chat/conversations/{id}/notes/{note_id}` | 메모 고치기 `{text}`, 지우기(204). 없으면 404 `note_not_found` | access 토큰 |
| PATCH | `/api/v1/chat/messages/{id}` | [상대의 말 고치기](#고치기). `{content}`. 고친 말을 돌려준다. 사람의 말이면 422 `not_editable` | access 토큰 |
| POST | `/api/v1/chat/messages/{id}/regenerate` | [다시 생성](#다시-생성-멈추기-대안). 그 말에 다시 답한다. SSE 의 모양은 말 보내기와 같다. 인사말은 422 `not_regenerable`, 없는 말은 404 `message_not_found` | access 토큰 |
| POST | `/api/v1/chat/messages/{id}/continue` | [이어서 출력](#이어서-출력). 끊긴 답(`partial`)에 이어 쓴다. SSE. 끊긴 답이 아니거나 지금 가지의 끝이 아니면 422 `not_continuable` | access 토큰 |
| POST | `/api/v1/chat/generations/{id}/stop` | [멈추기](#다시-생성-멈추기-대안). 204. 받은 만큼 저장한다. 멈출 것이 없으면 404 `generation_not_running` | access 토큰 |
| PUT | `/api/v1/chat/conversations/{id}/branch` | [다른 대안 보기](#다시-생성-멈추기-대안). `{message_id}`. 바뀐 대화를 돌려준다. 답을 쓰는 중이면 409 `generation_in_progress` | access 토큰 |
| PUT | `/api/v1/chat/conversations/{id}/model` | 대화의 모델 바꾸기. `{model}`. 바꾼 모델을 돌려준다. 고를 수 없으면 422 `model_unavailable` | access 토큰 |
| DELETE | `/api/v1/chat/conversations/{id}` | 지우기. 204. 지운 시각만 적는다 | access 토큰 |

**스트리밍(정한 것).** 말을 보내는 `POST /api/v1/chat/conversations/{id}/messages`, `POST /api/v1/chat/messages/{id}/regenerate`, `/continue`(모두 만들었다)가
바로 SSE(`text/event-stream`)로 답한다. 응답에 `X-Accel-Buffering: no` 를 싣고 15초 조용하면 하트비트(`: heartbeat`)를 끼운다. 끊겨도 서버는 생성을 끝까지 저장하고,
앱은 다시 들어와 저장된 말을 읽는다. 공용 코드의 `StreamRoutes` 로 span 과 요청의 시간 메트릭에서 빼고 `sse_*` 로 센다(`app/main.py` 의 `STREAMS`).

### 대화

캐릭터 하나와의 대화다(docs/architecture/chat-server.md 의 만드는 순서 1). `app/conversations/`, asset 서버를 부르는 것은 `app/assets/`.
한 번의 말(스트리밍, 과금)은 다음 조각이다.

**시작하기.** 캐릭터와 시작 상황만 고르고 들어간다(2026-10-20).

1. asset 서버에서 그 캐릭터의 **마지막 판**과 페르소나의 사본을 가져온다. 이 서버의 비밀(`ASSET_SECRET`)로 서명하고 사용자의 토큰을 그대로 넘긴다.
   쓸 수 있는 캐릭터인지는 asset 서버가 판단한다. 가져온 판의 등급은 이 서버도 한 번 더 본다(`allowed_ratings`).
2. 판의 시작 상황 가운데 `start`(0 부터, 기본 0) 번째를 고른다. 없으면 422 `start_not_found`(`starts` 에 판의 시작 상황의 수).
   제목, 상황, 시작 시각(`hour`, 1일째 몇 시. 판에 없으면 정오)을 대화에 복사해 둔다.
3. 판의 사본, 대화, 페르소나의 사본, 첫 말(캐릭터의 인사말)을 한 트랜잭션에서 저장한다. 인사말이 비어 있으면 첫 말이 없다.

| `persona_id` | 쓰는 페르소나 |
| --- | --- |
| 보내지 않음 | 지난번(가장 최근에 시작한) 대화의 것을 다시 가져온다. 그사이에 고쳤으면 새 revision 이다. 지난번에 없었거나 지워졌으면 없이 시작한다 |
| `null` | 없이 시작한다 |
| id | 그 페르소나. 없거나 남의 것이면 404 `persona_not_found` |

| asset 서버의 답 | 이 서버의 답 |
| --- | --- |
| 404(없다, 남의 비공개, 게시한 적 없음, 볼 수 없는 등급) | 404 `character_not_found` |
| 403 `adult_content_required`(자기 캐릭터인데 등급을 쓸 수 없다) | 403 `adult_content_required` |
| 닿지 못함, 시간 초과, 401, 5xx, 모양이 틀린 답, `ASSET_URL` 이 없음 | 503 `asset_unavailable`, `Retry-After: 5`. 다시 시도하지 않는다(사람이 다시 누른다) |

| `model` | 쓰는 모델 |
| --- | --- |
| 보내지 않음 | 지난번(가장 최근에 시작한, 지운 것도) 대화의 것. 지난번에 없었거나 이 대화에 고를 수 없으면 없이 시작한다 |
| `null` | 없이 시작한다. 말을 보내기 전에 고른다 |
| 이름표 | 그 모델. 이 대화에 고를 수 없으면 422 `model_unavailable`, 결제 서버의 가격 목록을 받지 못했으면 503 `prices_unavailable` |

어느 경우든 실패하면 아무것도 저장하지 않는다.

**모델.** 대화마다 하나다(`conversations.model_slug`, 모델 목록의 이름표). 고를 수 있는 모델은 켜져 있고 은퇴하지 않았고
결제 서버가 팔고 있는 것이고, 성인 등급의 대화(가져온 판의 등급)에는 그중 `allows_adult` 가 참인 것만이다. 고르거나 바꿀 때 한 번 본다.
그 뒤 모델이 꺼지거나 은퇴하거나 판매가 멈춰도 대화는 그 모델을 가리킨 채로 두고, 읽기와 목록의 `model.usable` 이 거짓이 된다.
화면이 다시 고르게 한다. 서버는 몰래 다른 모델로 바꾸지 않는다(TRPG 와 같은 원칙). 바꿔도 목록의 차례(최근에 말한 것부터)는 그대로다.
은퇴일과 원가의 날은 UTC 의 오늘로 본다.
결제 서버의 가격 목록을 받지 못했고 받아 둔 것도 없을 때: 사람이 고르거나 바꾸는 모델은 503 이다(값을 모르는 모델을 고르게 하지 않는다).
지난번 모델로 시작하는 것과 읽기는 그대로 된다. 값을 모르면 팔고 있다고 보고, 말을 보낼 때 결제 서버가 다시 본다.

- **사본.** 판의 사본(`characters`)은 사람마다, 판마다 하나다. 같은 판으로 여러 번 시작해도 하나를 함께 쓴다. 동시에 시작해도 하나만 남는다(`ON CONFLICT DO NOTHING`).
  가져온 뒤 바뀌지 않는다. 원본이 바뀌어도 그대로이고, 새 판과 새 설정을 알리는 것은 다음 조각이다.
- **DB 연결.** 지난번 페르소나를 읽은 뒤 트랜잭션을 닫고 asset 서버를 부른다. 바깥을 기다리는 동안 연결을 쥐지 않는다(연결의 몫이 5 + 5 다).
- **목록과 읽기.** 내 것만, 지우지 않은 것만, 볼 수 있는 등급(가져온 판의 등급)만 나온다. 나머지는 404 다.
- **가지.** 말은 트리다(`parent_id`). 대화는 지금 보고 있는 가지의 끝(`active_leaf_id`)을 가리키고, 읽을 때 재귀 쿼리로 끝에서 첫 말까지만 읽는다.
  가지 안의 차례는 시각이 아니라 깊이로 정한다(한 트랜잭션의 말들은 시각이 같다).
- **지우기.** 지운 시각만 적는다. 말과 사본은 남는다. 탈퇴할 때의 처리는 인증 서버의 알릴 곳에 chat 을 더하는 PR 이 정한다.
- 표의 모양은 설계 문서(docs/architecture/chat-server.md 의 "데이터의 모양")와 같다. 대화가 캐릭터의 사본을 바로 가리킨다(잇는 표가 없다).
  chat 은 캐릭터가 하나이고 story 는 자기 스키마에 자기 표를 둔다. 생성 중 표시(`generating_since`)는 말을 보내는 길을 만들 때 더한다.

### 모델 목록

대화에 쓸 수 있는 언어 모델들이다. `app/catalog/`. 게임 서버의 모델 목록(`trpg-server/app/catalog/`)을 줄여 옮겼다.

**원본은 파일 하나다**(`shared/ai-core/src/ai_core/model_catalog.toml`, #499). 게임 서버와 같은 파일을 이 서버의 표에 들여온다.
모델을 넣고, 칸을 고치고, 원가를 더하고, 날짜판과 은퇴일을 바꾸는 것은 파일을 고쳐 PR 로 올리고 `scripts.models sync` 로 들여온다.
들여오는 규칙은 게임 서버와 같다([게임 서버의 모델 목록](../trpg-server/README.md#모델-목록)). 새 모델은 꺼진 채 들어가고,
날짜판이 바뀌면 기록을 남기고 끈다. 파일에 없는 표의 모델은 지우지 않는다(대화와 청구 기록이 가리킨다).

이 서버만의 스위치는 둘이다. 파일에 없고 이 표에서 바꾼다.

| 칸 | 뜻 |
| --- | --- |
| `enabled` | 켜져 있나. 오늘의 원가가 있고 은퇴하지 않은 모델만 켠다. 게임 서버와 따로 켠다 |
| `allows_adult` | 성인 등급의 대화에 쓸 수 있나. 공급자의 약관을 확인하고 성인 평가 장면을 통과한 뒤에 켠다([설계의 성인 콘텐츠](../docs/architecture/chat-server.md#성인-콘텐츠)). 약관이 성적인 콘텐츠를 막는다고 확인된 창구(`anthropic`, `gemini`)의 모델은 켜지 못한다(`adult_refused`). 전체 이용가의 대화에는 그대로 쓴다 |

게임 서버와 다른 것: 회사의 대체 모델(`vendor_fallback`)이 없다. chat 은 모델이 끝나도 몰래 바꾸지 않고 사람이 고른다.
**값.** 판매가(말 한 번에 몇 크레딧)는 결제 서버의 가격표(`chat.<이름표>.i0.o0`)가 정한다. 이 서버는 받은 값을 붙여 보여 줄 뿐이고,
실제로 빠지는 값은 홀드를 걸 때 결제 서버가 정한다. `app/billing/` 은 게임 서버의 것에서 결제 서버를 부르는 부분만 옮겼다(나중에 server-core 로 올린다).

- 가격 목록(`GET /api/v1/billing/service/prices`, 서명)을 받아 두고 1분쯤마다 버전(ETag)으로 다시 묻는다. 결제 서버는 이 서버의 머리(`chat`)의 줄만 낸다.
  받지 못하면 마지막 목록을 쓰고 경고를 남긴다. 한 번도 받지 못했으면 503 `prices_unavailable`(`Retry-After: 30`)이다.
- 모델 목록 API 의 값 칸은 게임 서버의 서술 모델 목록과 같다: `credits`(글자, 결제 서버 없이 돌면 null), `tier`(`premium` 이면 골드로만 낸다),
  `promo`(행사가), `next`(예약된 바뀜. `credits` 가 null 이면 그때부터 팔지 않는다). 예약의 시각이 지나면 다시 받기 전에도 스스로 갈아 끼운다.
- 홀드, 확정, 반환, 연장(`app/billing/http_billing.py`)은 말을 보내는 PR 이 쓴다. 부를 때마다 `billing_calls_total` 을 센다.
- `BILLING_URL` 이 비면 받지 않는다(`free`). 모델은 값 없이 모두 보이고, 홀드는 언제나 잡힌 것으로 본다.

창구와 생각의 방식, 출력 상한의 칸은 표의 CHECK 로도 막는다. ai-core 의 목록(`catalog_contract`)에 값이 늘면 이 서버에도 마이그레이션이 필요하다.
`alembic check` 는 CHECK 의 차이를 보지 못해서, 테스트(`tests/test_catalog_sync.py`)가 표의 CHECK 와 계약의 목록을 맞대어 본다.

#### 관리 명령

관리 화면이 생기기 전까지 이것으로 들여오고, 켜고 끈다. `chat-server` 폴더에서 돌린다. 설정(`.env`)의 DB 를 쓰고 서버를 띄우지 않아도 된다.

```powershell
uv run python -m scripts.models sync --dry-run
uv run python -m scripts.models sync
uv run python -m scripts.models sync --file ..\shared\ai-core\src\ai_core\model_catalog.toml
uv run python -m scripts.models list
uv run python -m scripts.models list --on 2026-12-01
uv run python -m scripts.models show glm-5-3
uv run python -m scripts.models enable glm-5-3
uv run python -m scripts.models disable glm-5-3
uv run python -m scripts.models adult glm-5-3 --allow
uv run python -m scripts.models adult glm-5-3 --forbid
```

| 명령 | 하는 일 |
| --- | --- |
| `sync` | 파일을 들여온다. `--file` 이 없으면 설치된 ai-core 에 든 파일이다. `--dry-run` 은 바뀔 것만 보인다 |
| `list` | 모든 모델과 그날의 원가(입력/출력, USD, 백만 토큰당). 성인 등급의 대화에 쓰는 모델에는 `성인` 이 붙는다 |
| `show` | 모델 하나. 받는 것, 원가들, 날짜판을 바꾼 일 |
| `enable`, `disable` | 켜고 끈다. 지우지 않는다 |
| `adult --allow`, `adult --forbid` | 성인 등급의 대화에 쓰게 하거나 쓰지 않게 한다. 끄면 그 모델을 고른 성인 대화는 `usable` 이 거짓이 된다 |

거절되면(없는 모델, 원가가 없음, 은퇴함, 약관이 막는 창구, 파일이 틀림) 까닭을 찍고 1 로 끝난다. 일은 `app/catalog` 의 함수가 하고, 명령은 찍기만 한다.

### 한 번의 말

사람의 말을 받아 모델의 답을 흘려보낸다(설계의 "한 번의 말이 지나가는 길"). `app/turns/`, chat 과 story 가 함께 쓸 부분은 `app/conversation/`(창, SSE, 흘려보내기).

| 차례 | 하는 일 | 실패하면 |
| --- | --- | --- |
| 1 | 대화와 모델을 본다. 차례를 잡는다(`conversations.generating_since` 의 조건부 UPDATE, 한 대화 한 생성). 사람의 말과 기록(`generations`, `pending`)을 한 트랜잭션에 저장한다 | 404, 409 `model_required`, 422 `model_unavailable`, 409 `generation_in_progress`. 아무것도 저장하지 않는다 |
| 2 | 모델을 부를 provider 를 고른다(ai-core 의 `ModelRouter`, 모델 목록대로) | 503 `provider_unavailable`(키가 없다), 422 `model_unavailable` |
| 3 | 홀드를 건다(`chat.<이름표>.i0.o0`, 이름표 `chat:gen:<기록의 id>`) | 402 `credit_short`, 402 `gold_required`, 422 `model_unavailable`(팔지 않는다), 503 `billing_unavailable` |
| 4 | SSE 를 시작하고, 따로 도는 작업이 모델을 부른다. 받는 대로 `delta` 로 흘린다 | 이 뒤의 실패는 SSE 의 `failed` 다 |
| 5 | 받은 만큼 답을 저장하고 차례를 놓는다. 가지의 끝이 답이 된다 | 글자 없이 실패하면 답을 저장하지 않는다(`failed`) |
| 6 | 답이 있으면 확정, 없으면 반환한다 | 결제 서버가 받지 못하면 청구 정리가 마저 한다 |

2, 3 에서 거절하면 사람의 말은 남는다(응답의 `message_id`). 설계의 "모자라면 말은 저장하되 생성하지 않는다"다. 차례는 놓고 기록은 `declined` 다.

| 끝 | 답 | 청구 |
| --- | --- | --- |
| 다 받았다 | `complete` | 확정 |
| 길이 상한에서 잘렸다, 도중에 끊겼다(공급자의 오류) | 받은 만큼 `partial`. [이어서 출력](#이어서-출력)으로 이어 쓴다 | 확정(설계의 과금 표) |
| 글자 없이 실패했다, 빈 답이다 | 없다(SSE `failed`, `code` 는 `timeout`, `status_429`, `empty` …) | 반환 |
| 사람이 멈췄다 | 받은 만큼 `partial`(없으면 없다, SSE `failed` 의 `stopped`) | 바로 확정이나 반환 |
| 서버가 꺼지며 멈췄다 | 받은 만큼 `partial`(없으면 없다) | 다음에 뜬 서버의 청구 정리가 확정이나 반환 |

- **끊겨도 끝까지.** 모델을 부르는 것은 응답과 따로 도는 작업이다(`app.state.turns`). 사람이 앱을 닫아도 끝까지 돌아 저장하고 확정한다.
  서버가 꺼질 때(lifespan)는 도는 작업을 멈추고, 각 작업은 받은 만큼 저장한 뒤 멈춘다.
- **같은 실패를 되풀이하지 않는다.** 저절로 다시 부르지 않고 다른 모델로 넘어가지 않는다. 사람이 다시 생성한다.
- **차례.** 15분(`GENERATION_STALE`, 모델의 시간 상한보다 길다)이 지난 차례는 서버가 도중에 꺼진 것으로 보고 다음 말이 다시 잡는다.
- **모델에 보내는 것.** 카드(지킬 것, 캐릭터, 사용자 페르소나, 시작 상황. 빈 칸은 뺀다)와 지금 가지의 최근 말(`CHAT_CONTEXT_CHARS` 안, 마지막 말은 늘)이다.
  요약, 기억 메모, 로어북, 장소와 소지품은 그 단계에서 끼운다.
- **청구 정리**(`app/turns/settler.py`, 5초마다). 확정할 것과 돌려줄 것을 맡긴다. 맡기지 못하면 5초, 10초 … 5분 뒤로 미룬다.
  `pending`, `held` 인 채로 15분이 지난 것(서버가 꺼졌다)은 돌려준다. 결제 서버가 받아들이지 않으면 `failed` 로 두고 로그에 남긴다(사람이 본다).
- **원가.** 기록에 토큰 수와 그날의 단가로 센 원가(`cost_usd`)를 남긴다. 판매가가 원가를 넘는지 볼 때 쓴다.
- 요청 수의 제한은 [요청 수 제한](#요청-수-제한)에 있다. 한 대화 한 생성과 크레딧과 함께 상한이 된다.

### 다시 생성, 멈추기, 대안

대화는 트리다(`messages.parent_id`). 같은 부모 아래의 말들이 서로의 대안이고, 대화가 지금 보는 가지의 끝(`active_leaf_id`)이 하나 있다.

- **다시 생성**(`POST /messages/{id}/regenerate`). 캐릭터의 답이면 그 부모(사람의 말) 아래에, 사람의 말이면(답을 못 받았다) 그 말 아래에 새 답을 쓴다.
  사람의 말은 새로 저장하지 않는다. 모델에는 그 사람의 말까지의 가지가 간다(앞의 답은 보내지 않는다). 새 호출이라 새로 청구한다.
  나머지(차례, 홀드, SSE, 실패)는 말 보내기와 같다. `turn` 의 `user_message` 는 답할 사람의 말이다.
  가지의 끝은 새 답을 저장할 때 옮긴다. 거절되거나 글자 없이 실패하면 앞의 답이 그대로 보인다.
  인사말(부모가 없는 캐릭터의 말)은 카드가 쓴 글이라 다시 쓰지 않는다(422 `not_regenerable`).
- **멈추기**(`POST /generations/{id}/stop`). `turn` 의 `generation_id` 로 부른다. 공급자 호출을 끊는다(끊지 않으면 청구하지 않는 글에 원가가 든다).
  받은 만큼 `partial` 로 저장하고 바로 확정한다. 받은 글이 없으면 반환하고 SSE 는 `failed`(`stopped`)로 끝난다.
  사람이 멈추는 것은 모델을 부르는 일만 끊는다. 저장과 확정은 끊지 않는다. 서버가 꺼지며 멈추는 것(작업 전체의 취소)과 가른다.
  멈추는 스위치는 그 생성을 돌리는 서버의 메모리(`app.state.stops`)에 있다. 서버가 여럿이면 다른 서버에 닿은 멈추기는 404 다.
  지금은 한 대로 돈다. 늘리면 Redis 의 pub/sub 같은 것으로 알린다.
- **대안 오가기.** 대화를 읽으면 지금 가지의 말마다 `alternatives`(같은 부모 아래의 말들의 id, 먼저 생긴 것부터, 이 말도 든다)가 실린다.
  화면이 "< 2/3 >" 를 그린다. 다른 대안을 고르면(`PUT /conversations/{id}/branch`) 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다.
  보는 곳만 바꾸는 것이라 수정 시각(목록의 차례)은 그대로다. 답을 쓰는 중이면 바꾸지 않는다(409). 확인과 바꾸기를 한 문장으로 한다.
- **`generating`.** 대화가 차례를 쥐고 있으면 참이다(15분이 지난 차례는 아니다). 화면이 보내기와 다시 생성을 막고, 끝난 뒤 다시 읽는다.

### 다음 답 추천

캐릭터의 답 끝에 사람이 이어서 할 만한 말 셋을 함께 받는다(`app/conversation/suggestions.py`). 누르면 입력칸을 채우고, 보내는 것은 사람이다.

- **같은 호출에서 받는다.** 카드의 맨 끝에 "본문을 다 쓴 뒤 새 줄에 `<suggestions>` 를 쓰고 그 아래에 한 줄에 하나씩 써라"를 넣는다.
  호출이 늘지 않아 원가가 거의 그대로다(출력이 조금 는다). 끄려면 `CHAT_SUGGESTIONS=false`.
- **본문만 흘린다.** 표식이 조각의 경계에 걸릴 수 있어서, 끝의 몇 글자(표식의 앞부분일 수 있는 것)는 다음 조각이 올 때까지 붙잡는다. 표식 뒤는 흘리지 않는다.
- **따로 저장한다.** 본문은 `content`, 선택지는 `suggestions`(`done` 의 말과 대화 읽기에 실린다). 다음 호출에는 본문만 간다. 섞으면 모델이 선택지를 흉내 낸다.
- **거른다.** 줄마다 하나. 번호, 글머리표, 감싼 따옴표를 떼고, 빈 것, 200자보다 긴 것, 같은 것을 뺀 뒤 셋까지. 형식이 깨지면 선택지만 줄거나 없어지고 오류로 만들지 않는다. 표는 넷 이상을 받지 않는다(CHECK).
- **잘린 답**(길이 상한)은 선택지를 버린다(줄이 잘렸을 수 있다). 끊기거나 멈춘 답도 본문만 저장한다. 표식만 쓴 답은 빈 답(`failed` 의 `empty`)이다.

### 장소와 소지품

캐릭터의 판에 지도(장소, 길, 처음 있는 장소)와 물건(물건, 시작 소지품)이 있으면 대화가 그 안에서 돈다(`app/world/`, 설계의 "장소와 소지품").
상태는 서버가 갖고 바꾼다. 모델은 바뀐 상태를 읽고 반응만 쓴다.

- **상태.** 지금 있는 장소(`place`), 대화를 시작한 뒤 흐른 시간(`minutes`), 사용자의 소지품(`inventory`), 가 본 장소(`visited`, 화면이 안개를 그린다),
  상대의 차림(`outfit`, 사용자가 건넨 옷), 호감도(`affection`, 아래), 지금 시각(`clock`)과 배경(`background`, [시각과 배경](#시각과-배경)).
  처음에는 판의 시작 상태다. 지도가 없는 캐릭터면 장소가 없다(`null`).
- **말마다.** 상태는 바뀐 말(행동 말)에만 적는다(`message_states`, 매번 전체를). 나머지 말은 부모의 상태를 따르고, 지금의 상태는 가지의 끝에서 거슬러 올라가 읽는다.
  그래서 다시 생성하거나 앞 가지로 가면 그 가지의 상태가 된다. 되돌리기가 가지를 바꾸는 것으로 끝난다.
- **이동**(`POST /conversations/{id}/actions`, `{kind: "move", place}`). 지금 있는 곳과 길로 바로 이어진 곳만 간다(길은 양쪽으로).
  행동 말(`role` 이 `action`, "카페에 갔다. 15분이 걸렸다.")과 바뀐 상태를 저장하고, 모델의 반응을 흘려보낸다. 반응을 받으니 한 번 청구한다.
  갈 수 없으면 422 이고 아무것도 저장하지 않는다. 홀드가 거절되면 행동 말과 상태는 남는다(사람의 말과 같다). 반응은 다시 생성으로 받는다.
- **쓰기**(`{kind: "use", item}`). 가진 물건만 쓴다. 쓰면 없어지는 물건(판의 `consumable`, 음식 등)은 하나 줄고, 아니면(우산 등) 남는다(물건마다 정한다).
- **건네기**(`{kind: "give", item, words?}`). 가진 물건을 하나 상대에게 건넨다. 옷(`kind` 가 `clothing`)이면 상대가 입는다(차림에 한 번만 든다).
  `words` 는 덧붙이는 한마디다. 행동 말 아래에 사람의 말로 붙고, 반응은 그 한마디에 답한다(행동과 말이 한 턴, 한 번 청구).
  SSE 의 `turn` 에서 `user_message` 가 한마디, `action` 이 그 위의 행동 말이다. 한마디가 없으면 `user_message` 가 행동 말이고 `action` 은 `null` 이다.
- 수가 0 이 되면 소지품에서 빠진다. 가지고 있지 않으면 422 `not_held`, 판에 없는 물건이면 422 `item_not_found` 다.
- **모델에 보내는 것.** 카드에 "[지금]" 블록(시각, 장소와 설명, 갈 수 있는 곳과 시간, 소지품, 상대의 차림, 호감의 단계)이 들어간다. 시각이 늘 있으므로 블록도 늘 있다. 행동 말은 "[행동] …"으로 사람의 차례에 간다.
- **호감도**(`app/world/affection.py`). 판에 호감도가 있으면 시작 값에서 출발해, 사용자의 행동(건넸다, 갔다, 썼다)에 제작자가 적은 규칙대로 엔진이 바꾼다(0~100 으로 자른다).
  "처음 한 번만" 규칙은 그 가지에서 한 번만 걸린다(걸린 규칙을 상태에 적는다). 대화의 내용만으로는 움직이지 않는다(첫 출시).
  모델에는 단계 이름만 간다("사용자에 대한 호감: 친구"). 응답의 `affection` 은 `{display, value, stage, stage_index, stages}` 이고,
  단계로 보이는 캐릭터(`display` 가 `stage`)는 `value` 가 `null` 이다(숫자를 내려보내지 않는다). 호감도를 더하기 전에 적힌 상태는 시작 값으로 읽는다.
- 상대가 받은 선물의 목록, 모델이 호감도의 변화를 제안하는 것은 그 뒤다. 규칙은 `app/world/` 에 두고, TRPG 와 함께 쓸 때 `shared/` 로 뽑는다.

#### 시각과 배경

대화는 고른 시작 상황의 시각(1일째 `hour` 시)에서 시작한다. 이동(길의 시간)과 시간 보내기로 흐른다(#668, `app/world/clock.py`).

- **시각.** 시작 시각(대화의 `start_hour`)에 상태의 흐른 시간(`minutes`)을 더한 것이다. 응답의 `clock` 은 `{day, hour, minute, time_of_day}` 이다.
  따로 적지 않고 계산하므로 서로 어긋날 일이 없다. 모델에는 "시각: 2일째 저녁 18:30" 으로 간다.
- **시간대**는 다섯이고 경계는 TRPG 와 같다(2026-10-22 유저 결정): 새벽(`dawn`) 4시, 아침(`morning`) 7시, 낮(`day`) 11시, 저녁(`evening`) 17시, 밤(`night`) 21시. 4시 전은 밤이다.
- **시간 보내기**(`{kind: "wait"}`, 2026-10-22 유저 결정). 다음 시간대가 시작하는 시각까지 흐른다. 밤이면 다음 날 새벽 4시다.
  행동 말("시간을 보냈다. 저녁이 되었다.")을 붙이고 반응을 받는다(한 번 청구). 지도가 없어도 되고 막는 까닭이 없다. "하루 마치기"는 두지 않는다.
- **배경**(`background`). 지금 장소의 그 시간대의 배경, 없으면 장소의 기본 배경, 그것도 없거나 장소가 없으면 `null` 이다. 화면이 같은 규칙을 다시 짜지 않게 서버가 고른다.
  기본 배경의 색감만 바꿔 시간대를 보이는 연출은 화면의 일이다(나중).
- 시작 시각을 더하기 전에 만든 대화는 정오에 시작한 것으로 본다.

### 기억 메모

상대가 기억할 것을 사용자가 적고 고치는 짧은 글이다(`app/memory/`, 설계의 "기억"의 셋째 층, 화면 명세 C5). 대화마다 따로 있다.

- 모델의 카드에 "[기억]" 으로 늘 간다(시작 상황 뒤, 장소와 소지품 앞). 틀린 기억을 사람이 바로잡는 길이다.
- 하나에 300자, 대화 하나에 스물까지다. 늘 모델에 가는 글이라 입력의 양을 지킨다. 더할 때 대화의 행을 잠그고 세어 동시에 더해도 넘지 않는다.
- 답을 쓰는 중에도 고칠 수 있다. 고친 것은 다음 말부터 간다. 호출이 아니라 청구하지 않는다.
- 출처(`source`)는 사용자가 쓴 것(`user`)과 요약이 제안한 것(`summary`)이다. 요약의 제안은 아직 만들지 않는다. 생기더라도 받아들이기 전에는 모델에 가지 않는다.
- 가지와 상관없다(대화 하나에 하나의 목록). 대화를 지우면(행) 함께 지워진다.

### 굴리는 요약

최근 대화의 창(`CHAT_CONTEXT_CHARS`)에 들지 못하고 밀려난 앞부분을 싼 모델로 요약한다(`app/memory/summaries.py`, `summarizer.py`, 설계의 "기억"의 둘째 층).

- **언제.** 말 한 번이 끝나면(멈추지 않았으면) 그 대화를 한 번 본다. 밀려난 말이 마지막 요약 뒤로 `SUMMARY_AFTER_MESSAGES` 개 쌓였으면 요약한다.
  앞의 요약과 그 뒤의 말을 합쳐 새 요약을 쓴다(굴린다). 응답과 따로 돌아 사람은 기다리지 않는다.
- **어디에 붙나.** 요약은 밀려난 마지막 말에 붙는다(`summaries.message_id`, 첫 말부터 그 말까지의 요약). 대화는 트리라서 첫 말부터 어느 말까지의 길은 하나뿐이다.
  그래서 앞 가지로 돌아가도 그 가지에 있는 말의 요약을 쓰면 맞다. 버리고 다시 만들 일이 없다. 원본 말은 늘 남는다.
- **모델에 보내는 것.** 밀려난 말 가운데 가장 뒤의 요약이 카드에 "[앞의 줄거리]" 로 간다(시작 상황 뒤, 기억 메모 앞). 창 안의 말에 붙은 요약은 보내지 않는다(겹친다).
  그 요약 뒤에서 창 앞까지의 말은 다음 요약이 생길 때까지 빠진다.
- **원가.** 서비스가 낸다. 청구하지 않고 요약의 행에 모델, 토큰, 원가를 적는다. `SUMMARY_MODEL` 을 비우면 요약하지 않는다(창만 쓴다).
- **실패.** 로그(`chat.summary`)만 남기고 대화는 이어진다. 다음 말 한 번이 끝나면 다시 본다. 모델이 빈 글을 주면 적지 않는다.
- 한 대화에 한 번에 하나만 돈다(이 서버 안). 서버가 여럿이라 같은 말의 요약을 둘이 써도 먼저 쓴 것만 남는다. 서버가 꺼질 때 도는 요약을 멈춘다.
- 사람에게는 `GET /conversations/{id}/summary` 로 읽기만 보인다(화면 명세 C5).

### 요청 수 제한

한 사람이 짧은 시간에 너무 많이 보내지 못하게 막는다(`app/limits/`, #671). "한 대화에 한 생성"과 크레딧만으로는, 대화를 여럿 열어 몰아 보내거나 청구하지 않는 요청을 많이 보내는 것을 막지 못한다.

| 제한 | 세는 요청 | 기본 |
| --- | --- | --- |
| 생성 | 말 보내기, 행동, 다시 생성, 이어서(모델을 부른다) | 60초에 20번 |
| 쓰기 | 대화 시작과 지우기, 모델과 가지 바꾸기, 상대의 말 고치기, 기억 메모 더하기·고치기·지우기 | 60초에 120번 |

- 사람마다 센다(대상은 해시해서 키에 넣는다). 읽기와 멈추기는 세지 않는다. 넘으면 429 `too_many_attempts` 와 `Retry-After`(기다릴 초, 본문의 `retry_after`).
- 고정 구간이다(첫 요청에서 시작해 구간이 끝나면 처음부터). 올리기와 만료를 Lua 한 덩어리로 보낸다. 인증 서버, 게임 서버와 같은 방식이다.
- Redis 에 닿지 못하면 막지 않고 통과시키며 경고(`limits.unavailable`)를 남긴다. 대화를 막아서 잃는 것이 더 크다. 그래서 상태 확인(`/health/ready`)도 Redis 를 보지 않는다.
- 게임 서버의 `app/limits/` 에서 chat 이 쓰는 부분만 옮겼다. 셋째로 쓰는 곳(story)이 생기면 server-core 로 뽑는다.

### 고치기

고친 글이 다음 호출부터 모델에 간다. 둘 다 답을 쓰는 중이면 409 `generation_in_progress` 다.

| | 내 말 고치기 | 상대의 말 고치기 |
| --- | --- | --- |
| 주소 | 말 보내기에 `edit_of`(고칠 사람의 말의 id) | `PATCH /messages/{id}` |
| 하는 일 | 고칠 말의 부모 아래에 새 말을 붙이고 답을 받는다. 새 가지다. 원본과 그 답은 남아 대안으로 오간다 | 그 말을 그 자리에서 고친다. `edited` 가 참이 되고 선택지는 지운다(앞의 글에 맞춘 것이다) |
| 청구 | 답을 받으니 한 번 | 호출이 아니라 없다 |
| 안 되는 것 | 캐릭터의 말을 고르면 422 `not_editable` | 사람의 말이면 422 `not_editable`(원본을 남기려고 새 가지로만 고친다) |

- 상대의 말 고치기는 "답을 쓰는 중인가" 확인과 고치기를 UPDATE 한 문장으로 한다. 따로 하면 그사이 시작한 이어 쓰기가 끝나며 고친 글을 덮는다.
- 대화의 수정 시각(목록의 차례)은 바꾸지 않는다. 말한 것이 아니다. 내 말 고치기는 말을 보낸 것이라 바뀐다.
- 인사말도 고칠 수 있다(대화마다의 사본이다).
- 말 보내기는 가지의 끝을 차례를 잡은 뒤에 다시 읽는다. 그사이 다른 가지를 골랐으면 고른 가지에 붙는다.

### 이어서 출력

끊긴 답(`partial`. 길이 상한에서 잘렸거나, 도중에 끊겼거나, 멈췄다)에 이어 쓴다(`app/conversation/continuation.py`). 사람이 "이어서"를 누를 때만 한다. 저절로 하지 않는다.

- **지시로 시킨다.** 끊긴 답까지의 대화를 보내고, 맨 끝에 사람의 차례로 "끊긴 곳 바로 다음 글자부터 이어 써라(사용자의 말이 아니다)"를 붙인다.
  답을 미리 채워 이어 쓰게 하는 길이 공급자마다 있거나 없어서, 모든 공급자에서 똑같이 도는 쪽으로 했다. 대화가 사람의 말로 끝나야 받는 공급자도 있다.
- **되풀이한 앞부분은 뗀다.** 새 글의 앞이 끊긴 답의 끝(300자 안)과 8자 이상 겹치면 겹친 만큼 뗀다. 흘릴 때는 새 글이 끊긴 답의 어느 끝부분과 같게 이어지는 동안만 붙잡고, 어긋나면 바로 흘린다.
  끊긴 답이 문장 끝(마침표 등)에서 끊겼고 새 글이 빈칸 없이 시작하면 빈칸 하나를 끼운다(저장한 끊긴 답은 끝의 빈칸을 뺐다).
- **같은 말에 붙인다.** 새 말을 만들지 않는다. SSE 의 `turn` 에 `continues`(그 말의 id)가 실리고, `delta` 는 그 말 끝에 붙일 글, `done` 은 이어 붙인 그 말 전체다.
  다 쓰면 `complete` 가 되고 선택지가 붙는다. 또 끊기면 `partial` 로 남아 다시 이어 쓸 수 있다. 글 없이 실패하거나 거절되면 끊긴 답은 그대로다.
- **새로 청구한다.** 입력을 다시 보내고 원가가 또 든다(설계의 과금 표). 홀드와 확정, 멈추기, 차례는 말 보내기와 같다.
- **지금 가지의 끝만.** 끊긴 답 뒤에 말이 붙었거나 다른 가지를 보고 있으면 422 `not_continuable` 이다. 그 뒤의 말이 끊긴 답을 보고 쓴 것이라서다.
  가지의 끝은 차례를 잡은 뒤에 다시 읽는다(차례를 쥔 동안에는 가지를 바꾸지 못한다).

### 토큰 검증

공용 코드 `shared/server-core` 의 것(`server_core/auth/`)을 쓴다(#588). 알림 서버와 같다. 규칙의 설명은
[게임 서버의 토큰 검증](../trpg-server/README.md#토큰-검증)에 있다. 토큰의 주인(`CurrentUser`)에는 성인 등급(`adult_content`)과
운영자(`is_operator`)도 실린다. 성인 등급의 캐릭터와 대화를 거를 때 쓴다(`allowed_ratings`, 대화를 만들 때 한 번).

- 공개키: 처음 필요할 때 가져와 5분 기억한다. 모르는 `kid` 면 다시 가져오되 60초에 한 번만. 30분 넘게 못 가져오면 버리고 503.
- 끊긴 세션: 서버가 뜨자마자, 그 뒤 30초마다 인증 서버의 목록을 받는다. `ver` 가 그 사람의 `min_ver` 보다 낮은 토큰은 401.
- 토큰의 대상(`aud`)에 `ai-trpg-chat` 이 있어야 한다. 인증 서버의 `JWT_AUDIENCE` 기본값에 이 이름을 더하는 것은 인증 세션이 한다.
  그 전에 발급된 토큰에는 이 이름이 없어서 401 이다(access 토큰은 15분 뒤 저절로 맞는다).
  인증 서버의 `.env` 에 `JWT_AUDIENCE` 를 적어 둔 PC 는 그 줄에도 이 이름을 더한다.

## 로그

[관측 규격](../docs/observability.md)을 따른다. 공용 코드 `shared/server-core` 의 `server_core/observability/` 를 쓴다(#588).
이 서버의 이름(`chat-server`)은 설정(`app/core/config.py` 의 `service_name`)이 넘긴다. 공용 코드가 남긴 줄의 `logger` 는 `server_core.*` 다.

- 로그는 한 줄에 하나의 JSON 이다(`service`: `chat-server`). 표준 오류로 나간다.
- 요청마다 `X-Request-ID` 를 걸고 응답에 돌려준다. 요청이 끝나면 한 줄(`http.request`)을 남긴다. 주소는 경로의 틀로 적고 실제 값과 쿼리는 적지 않는다.
- 인증 서버를 부를 때 `traceparent` 로 추적을 이어 준다. span 을 내보내면 그 호출의 span 이 부모가 된다.
- 처리하지 못한 예외는 내부를 드러내지 않는 500 이다. 원인은 로그에 남는다. DB 주소, 토큰 같은 것은 로그에서도 가린다.

| `operation` | 언제 |
| --- | --- |
| `http.request` | 요청이 끝났다 |
| `auth.revocations_fetch` | 끊긴 세션의 목록을 받지 못했다(`warning`, `auth.revocations_unavailable`) |
| `charge.settle` | 청구 정리가 한 바퀴를 돌았다(맡긴 것이 있으면 `info`, 없으면 `debug`). 바퀴마다 `job_id`. 게임 서버와 같은 이름이다 |
| `chat.summary` | [굴리는 요약](#굴리는-요약)을 쓰지 못했다(`error`, `conversation_id`). 대화는 이어진다 |

## 추적

요청, 인증 서버를 부르는 것, 쿼리를 span 으로 남겨 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 민다. 수집기가 Tempo 에 넘긴다.
규칙과 까닭은 [관측 규격](../docs/observability.md)의 "3. 추적"에 있다. 주소가 비어 있으면 span 이 생기지 않고 로그는 지금과 같다.

| span | 이름 | 코드 |
| --- | --- | --- |
| 요청 | `GET /api/v1/chat/me`(메서드와 경로의 틀). 상태 확인은 걸지 않는다 | `server_core/observability/request_spans.py` |
| 인증 서버를 부르는 것 | `HTTP GET` | `server_core/observability/http_spans.py` |
| 쿼리 | `db SELECT conversations`(종류와 테이블). 손으로 쓴 것은 `db SELECT` | `server_core/observability/db_spans.py` |
| 뒤의 작업 | 작업의 이름. 한 바퀴가 새 추적 하나다 | `server_core/observability/spans.py` 의 `job_span` |

- 로그의 `trace_id` 가 span 의 trace id 와 같다. 요청의 span 에는 `request_id`, 작업의 span 에는 `job_id` 를 싣는다
- 싣지 않는 것: 주소의 경로와 뒤의 값, 머리말, 본문, SQL 의 문장과 값, 예외의 글. 쿼리가 실패하면 SQLSTATE 만 적는다
- 요청이나 작업 밖의 쿼리와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 span 을 걸지 않는다
- 뒤의 작업을 감싸는 틀(`job_span`, `job_scope`, `measured_job`)은 아직 쓰는 곳이 없다. 요약과 임베딩을 서버 안의 바퀴(loops)로 돌릴 때 쓴다. 테스트는 `tests/jobs.py` 의 바퀴로 본다
- span 은 따로 도는 스레드가 묶어서 보낸다. 서버가 꺼질 때 남은 것을 보낸다(5초 안). 수집기가 죽어 있어도 요청은 영향을 받지 않는다

## 메트릭

요청, DB, 뒤의 작업을 세어 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 15초마다 민다. 수집기가 Prometheus 에 넘긴다.
이름과 label 은 [관측 규격](../docs/observability.md)의 "메트릭"에 있다. 주소가 비어 있으면 세기만 하고 보내지 않는다.

| 메트릭 | label | 세는 곳 |
| --- | --- | --- |
| `http_server_requests_total`, `http_server_request_duration_seconds`, `http_server_active_requests` | `method`, `route`(경로의 틀), `status_code` | `server_core/observability/request_metrics.py`. 미들웨어의 맨 바깥이다 |
| `db_up` | 없음 | `app/api/readiness.py`. 준비 상태 확인이 본 DB |
| `db_pool_connections`, `db_pool_connections_max`, `db_pool_wait_seconds` | `state`(`idle`, `in_use`) | `server_core/observability/pool_metrics.py`. 풀은 5 + 넘칠 때 10 이다 |
| `background_jobs_started_total`, `background_jobs_finished_total`, `background_jobs_running`, `background_job_duration_seconds` | `operation`, `result` | `server_core/observability/metrics.py` 의 `measured_job`. 청구 정리(`charge.settle`)의 바퀴마다 |
| `sse_connections`, `sse_connections_opened_total`, `sse_connection_duration_seconds` | 없음 | `server_core/observability/metrics.py` 의 `measured_stream`. 말을 보내는 SSE 하나마다(`app/turns/router.py`) |
| `billing_calls_total` | `operation`(`hold`, `capture`, `release`, `extend`), `outcome` | `app/billing/metered.py`, `metrics.py`. 결제 서버를 부른 수. 게임 서버와 같은 이름과 label 이다 |

- 계측기는 공용 코드(`server_core/observability/metrics.py`)에 한 묶음으로 있다. 이 서버만의 계측기는 `InstrumentSet` 으로 더한다(`app/billing/metrics.py`).
  테스트는 `server_core/testing/metrics.py` 로 메모리에 모아 이름, 단위, label 을 본다(`metrics` fixture)
- 보내는 길은 공용 코드의 테스트가 가짜 수집기로 본다. 이 서버가 꺼질 때 이 서버의 이름으로 보내는지는 `tests/test_tracing_setup.py` 가 본다
- 대시보드와 경보, Prometheus 에 들어오는지 보는 CI(`stack`)는 인프라 세션의 PR 과 함께 붙는다

## DB

DB 인스턴스는 다른 서버와 같고, 계정과 스키마는 따로다. chat 서버는 `chat` 계정으로 `chat`
스키마(테스트는 `chat_test`)만 쓴다. 다른 서버의 스키마에 닿지 못하는 것을 테스트(`tests/test_schema_isolation.py`)가 확인한다.

테이블은 `app/conversations/models.py`(`characters`, `conversations`, `conversation_personas`, `messages`),
`app/catalog/models.py`(`ai_models`, `ai_model_costs`, `ai_model_snapshots`), `app/turns/models.py`(`generations`)에 있다.
모델 파일을 새로 만들면 `migrations/env.py` 와 `tests/cleaning.py` 에서 그 모듈을 불러온다.

### 마이그레이션

```powershell
cd chat-server
uv run alembic upgrade heads                          # 개발용 스키마에 적용
$env:DB_SCHEMA = 'chat_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA   # 테스트용 스키마에 적용
uv run alembic check                                  # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
uv run alembic revision --autogenerate -m "설명"       # 모델과 DB 를 비교해 새 마이그레이션 만들기
```

DB 주소와 스키마는 앱과 같은 설정(`.env`)에서 읽는다. `alembic.ini` 에는 적지 않는다.
어디까지 적용했는지 적는 표(`alembic_version`)도 스키마마다 따로 있다.

## 테스트

테스트는 실제 PostgreSQL 의 `chat_test` 스키마에서 돈다. `.env`의 `DATABASE_URL`을 그대로 쓴다.
테스트용 스키마에 마이그레이션을 먼저 적용한다(위의 "마이그레이션"). 테스트는 시작할 때마다 테이블을 비운다.

```powershell
cd chat-server
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

CI 는 `.github/workflows/chat-server.yml` 이다. 린트, 모양, 의존성 취약점, 마이그레이션(적용, 누락, 되돌리기), 테스트와 커버리지(95% 이상)를 본다.
관문(`ci.yml`, `changed-servers.sh`)이 이 워크플로를 부르게 하는 것은 인프라 쪽이 이 PR 에 얹는다.
