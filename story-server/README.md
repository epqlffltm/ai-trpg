# story 서버

하나의 세계관 안에서 여러 인물을 만나고, 장소를 옮기고, 이벤트를 겪고, 한 사람에게 고백해 엔딩을 보는 이야기를 맡는 서버다(#591).
규칙은 [story 서버 설계](../docs/architecture/story.md)에 있다. 캐릭터 하나와의 1:1 대화는 chat 서버가 맡는다.
둘이 함께 쓰는 것과 나눈 선은 [chat 서버 설계의 story-server 와 나눈 선](../docs/architecture/chat-server.md#story-server-와-나눈-선)에 있다.

<<<<<<< HEAD
**지금은 세션, 말 보내기, 행동, 다시 생성과 멈추기, 가지 고르기, 답 고치기, 이어서 출력, 계정의 기록, 기록 내려받기, 답의 신고, 요청 수 제한까지다(#591).** 공용 코드 `shared/server-core` 위에 설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증, Alembic 이 있고,
asset 서버에서 세계관의 판을 가져와 [세션](#세션)을 만들고 목록으로 보인다. 말을 보내면 장면의 인물들과 서술의 답을 [말 조각](#말-보내기)으로 흘려보낸다.
[행동](#행동)(이동, 시간, 선택지, 고백, 건네기)은 엔진이 판정하고 이벤트와 엔딩이 열린다. 답은 [다시 쓰고 멈출 수 있고](#다시-생성과-멈추기),
[대안의 가지를 고르고](#가지-고르기) [답을 고칠 수 있다](#답-고치기). 끊긴 답은 [이어 쓸 수 있다](#이어서-출력).
본 엔딩과 연 일러스트는 [계정의 기록](#계정의-기록)에 남고, 세션은 [파일로 내려받는다](#기록-내려받기). 사람마다 [요청 수](#요청-수-제한)를 센다.
=======
**지금은 세션, 말 보내기, 행동, 다시 생성과 멈추기, 가지 고르기, 답 고치기, 이어서 출력, 계정의 기록, 요청 수 제한까지다(#591).** 공용 코드 `shared/server-core` 위에 설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증, Alembic 이 있고,
asset 서버에서 세계관의 판을 가져와 [세션](#세션)을 만들고 목록으로 보인다. 말을 보내면 장면의 인물들과 서술의 답을 [말 조각](#말-보내기)으로 흘려보낸다.
[행동](#행동)(이동, 시간, 선택지, 고백, 건네기)은 엔진이 판정하고 이벤트와 엔딩이 열린다. 답은 [다시 쓰고 멈출 수 있고](#다시-생성과-멈추기),
[대안의 가지를 고르고](#가지-고르기) [답을 고칠 수 있다](#답-고치기). 끊긴 답은 [이어 쓸 수 있다](#이어서-출력).
본 엔딩과 연 일러스트는 [계정의 기록](#계정의-기록)에 남고, 사람마다 [요청 수](#요청-수-제한)를 센다.
>>>>>>> 0c3bc909 (ai patch)
말을 주고받는 조각은 여기까지다. 다음은 제작 도구(D7)다([만드는 순서](../docs/architecture/story.md#만드는-순서)).

정해 둔 값: 포트 `8007`, 토큰의 대상 `ai-trpg-story`, DB 계정과 스키마 `story`(테스트는 `story_test`), 주소 `/api/v1/story/`.

**대화의 핵심은 chat 과 함께 쓴다.** 대화 트리, 다시 생성과 분기, 요약, 기억, 스트리밍한 답을 저장하는 흐름은
chat 서버에서 옮긴 공용 코드 `shared/conversation-core` 를 두 서버가 함께 쓴다(이 서버는 말을 주고받는 조각부터). 표는 서버마다 따로 둔다(이 서버는 `story` 스키마).

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

로어북의 벡터(pgvector)를 쓰려면 story 계정이 `extensions` 스키마를 읽어야 한다(2026-10-28 에 스크립트에 더했다).
그 전에 만든 볼륨이라면 한 번 준다. 주지 않으면 마이그레이션(`lore_embeddings`)이 vector 타입을 찾지 못해 멈춘다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -c "GRANT USAGE ON SCHEMA extensions TO story;"
```

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

compose(`docker compose --profile app`)로 띄우면 같은 `story-server/.env` 를 쓰고 주소(DB, 인증 서버의 공개키, asset 서버)만 compose 가 덮어쓴다.
asset 서버의 주소를 주므로 `story-server/.env` 에 `ASSET_SECRET` 이 있어야 뜬다(`tools/fill_env.py` 가 채운다).
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
| `ASSET_URL` | 비어 있음(부르지 않음) | asset 서버의 주소(`http://127.0.0.1:8006`). 세션을 시작할 때 세계관의 판을 가져온다([세션](#세션)). 비우면 세션을 시작하지 못한다(503) |
| `ASSET_SECRET` | 비어 있음 | asset 서버에 보내는 요청에 서명하는 비밀. `asset-server/.env` 의 `STORY_SERVER_SECRET` 과 같은 값. `ASSET_URL` 을 적었으면 32자 이상이어야 뜬다. 비밀값이다 |
| `ASSET_TIMEOUT_SECONDS` | `5` | asset 서버를 한 번 부르는 시간의 상한(초, 30까지). 세션을 만드는 사람이 기다린다 |
| `BILLING_URL` | 비어 있음(받지 않음) | 결제 서버의 주소(`http://127.0.0.1:8003`). 모델의 값을 가격 목록에서 읽는다([모델 목록](#모델-목록)). 비우면 모델은 값 없이 보인다 |
| `AUTH_SERVER_SECRET` | 비어 있음 | 인증 서버가 [탈퇴](#탈퇴)를 알리는 요청의 서명 비밀. `auth-server/.env` 의 `STORY_SECRET` 과 같은 값. 적으면 32자 이상이어야 뜬다. 비우면 탈퇴 알림을 받지 않는다(401). 비밀값이다 |
| `NOTIFICATION_URL` | 비어 있음(보내지 않음) | [신고](#신고)의 처리를 넣는 알림 서버의 주소. compose 가 `http://notification-server:8004` 를 넘긴다. 비우면 발송함에 적기만 한다 |
| `NOTIFICATION_SECRET` | 비어 있음 | 알림 서버에 넣을 때 서명하는 비밀. `notification-server/.env` 의 `STORY_SERVER_SECRET` 과 같은 값. 주소를 적었으면 32자 이상이어야 뜬다. 비밀값이다 |
| `NOTIFICATION_TIMEOUT_SECONDS` | `5` | 알림 서버를 부를 때 기다리는 시간. 넘기면 다시 보낸다 |
| `BILLING_SECRET` | 비어 있음 | 결제 서버에 보내는 요청에 서명하는 비밀. `billing-server/.env` 의 `STORY_SERVER_SECRET` 과 같은 값. `BILLING_URL` 을 적었으면 32자 이상이어야 뜬다. 비밀값이다 |
| `BILLING_TIMEOUT_SECONDS` | `5` | 결제 서버를 한 번 부르는 시간의 상한(초, 10 까지). chat 서버와 같다 |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ZAI_API_KEY`, `DEEPINFRA_API_KEY` | 비어 있음 | 모델 목록의 창구마다 키. 비우면 그 창구의 모델로 말을 보내면 503 `provider_unavailable` 이다. 공급자가 내주는 값이라 `tools/fill_env.py` 가 만들지 않는다. 비밀값이다 |
| `LLM_TIMEOUT_SECONDS` | `120` | 모델을 한 번 부르는 시간의 상한(초, 600 까지) |
| `STORY_OUTPUT_LIMIT` | `1024` | 말 한 번의 답의 길이의 상한(토큰). 가격표의 출력 단계(`o0`)가 약속하는 길이다 |
| `STORY_CONTEXT_CHARS` | `12000` | 모델에 보내는 지난 말의 양의 상한(글자). 가격표의 입력 단계(`i0`)가 약속하는 양이다 |
| `STORY_SUGGESTIONS` | `true` | [다음 답 추천](#말-보내기). 켜면 답 끝에 선택지 셋을 함께 받는다. 호출은 늘지 않는다 |
| `EMBEDDER` | `off` | [로어북의 뜻으로 찾기](#말-보내기). `off` 면 상시와 키워드만, `llm` 이면 임베딩 모델을 부른다(`fake` 는 테스트용). chat, trpg-server 와 같은 이름이다 |
| `EMBEDDING_MODEL` | `bge-m3` | 임베딩 모델의 이름. 벡터에 함께 적는다(모델이 다르면 견주지 않는다) |
| `EMBEDDING_BASE_URL` | 비어 있음 | 임베딩 모델의 주소(OpenAI 와 같은 모양, `/embeddings` 앞까지). `EMBEDDER=llm` 이면 꼭 적는다 |
| `EMBEDDING_TIMEOUT_SECONDS` | `30` | 임베딩을 한 번 부르는 시간의 상한(초). 말 한 번의 찾기는 3초에 끊는다 |
| `EMBEDDING_DIMENSIONS` | 비어 있음 | 벡터의 길이. 적으면 받은 벡터가 이 길이인지 본다 |
| `SUMMARY_MODEL` | 비어 있음 | [굴리는 요약](#기억-메모)의 모델(모델 목록의 이름표). 비우면 요약하지 않는다 |
| `SUMMARY_AFTER_MESSAGES` | `8` | 창 밖으로 밀려난 말이 마지막 요약 뒤로 이만큼 쌓이면 요약한다(2~200) |
| `STORY_TEMPERATURE` | `0.9` | 글의 다양함(0~2). 받지 않는 모델에는 보내지 않는다 |
| `REDIS_URL` | 비어 있음(메모리) | [요청 수 제한](#요청-수-제한)을 세는 Redis(`redis://localhost:6379/3`). 비우면 서버 안의 메모리로 센다(서버가 하나일 때만 맞다). compose 는 DB 3 을 준다 |
| `GENERATION_LIMIT`, `GENERATION_WINDOW_SECONDS` | `20`, `60` | 모델을 부르는 요청(말, 행동, 다시 생성, 이어서)을 한 사람이 이 시간(초) 안에 이만큼까지 |
| `WRITE_LIMIT`, `WRITE_WINDOW_SECONDS` | `120`, `60` | 모델을 부르지 않는 쓰기(세션 시작과 지우기, 모델과 가지 바꾸기, 답 고치기, 신고)를 한 사람이 이 시간(초) 안에 이만큼까지 |
| `TRANSCRIPT_LIMIT`, `TRANSCRIPT_WINDOW_SECONDS` | `10`, `600` | [기록 내려받기](#기록-내려받기)를 한 사람이 이 시간(초) 안에 이만큼까지 |

DB 의 연결 풀(`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`)처럼 FastAPI 서버들이 함께 쓰는 칸은 공용 코드의 설정(`server_core.settings.CoreSettings`)에 있다.
`tools/fill_env.py` 가 `ASSET_SECRET` 과 `BILLING_SECRET` 을 짝(asset 서버, 결제 서버의 `STORY_SERVER_SECRET`)과 같은 값으로 채운다.
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
| GET | `/api/v1/story/models` | 세션에 고를 수 있는 [모델](#모델-목록)들과 말 한 번의 값(`{free, items}`). 켜져 있고 은퇴하지 않았고 결제 서버가 팔고 있는 것만. 회사, 이름표 순서. 가격 목록을 받지 못하면 503 `prices_unavailable` | access 토큰 |
| PUT | `/api/v1/story/conversations/{id}/persona` | 세션의 [페르소나](#세션) 바꾸기(`{"persona_id"}`, null 이면 없이). 같은 id 면 새 설정으로 바꾼다. `{persona}` 를 돌려준다. 없는 페르소나면 404 `persona_not_found`, asset 서버가 죽었으면 503 `asset_unavailable` | access 토큰 |
| PUT | `/api/v1/story/conversations/{id}/model` | 세션의 모델 바꾸기(`{"model"}`). 고를 수 없으면 422 `model_unavailable`, 가격 목록을 받지 못했으면 503 `prices_unavailable` | access 토큰 |
| POST | `/api/v1/story/conversations` | [세션](#세션) 시작(`{"world_id", "persona_id"?, "model"?}`). 세계관의 마지막 판과 페르소나를 가져와 고정한다. 201 | access 토큰 |
| GET | `/api/v1/story/conversations` | 내 세션의 목록(`?limit=&offset=&world_id=`). 최근의 것부터, `{items, total}`. 항목마다 지금 가지의 끝까지 온 곳(`progress`) | access 토큰 |
| GET | `/api/v1/story/conversations/{id}` | 세션 하나(지금 가지의 말과 말마다의 대안 `alternatives`, 그 끝의 상태 `state`, 화면이 쓰는 세계관의 칸 [`view`](#세션의-view), 가져온 페르소나 `persona`). 가져온 판의 문서는 싣지 않는다. 남의 것은 404 | access 토큰 |
| DELETE | `/api/v1/story/conversations/{id}` | [세션](#세션) 지우기. 204. 지운 시각만 적는다. 없거나 남의 것이면 404 | access 토큰 |
| PUT | `/api/v1/story/conversations/{id}/branch` | [가지 고르기](#가지-고르기)(`{"message_id"}`). 바뀐 세션을 돌려준다 | access 토큰 |
| POST | `/api/v1/story/messages/{id}/reports` | [모델의 답 신고](#신고). `{reason, description?}`. 201. 사람의 말과 행동 말은 422 `not_reportable`, 두 번째는 409 `already_reported` | access 토큰 |
| GET | `/api/v1/story/admin/message-reports` | 운영자: 열린 [신고](#신고)의 목록(`minor` 먼저, 오래된 것부터, 세션의 글은 없다). 운영자가 아니면 404 | access 토큰(운영자) |
| GET | `/api/v1/story/admin/message-reports/{id}?reason=` | 운영자: 신고 하나와 굳힌 글. 사유 필수, 볼 때마다 감사 기록. 없으면 404 `report_not_found` | access 토큰(운영자) |
| PUT | `/api/v1/story/admin/message-reports/{id}/outcome` | 운영자: 처리 `{outcome: actioned \| dismissed, reason}`. 204. 이미 처리했으면 409 `already_handled` | access 토큰(운영자) |
| PATCH | `/api/v1/story/messages/{id}` | [답 고치기](#답-고치기)(`{"segments": ["…"]}`). 고친 말을 돌려준다 | access 토큰 |
| POST | `/api/v1/story/conversations/{id}/messages` | [말 보내기](#말-보내기)(`{"content", "edit_of"?}`). 바로 SSE 로 장면의 인물들과 서술의 답을 흘려보낸다 | access 토큰 |
| POST | `/api/v1/story/conversations/{id}/actions` | [행동](#행동)(`{"kind", …}`). 엔진이 판정하고 바로 SSE 로 반응을 흘려보낸다 | access 토큰 |
| POST | `/api/v1/story/messages/{id}/regenerate` | [다시 생성](#다시-생성과-멈추기). 그 말에 다시 답한다. 바로 SSE 로 흘려보낸다 | access 토큰 |
| POST | `/api/v1/story/messages/{id}/continue` | [이어서 출력](#이어서-출력). 끊긴 답에 이어 쓴다. 바로 SSE 로 흘려보낸다 | access 토큰 |
| POST | `/api/v1/story/service/users/{public_id}/withdrawal` | [탈퇴](#탈퇴) 알림. 인증 서버만 부른다(프록시가 밖에서 받지 않는다) | 인증 서버의 서명 |
| POST | `/api/v1/story/generations/{id}/stop` | [멈추기](#다시-생성과-멈추기). 도는 답을 멈추고 받은 만큼 저장한다. 204, 멈출 것이 없으면 404 `generation_not_running` | access 토큰 |
| GET | `/api/v1/story/conversations/{id}/transcript` | [기록 내려받기](#기록-내려받기). `?format=md`(기본), `html`, `txt`. 지금 가지의 말들을 파일 하나로. 없거나 볼 수 없는 세션이면 404 | access 토큰 |
| GET | `/api/v1/story/endings` | 그 세계관에서 내가 본 엔딩들(`?world_id=`, 처음 본 차례). [계정의 기록](#계정의-기록) | access 토큰 |
| GET | `/api/v1/story/conversations/{id}/notes` | [기억 메모](#기억-메모)들(먼저 쓴 것부터) | access 토큰 |
| POST | `/api/v1/story/conversations/{id}/notes` | 기억 메모 더하기(`{"text"}`, 300자). 201. 가득 차면(20개) 409 `notes_full` | access 토큰 |
| PATCH | `/api/v1/story/conversations/{id}/notes/{note_id}` | 기억 메모 고치기(`{"text"}`). 없으면 404 `note_not_found` | access 토큰 |
| POST | `/api/v1/story/conversations/{id}/notes/{note_id}/accept` | 요약이 제안한 메모를 받아들이기. 다음 말부터 모델에 간다. 가득 차면 409 `notes_full` | access 토큰 |
| DELETE | `/api/v1/story/conversations/{id}/notes/{note_id}` | 기억 메모 지우기(제안을 버리는 것도 이것). 204 | access 토큰 |
| GET | `/api/v1/story/conversations/{id}/summary` | 지금 가지의 [굴리는 요약](#기억-메모)(`{text, covered_up_to, created_at}`, 읽기만). 없으면 null | access 토큰 |
| GET | `/api/v1/story/gallery` | 그 세계관에서 내가 연 일러스트들(`?world_id=`, 처음 연 차례). [계정의 기록](#계정의-기록) | access 토큰 |

### 세션

세계관 하나를 새로 시작하면 새 세션이 생긴다(`story.conversations` 의 행). 지난 세션은 목록에 남는다.
주소와 표의 이름은 chat 과 같은 `conversations` 이고, 화면과 문서는 "세션"이라 부른다.

1. asset 서버에서 그 세계관의 **마지막 판**을 가져온다(`GET /api/v1/asset/service/story/worlds/{id}/latest`).
   이 서버의 비밀(`ASSET_SECRET`)로 서명하고 사용자의 토큰을 그대로 넘긴다. 쓸 수 있는 사람인지는 asset 서버가 판단한다
   (주인이거나, 공개이고 판의 등급을 볼 수 있는 사람). DB 의 트랜잭션을 열기 전에, 연결을 쥐지 않은 채로 부른다.
2. 가져온 판의 등급을 이 서버의 규칙(`app/ratings.py`)으로 한 번 더 본다.
3. 판의 사본(`story.worlds`)과 세션을 한 트랜잭션에서 저장한다. 사본은 사람마다, 판마다 하나다. 같은 판으로 여러 번 시작해도 하나다.

- **페르소나**(chat 과 같다, 2026-10-27). `persona_id` 를 보내면 그 계정 페르소나를 asset 서버에서 가져와(`GET /api/v1/asset/service/story/personas/{id}`)
  세션에 복사한다(`story.conversation_personas`). 보내지 않으면 지난번 세션의 것이고(지워졌으면 없이), `null` 이면 없이 시작한다.
  고른 것이 없거나 남의 것이면 404 `persona_not_found` 다. 세션 읽기의 `persona` 에 실리고, 카드의 `[사용자]`(이름, 인물들이 부르는 호칭, 나이, 성별, 설명, 성격, 말투의 예)로 모델에 간다.
  복사해 두므로 asset 서버에서 고쳐도 그 세션은 그대로다.
- **페르소나 바꾸기**(2026-10-27). `PUT /conversations/{id}/persona` 가 다음 말부터 쓸 페르소나를 바꾼다(지금 도는 답은 그대로).
  같은 id 를 보내면 asset 서버의 지금 것을 다시 가져온다("새 설정으로 바꾸기"). 화면은 내 페르소나 목록의 `revision` 과 세션의 `persona.revision` 을 견줘 바뀐 것을 안다.
  `null` 이면 없이 이어 간다. 세션을 먼저 확인하고 asset 서버를 부른 뒤 사본을 한 문장(upsert)으로 바꾼다. 가지와 상관없이 세션에 하나다.

- **사본은 바뀌지 않는다.** 제작자가 다시 게시해도 그 세션은 처음의 판으로 돈다. 새 판은 새로 시작한 세션이 쓴다.
- **판의 문서는 받은 그대로 둔다.** 지금 검사하는 칸은 형식, 이름, 등급, 그림뿐이고(`app/assets/schemas.py`),
  나머지(시간대, 지도, 물건, 인물, 이벤트, 엔딩)는 그 칸을 쓰는 조각이 읽는 모양을 더한다.
- **모르는 형식의 판은 받지 않는다.** 이 서버가 읽을 줄 아는 형식은 4 까지다(`WORLD_FORMAT_MAX`). 모르는 조건이나 효과를 엔진이 판정할 수 없어서다.
  asset 서버가 형식을 올리면 그것을 읽는 법과 함께 이 값을 올린다.
- **장르**(판의 형식 4). 세션의 `world.genre` 에 판의 장르를 싣는다(목록과 읽기). 화면이 장면(D2)의 테마를 고른다. 형식 3 까지의 판이거나 고르지 않았으면 `null` 이다.
  값의 목록은 asset 서버(`asset-server/app/genres.py`)가 지킨다. 이 서버는 글자인지만 보고 그대로 싣는다. 규칙이 아니라 화면의 일이라 엔진은 보지 않는다.
- **목록과 읽기는 볼 수 있는 등급만이다.** 성인 확인을 잃으면 성인 등급의 세션은 목록에서 빠지고 읽으면 404 다.
- **목록의 진행**(`progress`). 지금 가지의 끝의 며칠째(`day`), 시간대(`slot`), 판의 기한(`deadline_days`), 본 엔딩의 id 와 이름(`ending`, `ending_name`),
  후일담인가(`epilogue`, 엔딩을 봤고 세계관이 후일담을 골랐다)다. 화면이 D1 의 "D-12 / 진행 / 끝(엔딩 이름) / 후일담"을 그린다.
  상태는 말에 붙어 있어 가지를 바꾸거나 다시 생성하면 저장 없이 바뀐다. 그래서 세션 표에 적어 두지 않고 목록을 읽을 때 세션마다 센다
  (세션마다 쿼리 둘, 한 쪽은 `limit` 개까지). 느려지면 세션 표에 요약을 두는 방식으로 바꾼다(2026-10-27).
- **지우기**(chat 과 같다). 지운 시각(`deleted_at`)만 적는다. 말, 상태, 판의 사본은 남는다. 지운 세션은 목록과 읽기에 나오지 않고,
  말과 행동을 보내면 404 다. 요약도 하지 않는다. "지난번에 고른 모델과 페르소나"는 지운 세션도 센다. 계정의 기록(본 엔딩, 연 일러스트)은 그대로다.
  행을 지우는 것은 [탈퇴](#탈퇴)뿐이다. 답을 쓰는 중에 지워도 그 답은 끝까지 저장되고 청구된다.

| asset 서버의 답 | 이 서버의 답 |
| --- | --- |
| 404(없다, 남의 비공개, 게시한 적이 없다, 볼 수 없는 등급) | 404 `world_not_found`. 가져온 판이 볼 수 없는 등급일 때도 같다 |
| 403 `adult_content_required`(자기 세계관인데 등급을 쓸 수 없다) | 403 `adult_content_required`. 화면이 본인인증으로 안내한다 |
| 닿지 못함, 시간 초과, 401, 5xx, 모양이 틀린 답, 모르는 형식, `ASSET_URL` 이 없음 | 503 `asset_unavailable`, `Retry-After: 5`. 다시 시도하지 않는다(사람이 다시 누른다) |

### 세션의 view

세션 읽기의 `view` 는 판의 문서에서 지금 보여도 되는 것만 골라 이 가지의 상태에 맞춘 것이다(`app/conversations/views.py`).
판의 문서에는 이벤트와 엔딩의 조건, 인물의 일정과 호감도 규칙, 만나지 않은 인물, 못 본 엔딩의 이름이 들어 있다.
화면이 장면(D2), 지도(D3), 소지품(D4), 인물 창(D5), 엔딩(D6)을 그릴 때 이것을 쓴다.

- **만남.** 이 가지의 답의 장면에 한 번이라도 들어온 인물이다. 엔진이 정한 장면의 인물이라 모델이 바꾸지 못한다.
  상태에 따로 적지 않고 답마다 저장된 장면의 인물(`messages.cast`)을 모은다. 그래서 지난 세션에도 맞다(2026-10-27).
- **인물**(`cast`). 만났으면 보임이다. 만나기 전에는 제작자가 고른 공개를 따른다. 실루엣은 이름, 그림, 인물 창이 비고(null), 숨김은 목록에 없다.
  인물 창의 소개, 나이, 성별, 호감도는 제작자가 고른 항목만 실린다. 호감도에는 단계와 보이는 법, 고백 대기가 끝나는 시각(`cooling_until`), 건넨 물건(`gifts`)이 있다.
  고백 대기, 건넨 선물, 함께 본 이벤트(`events`)는 호감도를 보이는 인물에만 싣는다(판에 그 셋을 따로 고르는 칸이 아직 없다).
- **이벤트**(`events`). 이 가지에서 열린 것의 이름, 장면의 인물, 일러스트다. 선택지의 글은 고르기를 기다리는 이벤트에만 싣는다. 조건과 효과는 없다.
- **엔딩**(`endings`). 칸은 모두 보인다. 이름과 일러스트는 본 것(계정의 기록이나 이 가지에서 본 것)만이고, 힌트는 늘 싣는다. `unlock` 이 거짓이면 계정에 남지 않는 엔딩이다.
- **지도**(`map`). 장소마다 가 본 곳인가(`visited`)와 지금 거기 보이는 인물(`cast`)이다. 장소의 차례는 `places` 와 같다.
  가 본 곳은 시작 장소와 가지의 말마다 붙은 상태의 장소, 지금 장소다. 상태에 따로 적지 않아 지난 세션에도 맞다.
  인물의 자리는 엔진이 정한다(동행, 일정, 기본 장소). 가 본 곳에 있고, 만났고, 제작자의 지도 보이기(보임, 숨김, 호감도 단계 이상)를 통과한 인물만 보인다.
  함께 다니는 인물은 장소에 넣지 않는다(`state.companions` 로 내 자리 옆에 보인다).
- 그 밖에 이름, 소개, 태그, 대표 그림, 기한, 엔딩 뒤, 시간대, 장소(배경 그림), 길, 물건이다.
- **판의 문서는 싣지 않는다**(2026-10-27). 세션의 `world` 는 목록과 같은 요약(id, 판, 이름, 그림, 등급)이다.
  상태의 호감도(`state.affection`)도 인물 창에 호감도가 실리는 인물만 싣는다. 말의 `turn` 프레임의 상태도 같다(이번 답의 장면의 인물은 만난 것으로 친다).

### 말 보내기

`POST /api/v1/story/conversations/{id}/messages` 가 바로 SSE(`text/event-stream`)로 답한다(`app/turns/`).
chat 의 한 번의 말과 같은 차례다: 차례를 잡고(한 세션 한 생성), 사람의 말과 기록(`generations`)을 저장하고, 홀드를 걸고,
모델을 부르며 흘려보내고, 답을 저장하고, 확정한다. 응답에 `X-Accel-Buffering: no` 를 싣고 15초마다 하트비트를 보낸다.
끊겨도 서버는 생성을 끝까지 저장하고, 앱은 다시 들어와 저장된 말을 읽는다. 이 주소는 공용 코드의 `StreamRoutes` 로 span 과 요청 메트릭에서 뺀다.

```
event: turn     data: {"generation_id", "user_message", "cast": ["mina"]}   답할 사람의 말과 장면의 인물
event: segment  data: {"speaker": "mina", "expression": "웃음"}             새 말 조각(서술은 null). 그 줄의 표정(기본이면 null)
event: delta    data: {"text": "..."}                                        지금 조각에 붙는 글
event: done     data: {"message": {... "segments": [{"speaker", "text", "expression"}], "cast", "suggestions"}}   저장한 답
event: failed   data: {"code": "timeout"}                                    답 없이 끝났다
```

- **로어북**(2026-10-28, chat 의 키워드 고르기와 같다, `conversation_core/lorebook.py`). 세계관의 판에 복사된 로어북의 항목 가운데
  상시 항목과, 최근 말 넷(이번 말 포함)에 키워드가 나온 항목을 카드의 `[로어북]`(장면의 인물 뒤)에 넣는다. 8개, 2000자까지다.
- **로어북의 뜻으로 찾기**(2026-10-28, chat 의 `app/lore` 와 같다, `app/lore/`). `EMBEDDER` 가 켜져 있으면 모델을 부르기 직전에
  최근 말 둘을 벡터로 바꿔, 그 판의 사본의 항목 벡터와 코사인 거리 0.45 안에서 가까운 것 셋까지를 키워드로 고른 것 뒤에 더한다.
  3초 안에 끝나지 않거나 실패하면 상시와 키워드만으로 답한다(로그 `story.lore_recall`).
  항목의 벡터(`lore_embeddings`)는 세션을 시작할 때 따로 도는 작업이 만든다. 찾을 때 모자라도 만들기를 맡긴다(로그 `story.lore_index`).
  사본마다 만들어 사본을 지우면 함께 지워진다. 로어북의 id 가 없는 판의 항목은 카드에는 들어가고 벡터만 만들지 않는다.
- **장면의 인물.** 가지의 끝의 상태로 엔진이 정한다(`app/engine/scene.py`). 장면 밖의 인물은 프롬프트에 넣지 않는다.
  선택지를 기다리는 동안 말을 하면 선택지는 사라진다(효과 없이). 그 상태를 사람의 말에 붙인다.
- **말 조각.** 모델은 줄마다 `@인물의 id:` 나 `@narration:` 을 적는다(`app/turns/segments.py`). 서버는 흘러오는 대로 잘라 말하는 사람을 본다.
  장면에 없는 인물의 줄은 흘리지 않고 저장하지 않으며 기록에 센다(`generations.dropped_segments`). 표식을 어긴 줄은 서술이다.
  남은 조각이 없으면 실패한 말이고 청구하지 않는다(`failed`, `empty`).
- **표정**(2026-10-27). 그림에 표정이 있는 인물이 장면에 있으면 카드의 쓰는 법에 고를 수 있는 표정을 적는다.
  모델은 그 인물의 줄에서 표식 뒤에 `<expression>웃음</expression>` 을 먼저 쓸 수 있다(chat 의 표정 표식을 줄마다 쓴다, `conversation_core/expressions.py`).
  서버는 표식을 떼어 흘리지 않고, 그 조각의 `expression` 으로 `segment` 메시지와 저장한 조각에 싣는다. 화면은 `view.cast[].sprites` 에서 그 표정의 그림을 고른다.
  그 인물의 그림에 없는 이름이나 "기본", 서술, 표정이 없는 인물은 `null` 이다. 표정은 본문(`content`)에 넣지 않는다. 답을 고쳐도 그대로다.
- **저장.** 답의 `segments` 가 기준이고, `content` 는 그 조각을 표식이 붙은 줄로 쓴 것이다(다음 호출의 프롬프트에 그대로 간다).
  답에는 그때의 장면의 인물(`cast`)을 함께 적는다. 상태는 행동 말(과 선택지를 지운 말)에 붙는다(`message_states`).
- **다음 답 추천**(chat 과 같다, `conversation_core/suggestions.py`). 카드 끝에 지시를 붙이면 모델이 본문 뒤에 `<suggestions>` 와 선택지를 쓴다.
  표식 뒤는 흘리지 않고 말 조각에도 넣지 않는다(`MarkerHold`, 표식이 조각의 경계에 걸려도). 다 쓴 답에서만 걸러(셋까지, 번호와 따옴표를 떼고, 같은 것은 하나)
  답의 `suggestions` 에 둔다. 다음 호출에는 본문만 간다. 끊긴 답에는 없고, 이어서 출력으로 다 쓰면 붙는다. 답을 고치면 지운다.
- **끝난 세션.** 엔딩을 봤고 세계관이 끝(읽기만)을 골랐으면 409 `session_ended` 다. 후일담이면 말을 받는다.
- **내 말 고치기.** `edit_of` 에 고칠 사람의 말의 id 를 실으면 새 말이 그 말의 대안(같은 부모 아래, 새 가지)이 되고 원본은 남는다(chat 과 같다).
  상태, 끝난 세션인지, 모델에 보낼 말들은 그 말의 앞까지의 가지의 것이다. 그래서 끝난 세션이어도 엔딩 앞의 말은 고칠 수 있다.
  답과 행동 말은 422 `not_editable`(답은 [답 고치기](#답-고치기)로, 행동은 엔진의 결과라 고치지 않는다), 그 세션의 말이 아니면 404 `message_not_found` 다.
- **거절.** 모델이 없으면 409 `model_required`, 쓸 수 없으면 422 `model_unavailable`, 답을 쓰는 중이면 409 `generation_in_progress`.
  크레딧이 모자라면 402 `credit_short`, 결제 서버나 공급자가 죽었으면 503 이다. 이때 사람의 말은 저장되고 `message_id` 로 알린다.
- **청구.** 결제 서버의 가격표 `story.<이름표>.i0.o0` 로 홀드를 건다(`story:gen:<기록의 id>`). 답이 있으면 확정, 없으면 반환이다.
  못 한 것은 청구 정리(`app/turns/settler.py`, 5초마다)가 마저 한다. 도중에 꺼진 서버가 남긴 홀드도 15분 뒤에 돌려준다.
- 끊긴 답은 [이어서 출력](#이어서-출력)으로 이어 쓴다. 한 사람이 몰아 보내면 429 다([요청 수 제한](#요청-수-제한)).

### 행동

`POST /api/v1/story/conversations/{id}/actions` 가 바로 SSE 로 답한다(말 보내기와 같은 모양). 행동은 여섯이다.

| `kind` | 칸 | 하는 일 |
| --- | --- | --- |
| `move` | `place` | 지금 장소와 길로 바로 이어진 장소로 옮긴다. 길의 시간만큼 시각이 흐른다 |
| `pass_time` | | 다음 시간대로 |
| `end_day` | | 다음 날의 첫 시간대로 |
| `choose` | `choice` | 기다리는 이벤트의 선택지 하나를 고른다. 그 효과가 든다 |
| `confess` | `cast` | 장면에 있는 인물 하나에게 고백한다. 성공과 실패는 엔진이 정한다 |
| `give` | `cast`, `item` | 장면에 있는 인물 하나에게 가진 물건 하나를 건넨다. 호감도가 얼마나 바뀌는지는 엔진이 정한다 |

- **판정은 엔진이 한다**(`app/engine/play.py`). 기다리던 선택지를 지우고(고르는 것이 아니면), 행동을 반영하고,
  시각이 흐른 행동이면 기한을 보고, 열 수 있는 이벤트를 하나 연다. 고백이나 기한이나 이벤트로 엔딩을 볼 수 있다.
  모델은 결과를 바꾸지 못한다. 행동 말의 글(`[행동]` 을 붙여 모델에 간다)에 엔진이 정한 결과(고백을 받아들였는가, 선물을 반가워했는가)가 적힌다.
- **답의 장면.** 엔딩을 봤으면 그 엔딩의 장면, 이벤트가 열렸으면 그 이벤트의 장면 지시를 카드에 넣고 그 장면이 부른 인물이 들어온다(`app/turns/scenes.py`).
- **저장.** 행동 말에 그 뒤의 상태와, 열린 이벤트(`event_id`)와 본 엔딩(`ending_id`)을 적는다. turn 메시지의 `state` 가 그 뒤의 상태다.
  행동에도 모델이 답하므로 한 번 청구한다.
- **계정의 기록.** 엔딩을 보거나 해금 대상인 장면이 열리면 [계정의 기록](#계정의-기록)에 적는다.
  끝을 고른 세계관이면 엔딩 뒤로 말과 행동을 받지 않는다(409 `session_ended`). 후일담이면 받는다.
- **거절.** 할 수 없는 행동이면 422 이고 아무것도 저장하지 않는다. `code` 는 `cannot_move`(이어지지 않은 장소, 지금 장소),
  `no_choice`(기다리는 선택지가 없다, 그런 선택지가 없다), `over`, `not_in_scene`, `not_confessable`, `cooling_down`(고백을 받지 않는다),
  `not_held`(건넬 물건이 없다)다. 장면에 없는 인물에게 건네면 `not_in_scene` 이다.
- **건네기**(`app/engine/gifts.py`). 물건이 하나 줄고, 건넨 적이 있는 (인물, 물건)에 넣는다(조건 `gave_item` 이 본다).
  그 인물의 선물 규칙(판의 `affection.gifts`) 가운데 그 물건의 것들을 판의 차례대로 더한다. 더할 때마다 0~100 으로 자른다(chat 과 같다).
  `once` 인 규칙은 그 인물에게 그 물건을 처음 건넬 때만 든다. 맞는 규칙이 없으면 물건만 건네진다.
  행동 말에는 호감도가 오르면 "반가워했다", 내리면 "달가워하지 않았다"가 적힌다(얼마나는 적지 않는다). 시각은 흐르지 않고, 후일담에도 된다.

### 다시 생성과 멈추기

chat 의 것과 같은 모양이다(`app/turns/service.py` 의 `begin_regenerate`, `app/turns/stops.py`).

- **다시 생성.** `POST /api/v1/story/messages/{id}/regenerate` 가 바로 SSE 로 답한다(말 보내기와 같은 모양).
  답이면 그 부모(사람의 말이나 행동 말)에 새 대안을 쓰고, 답을 못 받은 사람의 말이나 행동 말이면 그 말에 답한다.
  새 호출이라 새로 청구한다. 앞의 답은 남고, 새 답을 저장할 때 가지의 끝이 새 답으로 옮겨 간다. 거절되거나 조각 없이 실패하면 앞의 답이 그대로다.
- **엔진은 다시 판정하지 않는다.** 사람의 말도 상태도 새로 저장하지 않는다. 상태는 그 말까지의 가지의 것이고,
  답의 장면은 그 말에 적힌 이벤트와 엔딩(`event_id`, `ending_id`)으로 다시 세운다(`app/turns/scenes.py` 의 `replayed`).
  그래서 이벤트가 다시 열리지 않고, 엔딩을 다시 보지 않는다(기록도 그대로다).
- **끝난 세션에서도 된다.** 사람의 말이 늘지 않아서다. 엔딩의 장면을 다시 쓸 수 있다.
  앞의 말을 다시 쓰면 가지가 그 자리로 옮겨 가서 그 가지의 상태(엔딩 전)로 이어 갈 수 있다. 세션 안의 트리는 가지마다 상태를 갖는다는 설계 그대로다.
- **거절.** 말이 없거나 남의 것이면 404 `message_not_found`, 부모가 없는 답이면 422 `not_regenerable`, 답을 쓰는 중이면 409 `generation_in_progress`.
  모델과 청구의 거절은 말 보내기와 같다.
- **멈추기.** `POST /api/v1/story/generations/{id}/stop`. `id` 는 SSE 의 turn 의 `generation_id` 다. 모델을 부르는 일만 끊는다.
  받은 조각이 있으면 partial 로 저장하고 확정한다(`error_code` `stopped`). 없으면 반환하고 SSE 는 `failed`(`stopped`)로 끝난다.
  스위치는 그 생성을 돌리는 서버의 메모리에 있다(`app.state.stops`). 끝난 것, 남의 것, 다른 서버에서 도는 것은 404 `generation_not_running` 이다.
- 다시 생성은 모델을 부르는 요청으로 센다. 멈추기는 세지 않는다([요청 수 제한](#요청-수-제한)).

### 이어서 출력

`POST /api/v1/story/messages/{id}/continue` 가 길이 상한이나 멈추기로 끊긴 답(`partial`)에 이어 쓴다(`app/turns/service.py` 의 `begin_continue`).
chat 의 이어서 출력과 같은 차례이고, 새 호출이라 새로 청구한다. 지금 가지의 끝인 끊긴 답만 된다.

- **모델에 가는 것.** 끊긴 답까지의 말(끊긴 답은 표식이 붙은 줄 그대로)과, 맨 끝에 사람의 차례로 이어 쓰라는 지시
  (`conversation_core.continuation`)다. 장면의 인물은 끊긴 답에 적힌 것(`cast`) 그대로이고, 장면 지시는 답한 말에 적힌 이벤트와 엔딩으로 다시 세운다.
  엔진은 다시 판정하지 않는다. 끝난 세션이어도 된다(사람의 말이 늘지 않는다).
- **조각 잇기**(`app/turns/segments.py` 의 `continuing_splitter`). 첫 줄에 표식이 없으면 끊긴 마지막 조각을 이어 쓴 것이라 그 조각의 글 끝에 붙인다.
  첫 줄이 표식으로 시작하면 새 조각이다. 그 뒤의 줄은 말 보내기와 같다(장면 밖의 인물의 줄은 버린다).
  모델이 끊긴 답의 끝을 되풀이하면 겹친 만큼 뗀다(`OverlapTrim`, 8 글자 이상 겹칠 때).
- **SSE.** turn 에 `continues`(그 답의 id)가 실린다. 첫 `segment` 앞의 `delta` 는 그 답의 마지막 조각에 붙는 글이고, `segment` 가 오면 새 조각이다.
  `done` 의 말은 이어 붙인 그 답 전체다(같은 id).
- **저장.** 새 말을 만들지 않고 끊긴 답의 조각과 본문을 바꾼다. 다 쓰면 `complete`(다음 답 추천이 붙는다), 또 끊기면 `partial` 이라 다시 이어 쓸 수 있다.
  이어 쓴 것이 없으면 끊긴 답은 그대로이고 청구를 돌려준다.
- **거절.** 끊긴 답이 아니거나 가지의 끝이 아니면 422 `not_continuable`, 없거나 남의 말이면 404 `message_not_found`, 답을 쓰는 중이면 409 다.

### 가지 고르기

chat 의 것과 같은 모양이다(`app/conversations/` 의 `message_alternatives`, `choose_branch`).

- **대안.** 세션 읽기의 말마다 `alternatives` 가 실린다. 같은 부모 아래의 말들의 id 이고, 먼저 생긴 것부터이며 그 말도 든다.
  대안이 없는 말은 그 말 하나다. 화면이 "< 2/3 >" 를 그린다.
- **고르기.** `PUT /api/v1/story/conversations/{id}/branch` 에 대안 하나의 `message_id` 를 보낸다.
  그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 되고, 바뀐 세션을 돌려준다.
  상태는 말에 붙어 있으므로 그 가지의 상태(시각, 호감도, 본 엔딩)가 된다. 계정의 기록은 그대로다.
- 보는 곳만 바꾸므로 세션의 수정 시각(목록의 차례)은 그대로다.
- **거절.** 그 세션의 말이 아니거나 없는 말이면 404 `message_not_found`, 답을 쓰는 중이면 409 `generation_in_progress`, 남의 세션이면 404 다.

### 답 고치기

`PATCH /api/v1/story/messages/{id}` 가 모델의 답을 그 자리에서 고친다(`app/conversations/service.py` 의 `edit_message`). 청구하지 않는다.

- **조각마다 글만 고친다**(2026-10-26). `{"segments": ["노을이 졌다.", "기다렸어."]}` 처럼 조각의 글을 차례대로 보낸다.
  말하는 사람과 조각의 수는 저장된 그대로라서 장면 밖의 인물이 끼어들 길이 없다. 표식을 다시 읽지 않는다.
- 조각의 글은 한 줄이다(조각은 줄 하나다). 줄바꿈이나 빈 글은 입력 오류다. 앞뒤 빈칸은 걷는다.
- 본문(`content`)은 고친 조각으로 서버가 다시 쓴다. 다음 호출부터 고친 글이 모델에 간다. 고친 말에는 `edited` 가 붙는다.
  다음 답 추천은 고치기 전의 글에 맞춘 것이라 지운다.
- 상태와 세션의 수정 시각(목록의 차례)은 그대로다. 사람의 말은 말 보내기의 `edit_of` 로 새 가지를 만들어 고치고, 행동 말은 고치지 않는다(엔진의 결과다).
- **거절.** 답이 아니면 422 `not_editable`, 조각의 수가 다르면 422 `segments_mismatch`, 없거나 남의 말이면 404 `message_not_found`,
  답을 쓰는 중이면 409 `generation_in_progress` 다.

### 계정의 기록

세션을 지우거나 가지를 바꿔도 남는다(`app/records/`). 처음 본 세션(`conversation_id`)은 그 세션이 지워지면 비운다.

- **본 엔딩**(`ending_records`). 행동으로 엔딩을 봤고 그 엔딩이 기록에 남는 것이면(`unlock`) 적는다.
  사람마다, 세계관마다, 엔딩마다 처음 본 것 하나다. 엔딩 목록 화면(D6)이 `GET /endings` 로 읽는다.
- **연 일러스트**(`illustration_unlocks`). 행동 뒤에 열린 이벤트와 본 엔딩의 장면 가운데, 해금 대상(`collectible`)이고 그림(`image_id`)이 있는 것을 적는다
  (`app/records/illustrations.py`). 후일담에서 열린 장면도 적는다. 다시 생성은 장면을 다시 열지 않으므로 적지 않는다.
  사람마다, 세계관마다, 장면(`kind` 는 `event` 나 `ending`, `scene_id`)마다 처음 연 것 하나다. 연 때의 그림과 그 장면이 부르는 인물들(`cast`)을 함께 적는다.
  갤러리의 story 탭(C7)이 `GET /gallery` 로 읽어 인물마다 묶고, 인물이 없는 장면은 세계관 칸에 둔다.
- **키를 장면으로 둔 까닭**(2026-10-26). 일러스트는 인물이 아니라 이벤트와 엔딩의 장면에 붙어 있다. 한 장면에 인물이 0~4 명이라 인물 하나로 가리킬 수 없다.
  연 때의 그림을 적는 것은 제작자가 새 판에서 그림을 바꿔도 연 그림을 보이기 위해서다.

### 기억 메모

세션마다 사람이 쓰는 짧은 글이다(chat 의 기억 메모와 같다, `app/memory/`). 다음 말부터 카드의 `[기억]`(사용자 뒤, 지금 앞)으로 늘 모델에 간다.

- 하나에 300자, 세션 하나에 20개까지다. 늘 가는 글이라 입력의 양을 지킨다. 더할 때 세션을 잠그고 센다(동시에 더해도 넘지 않는다).
- 가지와 상관없이 세션에 하나의 목록이다. 답을 쓰는 중에도 고칠 수 있고 다음 말부터 들어간다. 모델을 부르지 않아 청구하지 않는다.
- 남의 세션은 404, 그 세션에 없는 메모는 404 `note_not_found`, 가득 차면 409 `notes_full`, 빈 글과 긴 글은 422 다. 쓰기는 요청 수 제한의 쓰기로 센다.
- **굴리는 요약**(2026-10-28, chat 과 같다, `app/memory/summaries.py`, `summarizer.py`). 말 한 번이 끝나면 따로 돌아,
  지난 말의 창(`STORY_CONTEXT_CHARS`) 밖으로 밀려난 말이 마지막 요약 뒤로 `SUMMARY_AFTER_MESSAGES` 개 쌓였으면 앞의 요약과 합쳐 새 요약을 쓴다.
  요약은 밀려난 마지막 말에 붙어(`summaries`) 어느 가지에서 읽어도 맞다. 다음 말부터 카드의 `[앞의 줄거리]`(사용자 뒤, 기억 앞)로 간다.
  싼 모델(`SUMMARY_MODEL`, 꺼 둔 모델도 된다)로 부르고 원가는 서비스가 낸다(청구하지 않고 행에 적는다). 비우면 요약하지 않는다.
  실패해도 이야기는 이어진다(로그 `story.summary`). 사람은 기다리지 않는다.
- **요약이 제안하는 메모**(2026-10-29, chat 의 #677 과 같다). 요약을 쓰는 같은 호출에서 줄거리 뒤에 `<notes>` 와 오래 기억할 사실을 셋까지 받는다.
  이미 적힌 메모(제안까지)를 보여 주어 되풀이하지 않게 하고, 받은 뒤에도 같은 것, 빈 것, 긴 것은 거른다. 잘린 요약은 제안하지 않는다.
  제안은 `source: summary`, `pending: true` 로 메모 목록에 보이고, 받아들이기(`accept`) 전에는 모델에 가지 않고 20개의 수에도 들지 않는다.
  기다리는 제안은 세션마다 10개까지 쌓인다. 버리기는 지우기다.

### 기록 내려받기

내 세션을 파일 하나로 받는다(#617 의 story 몫, `app/transcripts/`). chat 의 기록 내려받기와 같은 세 형식이다.

| 형식 | `format` | 모양 |
| --- | --- | --- |
| 마크다운 | `md`(기본) | 구분은 `##`, 서술은 문단, 말은 인용(`> **이름**`), 한 줄의 일은 목록. 글 맨 앞의 `#` 은 글자로 남긴다 |
| HTML | `html` | 파일 하나로 열린다. 밖의 자원과 스크립트가 없고, 글은 모두 바꿔 쓴다(escape). 머리의 CSP 가 한 번 더 막는다 |
| 텍스트 | `txt` | 표시 문법이 없다. 말은 `이름:` 아래에 들여 쓴다 |

- **넣는 것.** 지금 보고 있는 가지의 말(첫 말부터), 행동(서버가 쓴 글 그대로, 시각과 장소가 들어 있다), 그 행동 뒤에 열린 이벤트와 본 엔딩의 이름, 끊긴 답과 고친 답의 표시. 모두 세션 화면에서 본 것이다.
- **넣지 않는 것.** 다른 가지(대안), 다음 답 추천, 이벤트의 선택지(고른 것은 행동 말로 남는다), 표정, 기억 메모와 요약, 모델에게만 가는 글(세계관의 소개, 인물의 설정, 로어북, 이벤트의 장면 지시). 다른 가지를 받으려면 그 가지를 보고(`PUT .../branch`) 다시 받는다.
- 답은 말 조각마다 적는다. 서술은 이름이 없는 문단이고, 인물의 말은 세션에 가져온 판의 이름이다. 같은 사람이 이어 말한 조각은 하나로 묶는다(화면과 같다).
  사람의 말은 페르소나의 이름(없으면 "나")이다.
- 세션 읽기와 같은 규칙으로 찾는다. 남의 세션, 지운 세션, 볼 수 없는 등급이면 404 다.
- 파일의 이름은 세션의 제목이다(`Content-Disposition` 의 `filename*`). `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` 를 붙인다.
- 한 사람이 10분에 10번까지다([요청 수 제한](#요청-수-제한)). 없는 세션의 요청도 센다.

### 신고

자기 세션의 모델의 답을 신고한다(chat 의 #678 과 같은 모양, `app/reports/`, `app/operators/`).

- **굳히기.** 세션은 그 사람만 보는 것이라 운영자가 읽지 않는다. 그래서 신고하는 순간 그 답과 앞의 말 여섯(그 답까지의 가지의 것),
  세계관(asset 의 id, 판, 이름)과 모델을 신고에 굳힌다. 답의 글은 저장한 본문 그대로다(줄마다 `@mina:` 같은 말하는 사람의 표식).
  그 뒤에 답을 고치거나 가지를 바꿔도 운영자가 보는 글은 신고한 때의 것이다.
- **규칙.** 사유는 asset 의 신고와 같다(`spam`, `abuse`, `sexual`, `minor`, `illegal`, `other`, `other` 는 설명 필수, 설명은 500자까지).
  모델의 답만이다(사람의 말과 서버가 쓴 행동 말은 422 `not_reportable`). 같은 답은 한 번만(409 `already_reported`).
  볼 수 있는 세션의 말이 아니면(남의 것, 지운 세션, 볼 수 없는 등급) 404 `message_not_found` 다.
- **지우기.** 세션을 지운 것으로 적어도 신고는 남는다. 세션의 행이 지워지면(탈퇴) 함께 지워진다. 신고에 든 것은 신고한 사람의 세션이라서다.
- **운영자 API**(`/admin/...`, `app/operators/`, 운영자가 아니면 404). 열린 신고의 목록은 `minor` 가 먼저, 그다음 오래된 것부터이고 세션의 글과 신고한 사람을 싣지 않는다.
  신고 하나를 보려면 사유(`reason`, 쿼리, 1~200자)가 필수이고, 보기 전에 감사 기록(`operator_reads`)을 저장한다. 없는 신고를 본 시도도 남는다.
  처리(`actioned`, `dismissed`)는 감사 기록(`operator_actions`)과 한 트랜잭션이다. 이미 처리했으면 409 `already_handled` 다.
  두 기록은 덧붙이기만 한다(트리거가 고치기와 지우기를 막는다). 사유와 본 내용은 로그에 싣지 않는다.
- **처리는 기록이다.** 세계관을 숨기지 않는다. asset 의 숨기기 API 는 아직 캐릭터만이다.
- **알림.** 처리하면(받아들이든 아니든) 신고한 사람의 알림함에 `story_report.handled` 를 하나 넣는다. `payload` 는 신고한 때의 세계관 이름(`name`)뿐이다.
  결과, 사유, 세션의 글은 싣지 않는다(chat 의 신고와 같다). 열쇠는 `story_report.handled:<신고>` 다.
  알림 서버는 kind 마다 넣을 수 있는 서버를 정해 두므로 chat 의 `message_report.handled` 를 빌려 쓰지 않고 따로 둔다.
  처리와 한 트랜잭션에 발송함(`outgoing_notifications`, `app/notifications/`)에 적고, 알림 서버에는 뒤에서 5초마다 보낸다.
  발송함과 보내는 작업은 공용 코드에 있다([server-core 의 알림 보내기](../shared/server-core/README.md#알림-보내기)). 탈퇴하면 보내지 않은 알림을 지운다.

### 요청 수 제한

chat 의 것과 같다(`app/limits/`). 한 사람이 정해진 시간 안에 몇 번 했는가를 세고, 넘으면 429 로 막는다. 크레딧과 별개로 짧은 시간에 몰아 보내는 것을 늦춘다.

- **무엇을 세나.** 모델을 부르는 요청(말 보내기, 행동, 다시 생성, 이어서 출력)과 모델을 부르지 않는 쓰기(세션 시작과 지우기, 모델과 가지 바꾸기, 답 고치기, 신고)를 따로 센다.
  [기록 내려받기](#기록-내려받기)는 따로 센다(10분에 10번). 다른 읽기와 멈추기는 세지 않는다. 모델을 부르는 주소는 라우터에 걸어(`app/turns/router.py`) 그 라우터에 더하는 주소도 저절로 센다.
- **어떻게 세나.** 고정 구간이다(첫 시도에서 시작해 정한 초 뒤에 끝난다). Redis(DB 3, 키의 머리 `story:limit`)에 Lua 한 덩어리로 올리고 만료를 건다.
  사람의 번호는 해시해서 키에 넣는다. `REDIS_URL` 이 비면 서버 안의 메모리로 센다.
- **막히면.** 429 `too_many_attempts`, 본문의 `retry_after` 와 `Retry-After` 에 기다릴 초를 싣는다. 몇 번까지인지는 알리지 않는다.
- **Redis 에 닿지 못하면** 막지 않고 경고(`limits.unavailable`)만 남긴다. 이야기를 막아서 잃는 것이 더 크다.
- 같은 코드가 trpg, chat, story 세 곳에 있다. server-core 로 뽑는 것은 따로 한다(server-core 에 Redis 의존이 붙어 모든 서버의 잠금 파일이 바뀐다).

### 탈퇴

인증 서버가 계정을 비울 때 알린다(`POST /api/v1/story/service/users/{public_id}/withdrawal`, `app/withdrawal/`, chat 과 같다. [탈퇴 설계](../docs/architecture/withdrawal.md)).

- 지우는 것: 세션(지운 것으로 적어 둔 것도)과 딸린 것(말, 말마다의 상태, 요약, 기억 메모, 페르소나의 사본, 그 세션의 [신고](#신고)), 가져온 세계관의 판의 사본과 그 로어북의 벡터, 계정의 기록(본 엔딩, 연 일러스트), 보내지 않은 알림.
- 남기는 것: 청구 기록(`generations`). 세션과 말을 가리키는 칸만 비운다(공개 ID, 모델, 토큰 수, 원가, 청구 상태, 홀드의 이름표가 남는다).
  운영자의 감사 기록(`operator_reads`, `operator_actions`)도 남는다. 운영자와 신고의 id, 사유뿐이고 본 내용은 없다.
- 한 트랜잭션이고 멱등이다. 같은 알림이 다시 와도, 이 서버에 그 사람의 것이 없어도 200 `{"status": "processed"}` 다. 모르는 칸은 버린다.
- 인증 서버의 서명(`AUTH_SERVER_SECRET`)이 아니면 401, 본문의 모양이 틀리면 422, 본문이 16KB 를 넘으면 서명을 보기 전에 413 이다.
  사용자의 토큰은 없고 요청 수 제한도 걸지 않는다. 프록시는 `/api/v1/story/service/` 를 밖에서 받지 않는다(404).

### 토큰 검증

공용 코드 `shared/server-core` 의 것(`server_core/auth/`)을 쓴다(#588). 알림 서버와 같다. 규칙의 설명은
[게임 서버의 토큰 검증](../trpg-server/README.md#토큰-검증)에 있다. 토큰의 주인(`CurrentUser`)에는 성인 등급(`adult_content`)과
운영자(`is_operator`)도 실린다. 성인 등급의 세계관을 거를 때 쓴다(`allowed_ratings`, 세션을 만들 때 한 번).

- 공개키: 처음 필요할 때 가져와 5분 기억한다. 모르는 `kid` 면 다시 가져오되 60초에 한 번만. 30분 넘게 못 가져오면 버리고 503.
- 끊긴 세션: 서버가 뜨자마자, 그 뒤 30초마다 인증 서버의 목록을 받는다. `ver` 가 그 사람의 `min_ver` 보다 낮은 토큰은 401.
- 토큰의 대상(`aud`)에 `ai-trpg-story` 가 있어야 한다. 인증 서버의 `JWT_AUDIENCE` 기본값에 이미 있다(#597).
  인증 서버의 `.env` 에 `JWT_AUDIENCE` 를 적어 둔 PC 는 그 줄에도 이 이름을 더한다.

## 모델 목록

세션에 쓸 언어 모델들이다. chat 서버의 것(`chat-server/README.md` 의 "모델 목록")과 같은 코드와 같은 운영이다(2026-10-25 유저 결정).
원본은 모델 목록의 파일 하나(`shared/ai-core` 의 `ai_core/model_catalog.toml`)이고, 이 서버의 표에 들여온다.

```powershell
cd story-server
uv run python -m scripts.models sync --dry-run    # 무엇이 바뀔지 보기
uv run python -m scripts.models sync              # 들여오기. 새 모델은 꺼진 채로 들어온다
uv run python -m scripts.models list
uv run python -m scripts.models enable gpt-6-luna # 켜기. 오늘의 원가가 있고 은퇴하지 않아야 한다
uv run python -m scripts.models adult grok-5 --allow
```

- **고를 수 있는 모델**은 켜져 있고 은퇴하지 않았고 결제 서버가 팔고 있는 것이다. 성인 등급의 세션에는 그중 `allows_adult` 가 참인 것만이다.
  약관이 성적인 콘텐츠를 막는 창구(anthropic, gemini)는 성인 스위치를 켜지 못한다.
- **세션의 모델.** 시작할 때 `model` 을 보내지 않으면 지난번 세션의 모델을 쓴다(쓸 수 없으면 없이 시작한다).
  null 이면 없이, 이름표면 그 모델이고 고를 수 없으면 422 `model_unavailable` 이다. `PUT .../model` 로 바꾼다.
  이름표를 골랐는데 가격 목록을 받지 못했으면 503 `prices_unavailable` 이다(값을 모르는 모델을 고르게 하지 않는다).
  지난번 모델로 시작하는 것과 읽기는 그대로 된다. 값을 모르면 팔고 있다고 보고, 말을 보낼 때 결제 서버가 다시 본다.
- **몰래 바꾸지 않는다.** 고른 뒤 꺼지거나 은퇴하거나 판매를 멈춰도 세션은 그 모델을 가리키고, 읽을 때 `usable: false` 를 싣는다. 화면이 다시 고르게 한다.
- **값.** 판매가(말 한 번에 몇 크레딧)는 결제 서버의 가격표(`story.<이름표>.i0.o0`)가 정한다. 이 서버는 받은 값을 붙여 보여 줄 뿐이고,
  실제로 빠지는 값은 홀드를 걸 때 결제 서버가 정한다. `app/billing/` 은 chat 서버의 것과 같은 코드다(가격표의 머리만 `story`).
  - 가격 목록(`GET /api/v1/billing/service/prices`, 서명)을 받아 두고 1분쯤마다 버전(ETag)으로 다시 묻는다. 결제 서버는 이 서버의 머리(`story`)의 줄만 낸다.
    받지 못하면 마지막 목록을 쓰고 경고를 남긴다. 한 번도 받지 못했으면 503 `prices_unavailable`(`Retry-After: 30`)이다.
  - 모델 목록 API 의 값 칸은 chat 서버와 같다: `credits`(글자, 결제 서버 없이 돌면 null), `tier`(`premium` 이면 골드로만 낸다),
    `promo`(행사가), `next`(예약된 바뀜. `credits` 가 null 이면 그때부터 팔지 않는다).
  - 홀드, 확정, 반환, 연장(`app/billing/http_billing.py`)은 말을 보내는 PR 이 쓴다. 부를 때마다 `billing_calls_total` 을 센다.
  - `BILLING_URL` 이 비면 받지 않는다(`free`). 모델은 값 없이 모두 보인다.
- 들여오기(`app/catalog/sync.py`)는 chat 의 것과 같은 코드라 이것으로 세 벌이다(게임, chat, story). 표의 ORM 이 서버마다 달라 공용 코드로 올리려면 표의 모양까지 옮겨야 해서, 셋을 함께 고칠 일이 잦아지면 그때 올린다.

## 엔진

결과는 엔진이, 말은 모델이 맡는다. 엔진(`app/engine/`)은 판(세계관의 문서)과 지금의 상태만 받아 답을 돌려주는 순수 함수다.
DB 와 모델을 모른다. 세션과 말에 붙이는 일(상태를 말마다 저장하고 장면의 인물을 내려보내는 것)은 말을 주고받는 조각에서 한다.

| 파일 | 하는 일 |
| --- | --- |
| `world.py` | 엔진이 읽는 판의 칸(시간대, 길, 기한, 처음의 장소와 소지품, 인물과 고백, 이벤트와 선택지, 엔딩). 모르는 칸은 버린다 |
| `state.py` | 지금의 상태(시각, 장소, 소지품, 호감도, 건넨 물건, 본 이벤트, 동행, 고르기를 기다리는 이벤트, 고백 대기, 본 엔딩)와 처음의 상태. 바꿀 수 없는 값이다 |
| `clock.py` | 시각의 셈. 시각은 1일째 0시부터 흐른 분이다. 며칠째(자정에 바뀐다), 시간대(첫 시간대 전은 마지막 시간대), 기한 |
| `actions.py` | 시각을 흘리는 행동. 이동(길로 바로 이어진 곳, 길의 시간만큼), 시간 보내기(다음 시간대), 하루 마치기(다음 날의 첫 시간대) |
| `conditions.py` | 조건 10가지와 목록 맞추기(모두/하나라도, 빈 목록은 맞음). 일정, 이벤트, 고백, 엔딩이 함께 쓴다 |
| `scene.py` | 인물의 자리(동행 → 일정 → 기본 장소)와 장면의 인물(같은 장소 + 동행 + 이벤트가 부른 인물, 4명까지) |
| `effects.py` | 효과 여섯 가지를 적힌 차례대로 반영한다(호감도 ±n 은 0~100 으로 자른다, 물건 주기·가져가기, 동행 시작·끝, 장소 옮기기) |
| `events.py` | 이벤트 열기(조건이 맞는 것 가운데 판의 차례로 하나, 한 번만이면 다시 열리지 않는다)와 선택지 고르기. 고르지 않고 넘어가면 선택지는 사라진다 |
| `endings.py` | 엔딩의 판정. 그 시작(고백 성공·실패, 기한, 이벤트)의 엔딩을 판의 차례로 맞춰 첫 엔딩을 고른다. 엔딩을 보면 엔딩과 기한이 다시 일어나지 않는다 |
| `gifts.py` | 건네기. 장면의 인물에게 가진 물건 하나를 건네고, 그 물건의 선물 규칙들을 차례로 더한다(한 번만인 규칙은 처음 건넬 때만) |
| `confession.py` | 고백. 장면의 인물에게만, 호감도의 단계와 조건으로 성공을 정한다. 실패하면 계속(호감도를 내리고 정한 날 동안 다시 못 한다) 또는 실패 엔딩 |

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

| 테이블 | 무엇 |
| --- | --- |
| `worlds` | asset 서버에서 가져온 세계관의 판의 사본. 사람마다, 판마다 하나(`owner_id`, `source_id`, `version` 이 고유). 문서는 받은 그대로(JSONB) |
| `conversations` | 세션 하나. 판의 사본을 가리킨다(지우지 못하게 `RESTRICT`). 목록은 `owner_id`, `updated_at` 의 색인으로 읽는다. 세션의 모델(`model_slug`)을 가리킨다. 지운 세션은 지운 시각(`deleted_at`)만 적는다 |
| `ai_models`, `ai_model_costs`, `ai_model_snapshots` | [모델 목록](#모델-목록). chat 서버의 표와 같은 모양이다 |
| `conversation_personas` | 세션에 가져온 계정 페르소나의 사본(chat 의 표와 같은 모양). 세션마다 하나, 페르소나 없이 시작했으면 없다 |
| `messages` | 말 하나. 트리다(`parent_id`). 답은 말 조각(`segments`)과 그때의 장면의 인물(`cast`)을 갖는다. 사람이 고친 답은 `edited` 다. 다음 답 추천은 `suggestions`(셋까지)다. 세션의 `active_leaf_id` 가 지금 가지의 끝이다 |
| `message_states` | 말에 붙은 엔진의 상태(JSONB). 상태가 바뀐 말에만 있다. 가지의 끝의 상태는 끝에서 가장 가까운 것이고, 없으면 처음의 상태다 |
| `generations` | 모델을 한 번 부른 것과 그 청구(chat 서버의 표와 같은 모양). 버린 줄의 수(`dropped_segments`)를 더했다 |
| `lore_embeddings` | 판의 사본에 든 로어북 항목의 벡터(pgvector, `extensions` 스키마). (사본, 임베딩 모델, 로어북, 항목)마다 하나. 사본이 지워지면 함께 지워진다 |
| `memory_notes` | 세션의 기억 메모. 세션이 지워지면 함께 지워진다 |
| `summaries` | 굴리는 요약. 요약한 마지막 말에 붙고(`message_id`), 부른 모델과 토큰, 원가를 적는다. 말이나 세션이 지워지면 함께 지워진다 |
| `ending_records` | 계정의 본 엔딩. (`owner_id`, `world_source`, `ending_id`)마다 처음 본 시각과 세션. 세션이 지워지면 세션만 비운다 |
| `illustration_unlocks` | 계정의 연 일러스트. (`owner_id`, `world_source`, `scene_kind`, `scene_id`)마다 연 때의 그림(`image_id`), 장면의 인물(`cast`), 처음 연 시각과 세션 |
| `message_reports` | 모델의 답의 [신고](#신고)와 그때 굳힌 글(답과 앞의 말 여섯, 세계관과 판, 모델). (신고한 사람, 말)마다 하나. 열린 신고는 부분 색인으로 읽는다. 세션이 지워지면 함께 지워진다 |
| `operator_reads`, `operator_actions` | 운영자가 신고의 글을 본 기록과 처리한 기록(chat 과 같은 칸). 덧붙이기만 한다(트리거). 신고와 세션에 외래 키가 없어 탈퇴해도 남는다. 테스트는 TRUNCATE 로 비운다 |
| `outgoing_notifications` | 알림 서버에 보낼 알림의 발송함(공용 코드의 칸, chat 과 같다). 보낸 줄은 지우고 받지 않은 줄(`failed`)만 남는다. 탈퇴하면 그 사람의 것을 지운다 |

모델의 모듈을 새로 만들면 `migrations/env.py` 와 `tests/cleaning.py` 에서 그 모듈을 불러온다.

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
