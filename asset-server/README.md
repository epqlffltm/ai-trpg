# asset 서버

캐릭터, 계정 페르소나, 그림의 원본을 맡는 서버다(#290). 설계는 [docs/architecture/asset-server.md](../docs/architecture/asset-server.md)에 있다.

다른 FastAPI 서버(게임, 알림)와 같은 구성(설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증, Alembic, 테스트) 위에 기능이 차례로 붙는다.

| 이슈 | 내용 |
| --- | --- |
| #564 | 뼈대 |
| #565 | 계정 페르소나. 사용자 API. 서버끼리 사본 내주기는 다음 조각 |
| #566 | 그림. 올리기, 디코딩 격리, 내주기(nginx 의 `X-Accel-Redirect`), 자기 그림만 붙이기, 공개 캐릭터의 그림을 남이 보기, 탈퇴 때 지우기 |
| #567 | 캐릭터와 게시. 소개 HTML 거르기, 초안과 판, 공개 목록(지금). 서버끼리 판 내주기는 다음 조각 |

정해 둔 값: 포트 `8006`, 토큰의 대상 `ai-trpg-asset`, DB 계정과 스키마 `asset`(테스트는 `asset_test`), 주소 `/api/v1/asset/`.

## 실행

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `asset` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/08-asset-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트가 생기기 전에 만든 볼륨이라면 한 번 직접 실행한다. 루트의 `.env`에 `ASSET_DB_PASSWORD`를 적고
컨테이너를 다시 만든 뒤(`docker compose up -d`), 저장소 루트에서 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/08-asset-role.sql
```

초기화 스크립트, compose(`asset-migrate`, `asset-server`), 프록시의 `/api/v1/asset/`, 관문 CI, `.env` 도구는 인프라 세션이 따로 PR 로 맞춘다.
그 PR 이 들어가기 전에는 PC 에서 직접 띄운다(아래).

### 설치와 실행

파이썬 3.13 과 [uv](https://docs.astral.sh/uv/) 가 있어야 한다.

```powershell
cd asset-server
copy .env.example .env
uv sync
uv run alembic upgrade heads
uv run uvicorn app.main:app --port 8006 --reload
```

`.env`의 `DATABASE_URL`에 `asset` 계정의 비밀번호(루트 `.env`의 `ASSET_DB_PASSWORD`)와 포트(`POSTGRES_PORT`)를 적는다.

인증 서버 8000, 게임 서버 8001, 게시판 서버 8002, 결제 서버 8003, 알림 서버 8004 이고 8005 는 chat 서버의 자리라 8006 번으로 띄운다.
`http://127.0.0.1:8006/health` 가 `{"status":"ok"}` 를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8006/health/ready` 가 `{"status":"ok"}` 를 돌려주면 DB 까지 연결된 것이다.

compose 로 함께 띄울 때(인프라 세션의 PR 뒤)도 같은 `asset-server/.env` 를 쓴다. 주소(DB, 인증 서버의 공개키)만 compose 가 덮어쓴다.
바깥 주소는 프록시 하나(`http://127.0.0.1:8080/api/v1/asset/...`)이고 asset 서버의 포트는 열지 않는다.
이미지(`Dockerfile`)는 게임, 알림 서버의 것과 같은 모양이다. root 가 아닌 사용자(번호 10001)로 돌고, `.env` 와 테스트는 넣지 않는다.

## 설정

환경 변수나 `asset-server/.env` 에서 읽는다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | DB 접속 주소(`postgresql+asyncpg://asset:…@127.0.0.1:5432/trpg`). 적지 않으면 서버가 뜨지 않는다 |
| `DB_SCHEMA` | `asset` | 테이블이 놓이는 스키마. 테스트는 `asset_test`로 고정한다 |
| `DEBUG` | `false` | API 문서 화면(`/api/v1/asset/docs`)을 켠다 |
| `APP_ENVIRONMENT` | `development` | 로그의 `environment` 칸. 동작은 바꾸지 않는다 |
| `APP_VERSION` | `dev` | 로그의 `version` 칸. 배포할 때 git SHA 나 이미지의 버전을 넣는다 |
| `LOG_LEVEL` | `info` | 이 수준부터 로그를 남긴다(`debug`, `info`, `warning`, `error`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음(보내지 않음) | span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. `http://alloy:4318` 처럼 경로 없이 적는다([추적](#추적), [메트릭](#메트릭)) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | 메트릭을 보내는 간격(밀리초, 1000 이상) |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. 여기서 받은 키로 서명된 토큰을 믿는다 |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-asset` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다 |
| `PERSONA_MAX_PER_OWNER` | `50` | 한 사람이 가질 수 있는 계정 페르소나의 수(1~500). TRPG 의 보관함과 같다 |
| `CHARACTERS_FOR_EVERYONE` | `false` | 캐릭터를 누구나 만들 수 있는가. 1~2단계에는 운영자만 만든다(거짓). 참이어도 공개로 두는 것은 운영자만이다 |
| `CHAT_SERVER_SECRET` | 비어 있음(받지 않음) | chat 서버가 페르소나와 판을 가져갈 때 서명하는 비밀([다른 서버에 내주기](#다른-서버에-내주기)). `chat-server/.env` 의 `ASSET_SECRET` 과 같은 값. 적으면 32자 이상. 비밀값이다 |
| `AUTH_SERVER_SECRET` | 비어 있음(받지 않음) | 인증 서버가 [탈퇴](#탈퇴)를 알릴 때 서명하는 비밀. `auth-server/.env` 의 `ASSET_SECRET` 과 같은 값. 적으면 32자 이상이고 다른 비밀과 달라야 한다. 비밀값이다 |

| `IMAGE_STORE_ENDPOINT` | 비어 있음(저장소 없음) | [그림](#그림) 저장소의 주소. compose 가 `http://object-store:8333`(로컬), S3 의 지역 주소(staging)를 넘긴다. 비어 있으면 그림 올리기와 내주기가 503 이다 |
| `IMAGE_STORE_REGION` | `ap-northeast-2` | 서명에 넣는 지역. SeaweedFS 는 아무 값이나 받는다 |
| `IMAGE_STORE_BUCKET`, `IMAGE_STORE_ACCESS_KEY_ID`, `IMAGE_STORE_SECRET_ACCESS_KEY` | 비어 있음 | 버킷과 키. 주소를 적었으면 셋 다 적어야 뜬다. 비밀 키는 루트 `.env` 에 있다(compose 가 넘긴다). 비밀값이다 |
| `IMAGE_STORE_TIMEOUT_SECONDS` | `10` | 저장소에 넣는 요청의 시간 상한 |
| `IMAGE_MAX_BYTES` | `10485760`(10MB) | 올리는 그림의 크기 상한. 프록시의 상한은 11MB 다 |
| `IMAGE_MAX_PIXELS` | `40000000` | 가로 × 세로의 상한. 풀기 전에 머리만 보고 거절한다 |
| `IMAGE_DECODE_MEMORY_MB`, `IMAGE_DECODE_CPU_SECONDS`, `IMAGE_DECODE_WALL_SECONDS` | `768`, `10`, `15` | 그림을 여는 따로 된 프로세스의 상한(주소 공간, CPU 시간, 벽시계) |
| `IMAGE_DECODE_CONCURRENCY` | `2` | 한꺼번에 여는 수. 메모리는 상한 × 이 수까지 쓴다 |

부르는 서버마다 비밀을 따로 둔다. story 와 TRPG 는 그 서버가 가져가기 시작할 때 `STORY_SERVER_SECRET`, `TRPG_SERVER_SECRET` 으로 더한다.

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
| GET | `/api/v1/asset/me` | 토큰의 주인(`{"user_id"}`, 인증 서버의 `public_id`). 토큰 검증이 이어졌는지 보는 가장 작은 주소다(게임 서버의 `GET /me` 와 같다) | access 토큰 |
| POST | `/api/v1/asset/personas` | [계정 페르소나](#계정-페르소나) 만들기. 201. 처음 만든 것이 기본이다. 상한이면 409 `persona_limit` | access 토큰 |
| GET | `/api/v1/asset/personas` | 자기 페르소나 전부. 기본이 먼저, 그다음 만든 차례 | access 토큰 |
| GET | `/api/v1/asset/personas/{id}` | 하나 읽기. 남의 것과 없는 것은 404 | access 토큰 |
| PATCH | `/api/v1/asset/personas/{id}` | 고치기. 보낸 칸만 바뀐다. 내용이 바뀌면 `revision` 이 오른다 | access 토큰 |
| PUT | `/api/v1/asset/personas/{id}/default` | 기본으로 두기. 다른 것은 기본에서 내린다. `revision` 은 그대로 | access 토큰 |
| DELETE | `/api/v1/asset/personas/{id}` | 지우기. 204. 기본이었으면 가장 먼저 만든 것이 기본이 된다 | access 토큰 |
| POST | `/api/v1/asset/characters` | [캐릭터](#캐릭터와-게시) 만들기. 201. 처음에는 비공개. 1~2단계에는 운영자만(403 `operator_only`). 성인 등급은 성인 확인이 필요하다(403 `adult_content_required`) | access 토큰 |
| GET | `/api/v1/asset/characters` | 자기 캐릭터의 목록(`{items, total}`). 최근에 고친 것부터. `limit`, `offset` | access 토큰 |
| GET | `/api/v1/asset/characters/{id}` | 자기 캐릭터의 초안 하나. 남의 것과 없는 것은 404 | access 토큰 |
| PATCH | `/api/v1/asset/characters/{id}` | 초안 고치기. 보낸 칸만 바뀐다. 게시한 판은 그대로다. 공개로 두는 것(`visibility`)은 운영자만 | access 토큰 |
| DELETE | `/api/v1/asset/characters/{id}` | 지우기. 204. 판도 함께 지워진다 | access 토큰 |
| GET | `/api/v1/asset/characters/{id}/publish-check` | 게시해 보기(`{ready, problems, removed}`). 판은 생기지 않는다 | access 토큰 |
| POST | `/api/v1/asset/characters/{id}/versions` | 게시. 201. 새 판과 소개에서 걸러 낸 것(`removed`). 막는 것이 있으면 409 `{problems}` | access 토큰 |
| GET | `/api/v1/asset/characters/{id}/versions` | 판의 목록. 최근 것부터 | access 토큰 |
| GET | `/api/v1/asset/characters/{id}/versions/{number}` | 판 하나(굳힌 문서까지) | access 토큰 |
| GET | `/api/v1/asset/listings/characters` | 공개 캐릭터의 목록. 최근에 게시한 것부터. 볼 수 있는 등급만 | 없어도 된다 |
| GET | `/api/v1/asset/listings/characters/{id}` | 공개 캐릭터 하나(마지막 판의 문서). 볼 수 없으면 404 | 없어도 된다 |
| POST | `/api/v1/asset/images` | [그림](#그림) 올리기. 201. 본문은 그림 파일의 바이트(PNG, JPEG, WebP). 형식이 아니면 415 `image_format`, 열 수 없으면 422 `image_unreadable`, 크면 413, 저장소를 쓸 수 없으면 503 `image_store_unavailable` | access 토큰 |
| GET | `/api/v1/asset/images/{id}` | 그림 내주기. 볼 수 있으면 본문 없이 200 과 `X-Accel-Redirect`, `X-Image-Source`(프록시가 그림을 내준다). 없거나 볼 수 없으면 404. 주인과, 공개 캐릭터의 판에 쓰였으면 그 판을 볼 수 있는 사람이 본다 | 없어도 된다 |
| GET | `/api/v1/asset/service/{caller}/personas/{id}` | [다른 서버에](#다른-서버에-내주기) 페르소나의 사본과 `revision`. 토큰의 주인의 것만(아니면 404) | 서버의 서명 + access 토큰 |
| GET | `/api/v1/asset/service/{caller}/personas/{id}/revision` | 페르소나의 지금 `revision`(`{id, revision}`) | 서버의 서명 + access 토큰 |
| GET | `/api/v1/asset/service/{caller}/characters/{id}/latest` | 쓸 수 있는 캐릭터의 마지막 판(`{id, version, rating, published_at, document}`) | 서버의 서명 + access 토큰 |
| GET | `/api/v1/asset/service/{caller}/characters/{id}/latest/number` | 마지막 판의 번호(`{id, version}`). 같은 규칙 | 서버의 서명 + access 토큰 |
| POST | `/api/v1/asset/service/users/{public_id}/withdrawal` | [탈퇴](#탈퇴)한 사람의 페르소나와 비공개 캐릭터, 쓰이지 않는 그림을 지운다. 200 `{"status":"processed"}`. 그림 저장소에 닿지 못하면 503 | 인증 서버의 서명 |

### 계정 페르소나

TRPG, chat, story 가 함께 쓰는 "나"의 설정이다(#565, [설계](../docs/architecture/asset-server.md#계정-페르소나)). `app/personas/`.

| 칸 | 제한 | 내용 |
| --- | --- | --- |
| `name` | 1~50자(필수) | 이름. 앞뒤 공백을 뗀다 |
| `description` | 1,000자 | 설명 |
| `image_id` | 그림의 id 또는 `null` | 프로필 그림. 자기가 올린 [그림](#그림)만 붙인다(아니면 422 `image_not_owned`). 주인만 본다 |
| `age`, `gender` | 각 20자 | 적어 두는 글이다("스물일곱", "알 수 없음"). 서버는 이것으로 거르거나 막지 않는다 |
| `form_of_address` | 30자 | 호칭. 모델이 나를 부르는 말 |
| `speech_examples`, `personality` | 각 1,000자 | 말투 예시, 성격. 모델이 읽는다 |
| `is_default` | 응답에만 | 기본인가. 페르소나가 있으면 늘 하나가 기본이다 |
| `revision` | 응답에만 | 1 부터. 내용이 바뀔 때만 오른다(같은 값을 보내거나 기본으로 두는 것은 오르지 않는다) |

- **판이 없다.** 주인만 보고 고친다. 쓰는 서비스는 세션을 시작할 때 사본을 뜨고 `revision` 을 적어 둔다. 지금 것과 다르면 "새 설정으로 바꾸기"를 보인다.
- **고치기.** 보낸 칸만 바뀐다. 글의 칸은 빈 글로 비운다. `null` 은 `image_id` 만 받는다(그림을 뗀다). 글의 칸에 `null` 은 422 다.
- **지우기.** 행을 지운다. 가져간 세션은 사본으로 돈다.
- **상한과 동시성.** 한 사람마다 `PERSONA_MAX_PER_OWNER`(기본 50)까지다. 세거나 기본을 바꾸기 전에 그 사람에 거는 잠금(advisory lock)을 잡는다.
  동시에 만들어도 넘지 않고, 동시에 기본을 바꿔도 기본은 하나다(DB 의 부분 고유 색인 `uq_personas_default_per_owner` 도 막는다).
  고칠 때는 행을 잠근다(`FOR UPDATE`). 두 요청이 같은 `revision` 을 읽고 하나만 올리는 일이 없다.
- 다른 서버(chat, story, TRPG)는 [다른 서버에 내주기](#다른-서버에-내주기)의 주소로 사본과 `revision` 을 가져간다.
- TRPG 의 보관함을 나누는 이관(이름과 설명은 계정 페르소나로, 능력치는 TRPG 의 시트로)은 따로 한다.

### 소개 글의 HTML

제작자가 쓴 소개 글(HTML 과 인라인 CSS)을 허용 목록으로 거르는 모듈이다(`app/content/html.py`). 캐릭터의 게시(#567)가 쓴다.
규칙은 [공용 코드 규칙의 소개 글의 HTML](../docs/architecture/shared-code.md#소개-글의-html)이다. 화면은 같은 허용 목록으로 DOMPurify 를 한 번 더 거친다.

- `clean_intro(html)` 은 거른 글과 걸러 낸 것(`removed`: 종류와 이름)을 돌려준다. 게시가 걸러 낸 것을 `problems[]` 로 제작자에게 보인다.
  - 종류: `tag`(script, iframe, form …), `attribute`("div.onclick"), `style`(CSS 속성), `link`(https 가 아닌 링크), `image`(우리 그림 저장소의 것이 아닌 그림).
  - 같은 것은 한 번, 처음 나온 차례다.
- 거르는 것은 `nh3` 다. 무엇이 빠졌는지는 `nh3` 가 알려 주지 않아서, 같은 판단 함수로 입력을 따로 훑어 모은다.
  거른 글을 다시 거르면 바뀌지 않고 알릴 것도 없다(테스트가 본다). 거르기와 알리기가 같은 규칙을 쓴다는 뜻이다.
- 링크는 `https://` 만 남고 `rel="noopener noreferrer"` 가 붙는다. 상대 주소(`/login`, `#top`)도 뺀다.
- 그림은 우리 그림 저장소의 주소(`/api/v1/asset/images/{소문자 UUID}`)만 남는다.
- CSS 는 허용 목록의 속성만, 값에 `url(`, `expression(`, `\`(이스케이프)가 없을 때만 남는다. 남는 것이 없으면 `style` 을 뺀다.
- 크기 상한은 50KB(UTF-8 의 바이트, `intro_too_long`)다.
- 허용 목록은 모듈의 상수(`ALLOWED_TAGS`, `GLOBAL_ATTRIBUTES`, `TAG_ATTRIBUTES`, `ALLOWED_STYLE_PROPERTIES`)다. 화면의 DOMPurify 설정과 문서의 표를 이 값과 같게 둔다.
- **app.* 를 가져오지 않는다**(`tests/test_content_boundary.py`). 두 번째로 쓰는 곳(TRPG 시나리오 소개를 asset 으로 옮기는 PR)이 생기면 파일째 `shared/` 로 옮긴다(2026-10-21 결정).

### 캐릭터와 게시

chat 의 상대가 되는 캐릭터다(#567, [설계](../docs/architecture/asset-server.md#게시와-판)). `app/characters/`.
제작자는 초안을 고치고, **게시**하면 판(번호가 오르는 고정된 문서)이 생긴다. chat 은 대화를 시작할 때 판 하나를 가져가 고정한다.

| 칸 | 제한 | 내용 |
| --- | --- | --- |
| `name` | 1~50자(필수) | 이름 |
| `intro_html` | 50KB(UTF-8 바이트) | 소개(HTML 과 인라인 CSS). 초안에는 쓴 그대로 둔다. 게시할 때 거른다([소개 글의 HTML](#소개-글의-html)) |
| `greeting`, `speech_examples` | 각 2,000자 | 인사말(대화를 열 때 먼저 하는 말), 말투 예시. 모델이 읽는다 |
| `age`, `gender` | 각 20자 | 적어 두는 글이다. 거르거나 막지 않는다 |
| `tags` | 10개, 각 20자 | 목록에서 찾을 때 쓴다. 대소문자만 다른 것도 같은 것으로 보아 거부한다 |
| `starts` | 5개 | 시작 상황 `{title(30자), situation(2,000자)}`. 대화를 열 때 하나를 고른다. 제목이 겹치면 거부한다 |
| `image_id` | 그림의 id 또는 `null` | 대표 그림. 자기가 올린 [그림](#그림)만 붙인다(아니면 422 `image_not_owned`) |
| `rating` | `all`, `adult` | 이용 등급 |
| `places` | 30개 | [지도](#지도와-물건)의 장소 `{id, name(30자), description(1,000자), image_id}`. 그림은 그 장소의 배경 |
| `paths` | 100개 | 두 장소를 잇는 길 `{a, b, minutes(0~1,440)}`. 양쪽으로 다닌다 |
| `start_place` | 장소의 id 또는 `null` | 대화가 시작하는 장소 |
| `items` | 50개 | 물건 `{id, name(30자), description(500자), kind(thing, clothing), consumable, image_id}`. `consumable` 이면 쓰면 하나 없어진다 |
| `start_items` | 20개 | 사용자가 처음에 가진 물건 `{item(물건의 id), count(1~99)}` |
| `affection` | 객체 또는 `null` | [호감도](#호감도). 없으면 호감도가 없는 캐릭터다 |
| `visibility` | `private`, `public` | 공개 범위. 처음에는 비공개. 고칠 때만 바꾼다 |
| `latest_version`, `published_at` | 응답에만 | 마지막으로 게시한 판의 번호와 시각 |

첫 칸은 대화에 필요한 핵심만이었다(2026-10-21 유저 결정). 지도와 물건은 chat 의 만드는 순서 4 에서 캐릭터에 넣었다(2026-10-22 유저 결정, 판의 형식 2).
호감도는 판의 형식 3 에서 더했다. 상대의 시작 차림, 일러스트는 chat 이 그 단계에 갈 때 판의 형식을 올려 더한다.

- **누가 만드나.** 1~2단계에는 운영자만 만든다(`CHARACTERS_FOR_EVERYONE` 거짓, 403 `operator_only`). 3단계에서 열어도 **공개로 두는 것은 운영자만**이다. 일반 사용자의 공개는 신고와 관리자 화면(E4)이 생긴 뒤에 연다.
- **등급.** 성인 등급(`adult`)은 성인 확인을 한 사람이나 운영자만 쓴다(`app/ratings.py` 의 `allowed_ratings`, 게임 서버와 같은 규칙). 나이와 성별로는 거르지 않는다.
- **게시.** 막는 것은 시작 상황이 없는 것(`start_missing`), 남의 그림(`image_not_owned`), 맞지 않는 [지도와 물건](#지도와-물건)이다. 소개는 허용 목록으로 걸러 판에 넣고, 걸러 낸 것을 `removed` 로 알린다(게시는 된다).
  - 판은 바뀌지 않는다. 번호는 1 부터 오른다. 같은 캐릭터를 동시에 게시하면 행을 잠가 차례로 번호를 준다.
  - 판의 문서(`document`)는 형식 번호(`format`, 지금 3)를 갖는다. 칸이 늘면 번호를 올리고 받는 쪽이 번호로 읽는 법을 고른다.
    형식 1 의 판(지도와 물건이 없다)과 형식 2 의 판(호감도가 없다)도 그대로 읽힌다(빈 칸으로).
- **공개 목록.** 공개이고 게시한 판이 있는 캐릭터의 **마지막 판**을 낸다(초안이 아니다). 등급은 **판의 등급**으로 거른다. 초안의 등급을 바꿔도 다음 판까지는 게시한 판이 나간다.
  로그인하지 않은 사람과 성인 확인을 하지 않은 사람에게 성인 캐릭터는 없는 것이다(404). 토큰을 보냈는데 틀렸으면 401 이다.
- 지우면 판도 함께 지워진다. 이미 가져간 대화는 사본으로 돈다.
- chat(나중에 story)은 [다른 서버에 내주기](#다른-서버에-내주기)의 주소로 마지막 판을 가져가고, 지금의 번호를 묻는다.

#### 지도와 물건

chat 의 대화에서 지도를 펼쳐 갈 곳을 고르고, 소지품을 열어 쓰거나 건넨다(chat 서버 설계의 "장소와 소지품"). 여기서는 그 정의만 갖는다.
지금 어디에 있고 무엇을 가졌는지(상태)는 chat 이 대화의 가지마다 갖는다.

- **id.** 장소와 물건은 캐릭터 안에서 고유한 id(영문자, 숫자, `_`, `-`, 40자)를 갖는다. 길과 시작 소지품이 이것을 가리키고, chat 의 상태가 이것을 적는다.
  판이 바뀌어도 같은 것은 같은 id 로 둔다(만드는 화면이 정해 붙인다). 같은 id 가 두 번 있으면 422 다.
- **길.** 서로 다른 두 장소를 잇는다(제자리 길은 422). 같은 두 장소를 잇는 길은 하나다(차례를 가리지 않는다). 숨은 길과 찾기는 TRPG 의 규칙이라 없다. chat 은 가 본 곳만 보이는 안개를 쓴다.
- **옷.** `kind` 가 `clothing` 인 물건은 건네면 상대의 차림에 들어간다(chat 이 한다).
- **쓰기.** `consumable` 이 참인 물건(음식 등)은 쓰면 하나 없어진다. 거짓이면(우산 등) 남는다(2026-10-22 유저 결정, chat 이 한다).
- **그림.** 장소의 배경과 물건의 그림도 자기가 올린 그림만 붙인다(422 `image_not_owned`). 게시하면 판에 쓰인 그림으로 적혀 공개 캐릭터의 그림처럼 보인다.
- **어긋남은 게시에서.** 초안은 고치는 중이라 어긋나도 둔다(장소를 지웠는데 길이 남았다). 게시가 막는다.

| 막는 것 | 뜻 |
| --- | --- |
| `place_missing` | 길이나 처음 있는 장소가 없는 장소를 가리킨다 |
| `start_place_missing` | 장소가 있는데 처음 있는 장소를 고르지 않았다 |
| `item_missing` | 시작 소지품이 없는 물건을 가리킨다 |

장소와 물건이 하나도 없는 캐릭터도 게시된다(지도와 소지품이 없는 대화다).

#### 호감도

상대가 사용자를 얼마나 좋아하는지의 값 하나(0~100)다. 정의만 여기에 있고, 값을 바꾸는 것은 chat 의 엔진이다(chat 서버 설계의 "정한 것"의 호감도).

```json
{
  "display": "stage",
  "start": 10,
  "stages": [{"name": "낯섦", "at": 0}, {"name": "친구", "at": 30}, {"name": "연인", "at": 70}],
  "rules": [{"id": "gift", "on": {"kind": "give_item", "target": "scarf"}, "change": 5, "once": false}]
}
```

- **보이는 방식**(`display`). `number` 는 숫자와 게이지, `stage` 는 단계 이름과 게이지(숫자는 chat 이 내려보내지 않는다). 기본 `number`.
- **단계**(`stages`, 1~10개). 첫 단계는 0 에서 시작하고 경계(`at`)가 차례로 커진다. 이름은 겹치지 않는다(20자). 어느 값이든 단계가 하나다.
- **규칙**(`rules`, 50개까지). 사용자가 `on` 의 행동을 하면 `change`(-20~20, 0 은 아니다)만큼 바꾼다(0~100 안으로 자른다).
  `once` 면 그 대화의 가지에서 처음 한 번만이다(처음 하는 일). 행동은 TRPG 의 퀘스트 조건과 같은 (종류, 대상) 모양이다.

| `on.kind` | 뜻 | `on.target` |
| --- | --- | --- |
| `give_item` | 그 물건을 건넸다(선물) | 물건의 id |
| `reach_place` | 그 장소에 갔다(데이트 장소) | 장소의 id |
| `use_item` | 그 물건을 썼다 | 물건의 id |

- 규칙이 없는 물건이나 장소를 가리키면 게시가 막힌다(`affection_target_missing`). 대화의 내용만으로는 움직이지 않는다(첫 출시).
- 형식 1, 2 의 판은 호감도가 없다(`null`).

### 그림

배경, 캐릭터, 프로필, 소개 글 안의 그림이다(#566, [설계](../docs/architecture/asset-server.md#그림)). `app/images/`.

**올리기.** `POST /api/v1/asset/images`, 본문은 그림 파일 그대로다(multipart 가 아니다). 화면은 `fetch(url, {method: 'POST', body: file})` 로 보낸다.

1. 로그인을 먼저 본다. 토큰이 없으면 본문을 읽지 않고 401 이다.
2. 크기를 본다(`IMAGE_MAX_BYTES`). 머리말(Content-Length)이 넘는다고 하면 읽지 않고 413, 읽다가 넘어도 413 이다.
3. 형식을 파일의 머리로 고른다(PNG, JPEG, WebP). 요청의 Content-Type 과 확장자는 보지 않는다. 아니면 415 다.
4. **따로 된 프로세스에서 연다**(`app/images/isolation.py`, `app/images/decoder.py`). `python -I` 로 띄워 서버의 코드와 환경 변수를 읽지 않는다.
   그 프로세스가 맨 처음 주소 공간과 CPU 시간의 상한을 스스로 걸고, 서버는 벽시계의 상한을 걸어 넘으면 죽인다. 한꺼번에 `IMAGE_DECODE_CONCURRENCY` 개까지 연다.
   - 픽셀 수(`IMAGE_MAX_PIXELS`)는 Pillow 가 풀기 전에 머리만 보고 거절한다(압축 폭탄).
   - 머리가 고른 형식과 연 형식이 같아야 한다.
   - **다시 인코딩한다.** EXIF(위치 정보 등), ICC, 글 조각, 그림 뒤에 붙인 바이트가 없어진다. 사진의 방향(EXIF orientation)은 지우기 전에 픽셀에 적용한다. JPEG 과 WebP 는 품질 90 이다.
   - 움직이는 그림(애니메이션 WebP, APNG)은 첫 장만 남는다.
   - 열 수 없으면(망가졌다, 형식이 다르다, 상한을 넘었다, 시간이 다 됐다) 모두 422 `image_unreadable` 이다. 까닭은 나누지 않는다.
5. 저장소에 그림의 id 로 넣는다. 형식(`Content-Type`)을 객체에 적는다. 그다음 행(`images`: 주인, 형식, 바이트, 너비와 높이)을 적는다.
   여는 일과 넣는 일이 끝난 뒤에야 DB 연결을 잡는다. 넣은 뒤 행을 적지 못하면 아무도 가리키지 않는 객체가 저장소에 남는다(내주지 않는다).
6. 답: `{id, format, byte_size, width, height, url, created_at}`. `url` 은 내주는 주소(`/api/v1/asset/images/{id}`)다. 소개 글의 img 는 이 모양만 받는다.

**내주기.** `GET /api/v1/asset/images/{id}`

- 볼 수 있으면 본문 없이 200 과 두 머리말을 답한다. `X-Accel-Redirect: /_images/{id}`(프록시의 내부 위치), `X-Image-Source: <저장소의 GetObject 를 서명한 주소, 60초>`.
  프록시가 그 주소로 받아 그림의 id 로 캐시하고 내준다(`docker/nginx/templates/api.inc.template`). 프록시 없이 부르면 빈 200 이다.
- **볼 수 있는 사람.** 주인, 그리고 그 그림이 쓰인 판이 공개 캐릭터의 것이고 그 판의 등급을 볼 수 있는 사람이다.
  로그인하지 않아도 전체 이용가의 판에 쓰인 그림은 본다. 그 밖(남, 토큰 없음, 없는 그림)은 같은 404 다.
  - 옛 판의 그림도 보인다. 대화는 옛 판을 사본으로 갖고 있다. 대표 그림을 바꿔 다시 게시해도 옛 판의 그림이 보여야 한다.
  - 비공개로 돌리거나 지운 캐릭터의 그림, 게시 전의 초안에만 있는 그림, 페르소나의 그림은 주인만 본다.
- 브라우저의 img 는 Authorization 머리말을 싣지 못한다. 공개 캐릭터의 전체 이용가 그림은 img 로 바로 보인다.
  주인만 보는 그림과 성인 등급의 그림은 화면이 토큰을 실어 받아(fetch) object URL 로 보여 준다.
- 그림은 바뀌지 않는다. 고치려면 새로 올린다(새 id).

**저장소의 서명.** S3 의 서명(Signature Version 4)을 SDK 없이 만든다(`app/images/sigv4.py`). 넣기와 서명한 주소 둘뿐이다.
AWS 문서의 예시 값으로 시험하고(`tests/test_image_store.py`), 스택 시험이 실제 저장소(SeaweedFS)에 넣고 서명한 주소로 받아 본다.
주소는 경로 방식(`<주소>/<버킷>/<키>`)이다. 프록시는 그 주소가 저장소의 것일 때만 따라가므로, compose 밖에서 띄운 서버(`127.0.0.1:8333`)가 만든 주소로는 프록시를 거쳐 받을 수 없다.

**붙이기.** 페르소나와 캐릭터의 대표 그림(`image_id`), 소개 글의 img 는 **자기가 올린 그림만** 쓴다. 남의 그림 id 를 적어 그 그림을 공개로 돌리는 길을 막는다.
- 대표 그림은 붙일 때(만들기, 고치기) 본다. 남의 그림과 없는 그림은 422 `image_not_owned` 다. 떼기(`null`)는 늘 된다.
- 소개 글의 img 는 게시할 때 본다. 남의 그림이 있으면 게시를 막는다(`problems` 에 `image_not_owned`, 게시해 보기에도 나온다).
- 게시하면 그 판에 쓰인 그림(대표 그림과 거른 소개 글의 그림)을 적는다(`image_uses`). 남이 볼 수 있는지는 이 표로 본다.
- `image_id` 는 그림의 행을 가리키는 외래 키다. 그림이 지워지면(탈퇴) 비워진다.

**알려진 한계**
- 목록용 작은 그림은 만들지 않는다. 원본 하나다.

### 다른 서버에 내주기

chat(나중에 story 와 TRPG)이 세션을 시작할 때 페르소나의 사본과 캐릭터의 판을 가져가는 주소다(#565, #567,
[설계](../docs/architecture/asset-server.md#쓰는-서비스에-내주기)). `app/personas/supply.py`, `app/characters/supply.py`.

    GET /api/v1/asset/service/{caller}/...
    X-Service-Signature: t=<보낸 시각>,v1=<HMAC-SHA256>      그 서버의 비밀로 서명(server_core/service_auth/signing.py)
    Authorization: Bearer <사용자의 access 토큰>             그 서버가 받은 토큰을 그대로 넘긴다

- **두 가지를 함께 본다.** 서명은 "어느 서버가 부르나"를, 토큰은 "누구를 위해 가져가나"를 증명한다.
  서버의 비밀이 새도 그것만으로는 아무의 페르소나도 가져가지 못한다(그 사람의 토큰이 있어야 한다).
  토큰만으로는 이 주소를 부르지 못한다. 프록시가 `/api/v1/asset/service/` 를 바깥에 열지 않고(404), 서명이 없으면 401 이다.
- **서명.** 알림 서버의 것과 같다(`app/core/service_auth.py`). `caller` 는 주소에 있고 주소까지 서명하므로 남의 이름으로 부를 수 없다.
  비밀은 부르는 서버마다 따로다(`CHAT_SERVER_SECRET`). 서명이 없거나, 틀렸거나, 앞뒤 5분을 넘겼거나, 남의 주소의 것이거나,
  모르는 서버이거나, 그 서버의 비밀이 비었으면 모두 같은 401 이다. 토큰보다 서명을 먼저 본다. 본문은 16KB 까지(넘으면 413).
- **페르소나.** 토큰의 주인의 것만 내준다. 남의 것과 없는 것은 404 다. 사본은 모델에 넣을 내용과 `revision` 이다(기본인지와 시각은 싣지 않는다).
- **판.** 마지막 판을 내준다. 쓸 수 있는 사람인지는 asset 서버가 판단한다.
  - 주인이면 비공개여도 쓴다. 남은 공개이고 **판의 등급**을 볼 수 있어야 한다. 아니면 404 다(공개 목록과 같다).
  - 주인인데 판의 등급을 쓸 수 없으면(성인 확인을 잃었다) 403 `adult_content_required` 다. 자기 것이라 있는 것을 안다.
  - 게시한 적이 없으면 주인에게도 404 다.
- **지금의 번호와 revision.** 화면을 열 때 한 번 묻는다(턴마다 묻지 않는다). 가져간 것보다 크면 "새 판이 있다", 다르면 "새 설정으로 바꾸기"를 보인다.
  같은 규칙을 거친다. 비공개로 돌렸거나 볼 수 없게 된 캐릭터는 "새 판이 있다"도 알리지 않는다.
- 가져간 쪽은 사본으로 돈다. asset 서버가 죽어도 진행 중인 대화는 계속되고, 새 세션만 시작하지 못한다.
- 지금은 마지막 판만 내준다. 옛 판은 가져간 쪽이 사본으로 갖고 있다. 번호를 골라 가져올 일이 생기면 그때 더한다.

### 탈퇴

인증 서버가 유예(7일)가 지난 탈퇴를 알리면 그 사람의 것을 지운다([탈퇴](../docs/architecture/withdrawal.md)). `app/withdrawal/`.

    POST /api/v1/asset/service/users/{public_id}/withdrawal
    본문: {"withdrawn_at": "2026-10-28T03:00:00Z"}
    서명: 인증 서버의 비밀(AUTH_SERVER_SECRET). 사용자의 토큰은 없다

- **지우는 것.** 페르소나 모두, 비공개 캐릭터(판까지). 한 트랜잭션이다.
  그다음 그 사람의 [그림](#그림) 가운데 남은 판(남긴 공개 캐릭터의 판)에 쓰이지 않은 것을 저장소에서 지우고, 그 행을 지운다.
  남긴 공개 캐릭터의 초안이 가리키던 그림이 지워지면 초안의 `image_id` 가 비워진다.
  저장소에서 지우다 실패하면 503 이다. 행이 남아 있어 인증 서버가 다시 보낸 알림이 마저 지운다.
- **남기는 것.** 공개 캐릭터와 그 판. 남이 쓰는 것이다. 1~2단계에는 운영자만 공개로 둔다. 가져간 세션은 사본으로 돈다.
- **멱등.** 같은 알림이 다시 와도, 이 서버에 그 사람의 것이 없어도 200 `{"status":"processed"}` 다. 그 밖의 답이면 인증 서버가 다시 보낸다.
- **서명.** 인증 서버의 비밀은 부르는 서버의 표(`CHAT_SERVER_SECRET` 등)와 따로다. 그 비밀로는 페르소나와 판을 가져가지 못하고,
  chat 의 비밀로는 탈퇴를 알리지 못한다. 서명이 맞지 않으면 401, 본문의 모양이 틀리면 422 이고 아무것도 지우지 않는다. 본문의 모르는 칸은 버린다.
- 따로 로그를 남기지 않는다. 요청의 줄(`http.request`)에 경로의 틀과 결과가 남는다. 공개 ID 는 남기지 않는다.
- 보내는 쪽은 인증 서버의 워커(`auth-welcome-credits`)다. 인증 서버의 `ASSET_SECRET` 이 비어 있으면 보내지 않고 쌓아 둔다. 비밀을 적으면 그 전에 쌓인 것부터 온다.
### 토큰 검증

공용 코드 `shared/server-core` 의 것(`server_core/auth/`)을 쓴다(#588). 알림 서버와 같다. 규칙의 설명은
[게임 서버의 토큰 검증](../trpg-server/README.md#토큰-검증)에 있다. 토큰의 주인(`CurrentUser`)에는 성인 등급(`adult_content`)과
운영자(`is_operator`)도 실린다. 캐릭터의 만들기와 공개, 등급(`app/ratings.py`)이 그것을 본다. 로그인 없이도 읽는 주소(공개 목록)는 `OptionalUser` 를 쓴다.

- 공개키: 처음 필요할 때 가져와 5분 기억한다. 모르는 `kid` 면 다시 가져오되 60초에 한 번만. 30분 넘게 못 가져오면 버리고 503.
- 끊긴 세션: 서버가 뜨자마자, 그 뒤 30초마다 인증 서버의 목록을 받는다. `ver` 가 그 사람의 `min_ver` 보다 낮은 토큰은 401.
- 토큰의 대상(`aud`)에 `ai-trpg-asset` 이 있어야 한다. 인증 서버의 `JWT_AUDIENCE` 기본값에 이 이름을 더하는 것은 인증 세션이 한다.
  그 전에 발급된 토큰에는 이 이름이 없어서 401 이다(access 토큰은 15분 뒤 저절로 맞는다).
  인증 서버의 `.env` 에 `JWT_AUDIENCE` 를 적어 둔 PC 는 그 줄에도 이 이름을 더한다.

## 로그

[관측 규격](../docs/observability.md)을 따른다. 공용 코드 `shared/server-core` 의 `server_core/observability/` 를 쓴다(#588).
이 서버의 이름(`asset-server`)은 설정(`app/core/config.py` 의 `service_name`)이 넘긴다. 공용 코드가 남긴 줄의 `logger` 는 `server_core.*` 다.

- 로그는 한 줄에 하나의 JSON 이다(`service`: `asset-server`). 표준 오류로 나간다.
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
| 요청 | `GET /api/v1/asset/me`(메서드와 경로의 틀). 상태 확인은 걸지 않는다 | `server_core/observability/request_spans.py` |
| 인증 서버를 부르는 것 | `HTTP GET` | `server_core/observability/http_spans.py` |
| 쿼리 | `db SELECT personas`(종류와 테이블). 손으로 쓴 것은 `db SELECT` | `server_core/observability/db_spans.py` |
| 뒤의 작업 | 작업의 이름. 한 바퀴가 새 추적 하나다 | `server_core/observability/spans.py` 의 `job_span` |

- 로그의 `trace_id` 가 span 의 trace id 와 같다. 요청의 span 에는 `request_id`, 작업의 span 에는 `job_id` 를 싣는다
- 싣지 않는 것: 주소의 경로와 뒤의 값, 머리말, 본문, SQL 의 문장과 값, 예외의 글. 쿼리가 실패하면 SQLSTATE 만 적는다
- 요청이나 작업 밖의 쿼리와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 span 을 걸지 않는다
- 뒤의 작업을 감싸는 틀(`job_span`, `job_scope`, `measured_job`)은 아직 쓰는 곳이 없다. 그림의 정리 작업 같은 것이 생기면 쓴다. 테스트는 `tests/jobs.py` 의 바퀴로 본다
- span 은 따로 도는 스레드가 묶어서 보낸다. 서버가 꺼질 때 남은 것을 보낸다(5초 안). 수집기가 죽어 있어도 요청은 영향을 받지 않는다

## 메트릭

요청, DB, 뒤의 작업을 세어 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 15초마다 민다. 수집기가 Prometheus 에 넘긴다.
이름과 label 은 [관측 규격](../docs/observability.md)의 "메트릭"에 있다. 주소가 비어 있으면 세기만 하고 보내지 않는다.

| 메트릭 | label | 세는 곳 |
| --- | --- | --- |
| `http_server_requests_total`, `http_server_request_duration_seconds`, `http_server_active_requests` | `method`, `route`(경로의 틀), `status_code` | `server_core/observability/request_metrics.py`. 미들웨어의 맨 바깥이다 |
| `db_up` | 없음 | `app/api/readiness.py`. 준비 상태 확인이 본 DB |
| `db_pool_connections`, `db_pool_connections_max`, `db_pool_wait_seconds` | `state`(`idle`, `in_use`) | `server_core/observability/pool_metrics.py`. 풀은 5 + 넘칠 때 10 이다 |
| `background_jobs_started_total`, `background_jobs_finished_total`, `background_jobs_running`, `background_job_duration_seconds` | `operation`, `result` | `server_core/observability/metrics.py` 의 `measured_job`. 아직 쓰는 작업이 없다 |

- 계측기는 공용 코드(`server_core/observability/metrics.py`)에 한 묶음으로 있다. 이 서버만의 계측기가 생기면 `InstrumentSet` 으로 더한다(알림 서버의 `app/notifications/metrics.py`).
  테스트는 `server_core/testing/metrics.py` 로 메모리에 모아 이름, 단위, label 을 본다(`metrics` fixture)
- 보내는 길은 공용 코드의 테스트가 가짜 수집기로 본다. 이 서버가 꺼질 때 이 서버의 이름으로 보내는지는 `tests/test_tracing_setup.py` 가 본다
- 대시보드와 경보, Prometheus 에 들어오는지 보는 CI(`stack`)는 인프라 세션의 PR 과 함께 붙는다

## DB

DB 인스턴스는 다른 서버와 같고, 계정과 스키마는 따로다. asset 서버는 `asset` 계정으로 `asset`
스키마(테스트는 `asset_test`)만 쓴다. 다른 서버의 스키마에 닿지 못하는 것을 테스트(`tests/test_schema_isolation.py`)가 확인한다.

테이블은 `personas`(#565), `characters`, `character_versions`(#567)다. 모델을 새로 만들면 `migrations/env.py` 와 `tests/cleaning.py` 에서 그 모듈을 불러온다.

### 마이그레이션

```powershell
cd asset-server
uv run alembic upgrade heads                          # 개발용 스키마에 적용
$env:DB_SCHEMA = 'asset_test'; uv run alembic upgrade heads; Remove-Item Env:DB_SCHEMA   # 테스트용 스키마에 적용
uv run alembic check                                  # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
uv run alembic revision --autogenerate -m "설명"       # 모델과 DB 를 비교해 새 마이그레이션 만들기
```

DB 주소와 스키마는 앱과 같은 설정(`.env`)에서 읽는다. `alembic.ini` 에는 적지 않는다.
어디까지 적용했는지 적는 표(`alembic_version`)도 스키마마다 따로 있다.

## 테스트

테스트는 실제 PostgreSQL 의 `asset_test` 스키마에서 돈다. `.env`의 `DATABASE_URL`을 그대로 쓴다.
테스트용 스키마에 마이그레이션을 먼저 적용한다(위의 "마이그레이션"). 테스트는 시작할 때마다 테이블을 비운다.

```powershell
cd asset-server
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

CI 는 `.github/workflows/asset-server.yml` 이다. 린트, 모양, 의존성 취약점, 마이그레이션(적용, 누락, 되돌리기), 테스트와 커버리지(95% 이상)를 본다.
관문(`ci.yml`)이 이 워크플로를 부르게 하는 것은 인프라 세션의 PR 이다. 그 전에는 main 에 들어간 뒤의 push 에서만 돈다.
