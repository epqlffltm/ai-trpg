# asset 서버

캐릭터, 계정 페르소나, 그림의 원본을 맡는 서버다(#290). 설계는 [docs/architecture/asset-server.md](../docs/architecture/asset-server.md)에 있다.

다른 FastAPI 서버(게임, 알림)와 같은 구성(설정, 로그, 추적, 메트릭, 상태 확인, 토큰 검증, Alembic, 테스트) 위에 기능이 차례로 붙는다.

| 이슈 | 내용 |
| --- | --- |
| #564 | 뼈대 |
| #565 | 계정 페르소나. 사용자 API. 서버끼리 사본 내주기는 다음 조각 |
| #566 | 그림. 올리기, 디코딩 격리, 내주기(nginx 의 `X-Accel-Redirect`) |
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

서버끼리 부를 때의 비밀(계정 페르소나와 판을 가져가는 서버마다의 비밀)은 server-core 의 서명(#588)이 들어온 뒤에 더한다.

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

### 계정 페르소나

TRPG, chat, story 가 함께 쓰는 "나"의 설정이다(#565, [설계](../docs/architecture/asset-server.md#계정-페르소나)). `app/personas/`.

| 칸 | 제한 | 내용 |
| --- | --- | --- |
| `name` | 1~50자(필수) | 이름. 앞뒤 공백을 뗀다 |
| `description` | 1,000자 | 설명 |
| `image_id` | 그림의 id 또는 `null` | 프로필 그림. 그림(#566)이 생기기 전이라 지금은 적어 두기만 한다. 그림이 생기면 자기 그림인지 본다 |
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
- 서버끼리 사본과 `revision` 을 내주는 길은 server-core 의 서명(#588)이 들어온 뒤에 더한다.
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
| `image_id` | 그림의 id 또는 `null` | 대표 그림. 그림(#566)이 생기기 전이라 적어 두기만 한다 |
| `rating` | `all`, `adult` | 이용 등급 |
| `visibility` | `private`, `public` | 공개 범위. 처음에는 비공개. 고칠 때만 바꾼다 |
| `latest_version`, `published_at` | 응답에만 | 마지막으로 게시한 판의 번호와 시각 |

첫 칸은 대화에 필요한 핵심만이다(2026-10-21 유저 결정). 호감도의 규칙, 의복과 물건, 지도, 일러스트는 chat 이 그 단계(장소와 소지품)에 갈 때 판의 형식을 올려 더한다.

- **누가 만드나.** 1~2단계에는 운영자만 만든다(`CHARACTERS_FOR_EVERYONE` 거짓, 403 `operator_only`). 3단계에서 열어도 **공개로 두는 것은 운영자만**이다. 일반 사용자의 공개는 신고와 관리자 화면(E4)이 생긴 뒤에 연다.
- **등급.** 성인 등급(`adult`)은 성인 확인을 한 사람이나 운영자만 쓴다(`app/ratings.py` 의 `allowed_ratings`, 게임 서버와 같은 규칙). 나이와 성별로는 거르지 않는다.
- **게시.** 막는 것은 시작 상황이 없는 것(`start_missing`)이다. 소개는 허용 목록으로 걸러 판에 넣고, 걸러 낸 것을 `removed` 로 알린다(게시는 된다).
  - 판은 바뀌지 않는다. 번호는 1 부터 오른다. 같은 캐릭터를 동시에 게시하면 행을 잠가 차례로 번호를 준다.
  - 판의 문서(`document`)는 형식 번호(`format`, 지금 1)를 갖는다. 칸이 늘면 번호를 올리고 받는 쪽이 번호로 읽는 법을 고른다.
- **공개 목록.** 공개이고 게시한 판이 있는 캐릭터의 **마지막 판**을 낸다(초안이 아니다). 등급은 **판의 등급**으로 거른다. 초안의 등급을 바꿔도 다음 판까지는 게시한 판이 나간다.
  로그인하지 않은 사람과 성인 확인을 하지 않은 사람에게 성인 캐릭터는 없는 것이다(404). 토큰을 보냈는데 틀렸으면 401 이다.
- 지우면 판도 함께 지워진다. 이미 가져간 대화는 사본으로 돈다.
- 서버끼리 판을 가져가는 길과 지금의 판 번호를 묻는 길은 다음 조각이다(서명은 `server_core.service_auth`).

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
