# 게시판 서버

[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)

[ai-trpg](../README.md)의 게시판 서버. 사이트가 운영하는 커뮤니티를 맡는다. 공지, 이벤트, 잡담, 시나리오 이야기 같은 글과 댓글이다. NestJS(TypeScript)로 만든다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.
시나리오의 소개 페이지에 붙는 댓글(플레이한 사람들의 평)은 여기가 아니라 시나리오 쪽의 일이다.

지금은 게시판, 글, 댓글, 글마다의 댓글 수, 글 고정, 글 검색, 쓰기 횟수 제한, 글과 댓글의 신고까지 있다. 게시판 넷(공지사항, 이벤트, 자유 게시판, 시나리오 이야기)에 글을 쓰고, 글에 댓글과 답글을 단다. 글과 댓글에는 글쓴이의 닉네임이 함께 나온다.

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

명령은 모두 `board-server` 폴더 안에서 실행한다. Node.js 24 가 필요하다.

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

```
cp .env.example .env
npm install
npm run migration:run
npm run start:dev
```

`.env`의 `DATABASE_URL`에 `board` 계정의 비밀번호(루트 `.env`의 `BOARD_DB_PASSWORD`)와 포트(`POSTGRES_PORT`)를 적는다.
`AUTH_JWKS_URL`은 인증 서버를 다른 포트로 띄웠을 때만 고친다.
인증 서버가 8000번, 게임 서버가 8001번을 쓰므로 8002번으로 띄운다. `http://127.0.0.1:8002/health/ready`가 `{"status":"ok"}`를 돌려주면 DB 까지 정상이다.

`npm run start:dev`는 파일을 고치면 서버를 다시 띄운다. 고치지 않고 한 번만 띄우려면 `npm run start`다.
서버는 뜰 때 DB 에 연결해 본다. 닿지 않으면 1초 간격으로 세 번 다시 해 보고 뜨지 않는다.

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | `postgresql://board:<비밀번호>@127.0.0.1:5432/trpg` 형식. 게임 서버와 달리 `+asyncpg`가 붙지 않는다 |
| `DB_SCHEMA` | `board` | 테이블이 놓이는 스키마. 테스트는 `board_test`로 고정한다 |
| `AUTH_JWKS_URL` | 없음(필수) | 인증 서버가 공개키를 내주는 주소. `http://127.0.0.1:8000/api/v1/auth/jwks` |
| `AUTH_SESSION_REVOCATIONS_URL` | `AUTH_JWKS_URL` 옆(`…/session-revocations`) | 인증 서버가 끊긴 세션의 목록을 내주는 주소(#274). `AUTH_JWKS_URL` 이 `/jwks` 로 끝나지 않으면 적어야 한다 |
| `JWT_ISSUER` | `ai-trpg-auth` | 믿는 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-board` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다. 하나만 적는다 |
| `HOST` | `127.0.0.1` | 서버가 듣는 주소. 컨테이너에서는 `0.0.0.0` |
| `PORT` | `8002` | 서버가 듣는 포트 |

### 로그인한 사용자로 불러 보기

인증 서버를 띄우고 로그인해서 받은 access 토큰을 붙여 부른다.

```
curl http://127.0.0.1:8002/api/v1/board/me -H "Authorization: Bearer <access 토큰>"
```

`{"user_id":"..."}`가 오면 인증 서버가 발급한 토큰을 이 서버가 검증한 것이다. 토큰에 닉네임이 실려 있었다면 이때 적어 둔다. 401 이 오면 둘을 본다.

- **인증 서버의 `JWT_AUDIENCE`에 `ai-trpg-board`가 있는가.** 인증 서버는 토큰에 대상의 목록을 싣고, 이 서버는 그 목록에 자기 이름이 있는지 본다.
  인증 서버의 기본값에는 들어 있다. `auth-server/.env`에 `JWT_AUDIENCE`를 직접 적어 둔 PC 라면 그 줄에 `ai-trpg-board`를 더하고 인증 서버를 다시 띄운다.
- **토큰이 그 뒤에 발급된 것인가.** 대상은 발급할 때 정해진다. 고치기 전에 받은 토큰에는 새 이름이 없다. access 토큰의 수명은 15분이다.

503 이 오면 이 서버가 인증 서버의 공개키를 한 번도 받지 못한 것이다. 인증 서버가 떠 있는지와 `AUTH_JWKS_URL`을 본다.

### 운영자

공지사항과 이벤트 게시판에는 운영자만 글을 쓴다. 운영자는 남의 글도 지울 수 있다.
누가 운영자인지는 인증 서버가 정한다(#389). 인증 서버의 Django 그룹 `operators` 에 든 계정이고, access 토큰의 `roles` 에 `"operator"` 가 실린다. 이 서버는 토큰을 읽기만 한다.

넣고 빼는 법은 인증 서버 README 의 "운영자를 넣고 빼는 법"을 따른다(관리자 화면 `/admin/` 의 회원 → 권한의 그룹).
넣은 뒤에는 그 사람이 다시 로그인하거나 토큰을 갱신해야 실린다. 뺀 것도 이미 받은 access 토큰이 끝날 때까지(15분) 통한다. 바로 막아야 하면 인증 서버에서 그 사람의 세션을 끊는다.
잘 실렸는지는 그 사람의 토큰으로 `/api/v1/board/me`를 불러 `is_operator`가 `true`인지 본다.

예전에는 이 서버의 `operators` 테이블이 운영자를 정했다. 마이그레이션 `DropOperators` 가 그 테이블을 지운다. 거기 있던 사람은 옮겨지지 않으니, 마이그레이션 전에 목록을 보고 인증 서버의 그룹에 넣는다.

### 테스트와 검사

```
npm run lint
npm run format
npm run build
npm test
npm run test:e2e
```

- `npm run lint`(oxlint): 쓰지 않는 이름이나 기다리지 않은 Promise 같은 문제를 실행하지 않고 찾는다.
- `npm run format`(prettier): 코드의 모양을 정해진 규칙으로 맞춘다. 고치지 않고 검사만 하려면 `npm run format:check`다.
- `npm run build`: TypeScript 를 JavaScript 로 바꿔 `dist/`에 놓는다. 타입이 맞지 않으면 여기서 실패한다. 파이썬에는 없는 단계다.
- `npm test`(vitest): `src/` 안의 `*.spec.ts`. 함수와 클래스를 하나씩 본다. 서버도 DB 도 쓰지 않는다.
- `npm run test:e2e`: `test/` 안의 `*.e2e-spec.ts`. 앱을 통째로 만들어 주소로 불러 본다. 실제 PostgreSQL 에서 돈다.
- `npm run test:cov`, `npm run test:e2e:cov`: 같은 테스트를 돌리며 지나간 줄의 비율(커버리지)도 잰다. 대상은 `src/` 전체(테스트와 마이그레이션은 빼고)이고, 테스트가 불러오지 않은 파일도 0% 로 센다. 결과는 `coverage/unit`, `coverage/e2e` 에 남는다(커밋하지 않는다).

커밋하기 전에 다섯을 모두 돌린다.

앱 테스트는 서버의 경고와 오류만 화면에 찍는다. 일부러 5xx 를 만드는 테스트(검색 시간 초과, 인증 서버에 닿지 않음, DB 에 닿지 않음)는 로그를 화면 대신 모아서 "오류 줄이 남았다"를 확인한다(`test/logs.ts`).
그래서 테스트가 모두 통과하면 화면에 `ERROR` 가 나오지 않는다. 나오면 어딘가에서 예상하지 못한 오류가 난 것이다.

앱 테스트는 개발용과 같은 DB의 `board_test` 스키마를 쓰므로 개발용 데이터(`board` 스키마)를 건드리지 않는다.
DB 주소는 환경 변수나 `.env`의 것을 그대로 읽고, 스키마는 테스트가 고정한다(`test/setup.ts`).
테스트용 스키마에도 테이블이 있어야 한다. 마이그레이션을 새로 만들거나 받으면 한 번 적용한다.

```
# PowerShell
$env:DB_SCHEMA='board_test'; npm run migration:run; Remove-Item Env:DB_SCHEMA

# bash
DB_SCHEMA=board_test npm run migration:run
```

앱 테스트는 테스트용 스키마의 글, 댓글, 신고를 비우고 쓴다(`test/data.ts`). 운영자는 토큰의 `roles` 로 흉내 낸다(`test/tokens.ts`). 파일을 하나씩 차례로 돌린다. 모두 같은 스키마에 쓰기 때문이다.

DB가 꺼져 있으면 앱 테스트가 실패한다. 인증 서버는 띄우지 않아도 된다. 토큰은 테스트가 직접 만든 키로 서명하고,
그 공개키를 인증 서버가 내준 것처럼 앱에 꽂는다(`test/tokens.ts`, `test/app.ts`).
다른 서버들의 계정과 스키마(`auth`, `game`, `billing`)도 DB 에 만들어져 있어야 한다. 게시판 계정이 거기에 들어가지 못하는지 테스트가 확인한다.

### 계약 시험

`contract/` 는 같은 시나리오를 **떠 있는 서버에 HTTP 로만** 보내는 시험이다(pytest, #785). 서버의 코드를 가져오지 않는다.
그래서 같은 시험이 지금의 서버(NestJS)와 다시 쓸 서버(FastAPI) 둘 다에 돈다. 둘 다 통과하면 갈아 끼워도 된다.

- 서버는 시험이 프로세스로 띄운다. 명령은 `BOARD_SERVER_COMMAND`(기본 `node dist/main.js`), 폴더는 `BOARD_SERVER_DIR`(기본 `board-server`)다.
  서버에는 서버가 원래 읽는 환경 변수만 준다(`PORT`, `HOST`, `DATABASE_URL`, `DB_SCHEMA`, `AUTH_JWKS_URL`, `AUTH_SERVER_SECRET`).
- 인증 서버는 시험이 띄우는 작은 가짜가 공개키 목록을 내준다(`contract/harness/auth.py`). 토큰은 시험의 키로 서명한다.
- DB 는 `board_test` 스키마를 쓴다. 시험마다 글, 댓글, 신고, 닉네임, 알림의 발송함을 비운다. 시간이 흐른 것처럼 시각을 옮기는 일만 DB 로 한다.
- 사람은 시험마다 새로 만든다. 서버가 최근에 적은 닉네임을 기억해 두는 것과 섞이지 않게 한다.
- 쓰기 한도는 서버의 것 그대로다. 많이 쓰는 시험은 사람을 나누거나 DB 에 바로 넣는다.
- 옮긴 것: 게시판, 글, 검색, 댓글, 댓글 수, 고정, 신고, 쓰기 한도, 토큰, 글쓴이의 닉네임, 오류의 모양, health, 탈퇴 받기, 알림의 발송함에 적기.
- 옮기지 않은 것: 로그, 메트릭, 추적, 설정, DB 권한, OpenAPI, 검색 시간 초과, 그리고 Nest 의 부품을 바꿔 꽂아야 하는 경우
  (시험용 컨트롤러, 처음 키를 받지 못한 서버, 끊긴 세션의 목록, DB 에 닿지 않는 health, 알림을 실제로 보내기, 쿼리 수 세기).
  HTTP 만으로는 볼 수 없어서 `test/*.e2e-spec.ts` 가 계속 본다. 다시 쓸 서버에서는 그 서버의 시험으로 옮긴다.

```
# 빌드하고 테스트용 스키마에 마이그레이션을 적용한 뒤(위)
cd contract
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

### 패키지를 더하고 뺄 때

```
npm install 패키지이름
npm install --save-dev 패키지이름
npm uninstall 패키지이름
```

`package.json`과 `package-lock.json`이 함께 바뀐다. 둘 다 커밋한다. `node_modules/`는 커밋하지 않는다.
설치할 때 취약점 경고가 나와도 `npm audit fix --force`는 쓰지 않는다. 버전의 범위를 무시하고 올리거나 내려서 프로젝트가 깨질 수 있다.
서버에 실제로 들어가는 패키지의 취약점만 보려면 `npm audit --omit=dev`다.

## DB와 마이그레이션

테이블 구조의 변경은 TypeORM 의 마이그레이션으로 관리한다. DB 주소와 스키마는 서버와 같은 설정에서 읽는다(`src/database/data-source.ts`).
명령은 먼저 빌드하고, 빌드된 파일(`dist/`)로 돈다.

```
npm run migration:run                                        # 마이그레이션 적용
npm run migration:generate -- src/migrations/AddSomething    # 엔티티와 DB를 비교해 새 마이그레이션 만들기
npm run migration:check                                      # 엔티티를 바꾸고 마이그레이션을 안 만들었는지 검사
npm run migration:show                                       # 적용된 것과 안 된 것 보기
npm run migration:revert                                     # 마지막 하나 되돌리기
```

파이썬 쪽의 Alembic 과 짝을 지으면 `upgrade head`가 `migration:run`, `revision --autogenerate`가 `migration:generate`, `check`가 `migration:check`다.

**자동으로 만든 마이그레이션은 읽어 보고 커밋한다.** TypeORM 은 색인을 지우는 줄에 만들 때의 스키마 이름을 붙인다(`DROP INDEX "board"."IDX_..."`).
같은 파일을 `board`와 `board_test`에 함께 쓰므로 그 이름을 지운다. 지우지 않으면 `npm test`가 실패한다(`src/migrations/migrations.spec.ts`).
만든 뒤에는 `npm run format`으로 모양을 맞춘다.

적용한 기록은 스키마마다 `migrations` 테이블에 남는다.

| 테이블 | 내용 |
| --- | --- |
| `boards` | 게시판. 주소의 이름(`slug`), 보이는 이름, 누가 쓰는가(`write_policy`), 차례 |
| `posts` | 글. 번호(순번), 게시판, 글쓴이의 ID(탈퇴했으면 비었다), 제목, 본문, 쓴 시각, 고친 시각, 지운 시각 |
| `comments` | 댓글과 답글. 번호(순번), 글, 어느 댓글의 답글인가(`parent_id`), 글쓴이의 ID(탈퇴했으면 비었다), 내용, 쓴 시각, 고친 시각, 지운 시각 |
| `authors` | 글쓴이의 닉네임. 사람마다 한 줄. 사람의 ID, 닉네임, 이름을 바꿔 적은 시각 |
| `reports` | 글과 댓글의 신고. 번호(순번), 글이나 댓글(둘 가운데 하나), 신고한 사람의 ID(탈퇴했으면 비었다), 사유, 설명, 신고한 시각, 처리한 시각·운영자·결과 |

`AllowWithdrawnAuthors`(탈퇴, #603)는 비운 글쓴이나 신고한 사람이 하나라도 있으면 되돌려지지 않는다. 그 자리에 넣을 번호를 이 서버는 모른다.

게시판은 마이그레이션이 넣는다(`SeedBoards`). 게시판을 더하려면 행을 넣는 새 마이그레이션을 만든다. 이미 적용된 마이그레이션 파일은 고치지 않는다.

## API

게시판 서버의 API는 `/api/v1/board/` 아래에 놓는다. 아래 표의 경로는 `/health` 둘을 빼고 모두 그 뒤에 붙는다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버가 살아 있는지 확인 | 불필요 |
| GET | `/health/ready` | 요청을 처리할 준비가 됐는지 확인(DB 에 닿는가). 닿지 않으면 503 | 불필요 |
| GET | `/me` | 토큰의 주인이 누구인지 확인. `{"user_id": "...", "is_operator": false}`. 운영자인지는 토큰의 `roles` 를 읽은 것이다 | 필요 |
| GET | `/boards` | 게시판 목록. 정해 둔 차례대로 | 불필요 |
| GET | `/boards/{slug}/posts` | 한 게시판의 글 목록. 새 글부터, 본문 없이. 첫 쪽에는 고정한 글을 따로 싣는다. `?page=1&size=20` | 불필요 |
| POST | `/boards/{slug}/posts` | 글 쓰기. `{"title", "content"}`. 201 과 쓴 글 | 필요 |
| GET | `/posts` | 글 검색. `?q=고정+버그`. 제목과 본문에서 찾는다. `&board=free&page=1&size=20` | 불필요 |
| GET | `/posts/{id}` | 글 하나를 본문까지 | 불필요 |
| PATCH | `/posts/{id}` | 글 고치기. 고칠 칸만 보낸다. 글쓴이만. 운영자만 쓰는 게시판의 글은 지금 운영자인 글쓴이만 | 필요 |
| DELETE | `/posts/{id}` | 글 지우기. 글쓴이와 운영자. 운영자만 쓰는 게시판의 글은 운영자만. 204 | 필요 |
| PUT | `/posts/{id}/pin` | 글 고정하기. `{"days": 7}`(적지 않으면 7일, 365일까지). 운영자만. 204 | 필요 |
| DELETE | `/posts/{id}/pin` | 글의 고정 풀기. 운영자만. 204 | 필요 |
| GET | `/posts/{id}/comments` | 한 글의 댓글 목록. 먼저 쓴 것부터, 답글을 붙여서. `?after=57&size=20` | 불필요 |
| POST | `/posts/{id}/comments` | 댓글 쓰기. `{"content"}`. 답글이면 `{"content", "parent_id"}`. 201 과 쓴 댓글 | 필요 |
| PATCH | `/comments/{id}` | 댓글 고치기. `{"content"}`. 글쓴이만 | 필요 |
| DELETE | `/comments/{id}` | 댓글 지우기. 글쓴이와 운영자. 204 | 필요 |
| POST | `/posts/{id}/reports` | 글 신고하기. `{"reason", "description"}`. 201 | 필요 |
| POST | `/comments/{id}/reports` | 댓글(답글 포함) 신고하기. 201 | 필요 |
| GET | `/reports` | 열린 신고를 신고당한 것마다 묶은 목록. 오래 기다린 것부터. `?page=1&size=20`. 운영자만 | 필요 |
| GET | `/posts/{id}/reports` | 한 글에 걸린 신고 모두(처리한 것도). 최근 것부터, 설명과 신고한 사람까지. 운영자만 | 필요 |
| GET | `/comments/{id}/reports` | 한 댓글에 걸린 신고 모두. 운영자만 | 필요 |
| PUT | `/posts/{id}/reports/outcome` | 한 글에 걸린 열린 신고를 모두 닫기. `{"outcome": "actioned"}`. 운영자만. 204 | 필요 |
| PUT | `/comments/{id}/reports/outcome` | 한 댓글에 걸린 열린 신고를 모두 닫기. 운영자만. 204 | 필요 |
| POST | `/service/users/{userId}/withdrawal` | 탈퇴를 받는다. `{"withdrawn_at"}`. 200 `{"status": "processed"}`. 인증 서버만([탈퇴 받기](#탈퇴-받기)) | 인증 서버의 서명 |

`/health` 둘은 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다.

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
- `board`를 적으면 그 게시판에서만, 적지 않으면 모든 게시판에서 찾는다. 줄마다 어느 게시판의 글인지(`board`) 실린다.
- 댓글에서는 찾지 않는다. 지운 글은 나오지 않는다.
- 검색 하나에 3초까지 쓴다. 넘으면 멈추고 503 으로 답한다.

제목은 100자, 본문은 20000자까지다. 제목의 앞뒤 빈칸은 떼고, 본문은 받은 그대로 저장한다.

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

넘기면 429 다. 가장 먼저 쓴 것이 그 시간을 벗어나면 하나를 더 쓸 수 있고, 그때까지 남은 초가 `retry_after`다. 같은 값이 `Retry-After` 머리말에도 실린다.
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
신고 하나하나(설명, 신고한 사람)는 `GET /posts/{id}/reports`, `GET /comments/{id}/reports`로 본다. 처리한 신고도 나온다.

```json
{ "id": "9", "reason": "other", "description": "설명", "reporter_id": "7d0e3a52-...", "created_at": "...", "handled_at": null, "handled_by": null, "outcome": null }
```

처리(`PUT .../reports/outcome`)는 그것에 걸린 열린 신고를 한 번에 모두 닫는다. 결과(`outcome`)는 `actioned`(조치함)나 `dismissed`(문제없음)다.
처리한 시각과 운영자가 함께 남는다. 닫은 뒤에 새 신고가 오면 다시 목록에 나온다. 열린 신고가 없으면 404 다.
글을 지우는 것은 처리와 따로, 지우기 API(`DELETE /posts/{id}`)로 한다. 지운 것에 걸린 신고도 처리해야 목록에서 빠진다.

**오류는 언제나 `{"detail": "문장"}`이다.** 다른 서버들과 같은 칸 이름이다. 입력이 틀렸을 때는 어느 칸이 왜 틀렸는지를 `errors`에 더한다.

```json
{ "detail": "입력이 올바르지 않습니다.", "errors": { "title": ["제목을 적어야 합니다."] } }
```

| 상태 | 언제 |
| --- | --- |
| 400 | 입력이 틀렸다. 모르는 칸을 보냈다. 고칠 칸을 하나도 보내지 않았다. JSON 이 깨졌다. 답글을 달 댓글이 없거나 그것이 답글이다 |
| 401 | 로그인이 필요한데 토큰이 없거나 받아들일 수 없다 |
| 403 | 운영자만 쓰는 게시판에 썼다. 남의 글이나 댓글을 고치거나 지우려 했다. 운영자에서 내려온 뒤에 운영자만 쓰는 게시판의 제 글을 고치거나 지우려 했다. 자기 글이나 댓글을 신고했다. 운영자가 아닌데 신고를 읽거나 처리하려 했다 |
| 404 | 없는 게시판, 없는 글, 없는 댓글, 지운 것, 없는 주소. 처리할 신고가 없다 |
| 409 | 한 댓글에 달 수 있는 답글이 다 찼다. 한 게시판에 고정할 수 있는 글이 다 찼다. 이미 신고했다 |
| 429 | 글이나 댓글을 너무 자주 썼다. 신고를 너무 자주 했다. `retry_after`(초)와 `Retry-After` 머리말이 기다릴 시간이다 |
| 500 | 서버의 잘못. 무슨 일인지는 응답에 싣지 않고 로그에 남긴다 |
| 503 | 검색이 정해 둔 시간(3초)을 넘겨 멈췄다. 인증 서버의 공개키를 구하지 못했다(아래) |

**API 는 기본으로 로그인이 필요하다.** 로그인 없이 열어 둘 API 에만 `@Public()`을 붙인다. 토큰은 `Authorization: Bearer <access 토큰>` 머리말로 보낸다.

| 상태 | 언제 | 응답 |
| --- | --- | --- |
| 401 | 토큰이 없거나 받아들일 수 없다 | `{"detail": "인증이 필요합니다."}`, `WWW-Authenticate: Bearer` |
| 503 | 인증 서버의 공개키를 구하지 못해 확인할 수 없다 | `{"detail": "지금은 인증을 확인할 수 없습니다. ..."}`, `Retry-After: 60` |

401 은 왜 틀렸는지 알리지 않는다. 만료든 서명이 틀렸든 응답이 같다. 클라이언트는 401 이면 토큰을 갱신하고, 503 이면 로그아웃시키지 않고 잠시 뒤 다시 부른다.
게임 서버와 같은 응답이다.

### API 목록(OpenAPI)

화면의 타입과 디자인 도구에 넘기는 API 목록은 [`docs/api/board.openapi.json`](../docs/api/board.openapi.json)이다(#559, [API 목록](../docs/api/README.md)).
코드에서 뽑는다. 손으로 고치지 않는다. API 를 바꾸면 저장소 루트에서 다시 뽑아 함께 커밋한다. 빠뜨리면 CI 의 `api-docs` 가 실패한다.

```
# board-server 에서 npm ci 를 해 둔 뒤, 저장소 루트에서
uv run --no-project python tools/export_openapi.py board
```

도구는 이 서버의 `npm run --silent openapi` 를 부른다. 빌드한 뒤(`nest build`) 앱을 미리 보기로 만들어 목록을 JSON 으로 낸다(`src/openapi/export.ts`).
서버를 띄우지 않고 DB 에도 닿지 않는다. 서버는 `/docs` 를 열지 않는다. 바깥에 나가는 목록은 저장소의 파일뿐이다.

목록이 맞으려면 코드를 이렇게 쓴다.

- **응답의 모양은 `*.response.ts` 의 클래스로 적는다.** 인터페이스는 빌드에서 사라져 목록에 칸이 빠진다.
  `@nestjs/swagger` 의 플러그인이 빌드할 때 `*.dto.ts`, `*.query.ts`, `*.response.ts` 의 클래스에서 칸의 타입과 `/** */` 주석을 읽는다(`nest-cli.json`).
  컨트롤러의 반환 타입은 응답으로, 메서드의 주석은 요약으로 실린다.
- **제네릭은 읽지 못한다.** `Page<Item>` 을 그대로 돌려주면 `items` 가 무엇의 목록인지 빠진다. 항목마다 클래스를 둔다
  (`PostSummaryPageResponse` 처럼 `PageFields`(`posts/page.response.ts`)를 이어받고 `Page<Item>` 을 implements 한다).
- **로그인 없이 부르는 API** 는 `@Public()` 이 목록에도 그렇게 적는다. 목록은 기본으로 bearer 토큰이 필요하다고 적는다.
- **운영자의 API** 는 컨트롤러에 `@ForOperators()` 를 붙인다(`src/openapi/audience.ts`). 주소에 `/admin/` 이 없어서 도구가 주소로 알 수 없다.
  표시는 목록에만 쓰인다. 운영자만 부르게 막는 것은 서비스가 한다.
- 기본값이 있는 입력(`page`, `size`, `days`)은 적지 않아도 되는 것으로, 모든 API 의 오류는 `ErrorBody` 로 목록에 적힌다(`src/openapi/document.ts`).

## 알림 보내기

내 글에 댓글이 달리거나 내 댓글에 답글이 달리면 그 사람의 알림함에 알린다(#385, `src/notifications/`). 알림함은 알림 서버에 있다([알림 서버의 README](../notification-server/README.md)).

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
- 서명은 결제 서버를 부를 때와 같은 모양이다(`src/service-auth/signing.ts`). 주소는 `POST /api/v1/notification/service/board/notifications` 다.

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `NOTIFICATION_URL` | 없음(보내지 않음) | 알림 서버의 주소. `http://127.0.0.1:8004`. 비우면 발송함에 적기만 한다(7일이 지나면 지워진다) |
| `NOTIFICATION_SECRET` | 없음 | 요청에 서명하는 비밀. 알림 서버의 `BOARD_SERVER_SECRET` 과 같은 값, 32자 이상. `NOTIFICATION_URL` 을 적었으면 없을 때 서버가 뜨지 않는다. 비밀값이다 |

**알림 서버와 붙여 보기.** 알림 서버가 떠 있어야 한다. 비밀을 하나 만들어 두 파일에 함께 넣는다. **저장소 루트에서** 실행한다. 값은 화면에 찍히지 않는다.
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

인증 서버는 탈퇴를 요청하고 7일(유예)이 지난 계정을 비운 뒤 서버마다 알린다(#603, [탈퇴 설계](../docs/architecture/withdrawal.md)). 이 서버는 그 사람의 것을 정리한다(`src/withdrawals/`).

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
| 400 | 주소의 `userId` 가 UUID 가 아니다, `withdrawn_at` 이 없거나 시간대가 있는 ISO 8601 시각이 아니다, 모르는 칸이 있다 |
| 401 | 서명이 없거나 맞지 않다. 사용자의 토큰으로는 부를 수 없다. `AUTH_SERVER_SECRET` 이 비어 있으면 모두 401 이다 |

- **번호를 남기지 않는 까닭.** 응답의 `author_id` 는 누구나 본다. 남기면 탈퇴한 사람의 글을 한데 모을 수 있다. 그래서 비운다
- **비운 뒤.** 그 글과 댓글은 누구의 것도 아니다. 고칠 사람이 없고 운영자만 지운다. 누구나 신고한다. 달린 댓글과 답글은 알리지 않는다
- **한 트랜잭션이다.** 몇 번을 받아도 같다. 인증 서버는 200 과 `processed` 를 받을 때까지 다시 보낸다
- **서명은 받은 바이트 그대로에 확인한다.** 그래서 앱이 본문의 바이트를 남긴다(`main.ts` 의 `rawBody`). 경로는 앞부분(`/api/v1/board`)을 포함한다.
  확인하는 코드는 알림 서버에 보낼 때 서명하는 코드와 같은 파일이다(`src/service-auth/signing.ts`). 시각이 앞뒤 5분을 넘긴 서명은 받지 않는다
- SQL 을 직접 적는다(`withdrawals.service.ts`). TypeORM 의 `update` 는 고친 시각을 함께 바꾼다. 글쓴이를 비운 것은 글을 고친 것이 아니다
- 로그에는 정리한 수만 남긴다(`operation`: `board.withdrawal`, `blanked_posts`, `blanked_comments`, `blanked_reports`, `deleted_authors`, `deleted_notifications`). 사람은 남기지 않는다

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `AUTH_SERVER_SECRET` | 없음(받지 않음) | 인증 서버의 서명을 확인하는 비밀. 인증 서버의 `BOARD_SECRET` 과 같은 값, 32자 이상. 짧으면 서버가 뜨지 않는다. 비우면 탈퇴의 알림을 401 로 거절한다(인증 서버는 쌓아 두었다가 적은 뒤에 다시 보낸다). 비밀값이다 |

`tools/fill_env.py` 가 두 파일(`auth-server/.env` 의 `BOARD_SECRET`, `board-server/.env` 의 `AUTH_SERVER_SECRET`)에 같은 값을 채운다.

## 구조

```
src/
  main.ts                        서버를 띄우는 시작점
  app.module.ts                  이 서버를 이루는 모듈들을 모은다
  app.setup.ts                   주소의 앞부분 같은, 앱에 거는 규칙
  config/environment.ts          환경 변수를 검사해 설정으로 바꾼다
  auth/
    jwks.ts                      인증 서버의 공개키를 가져오고 기억한다
    session-revocations.ts       인증 서버가 내주는 끊긴 세션의 목록을 받고 기억한다
    session-revocations.refresher.ts  그 목록을 30초마다 받는다. 앱이 뜨면 시작하고 닫히면 멈춘다
    tokens.ts                    토큰을 검증하는 규칙
    roles.ts                     토큰의 역할(roles)에서 운영자인지 읽는 규칙
    actor.ts                     요청한 사람(ID 와 운영자인지). 서비스가 받는 모양
    bearer.ts                    Authorization 머리말에서 토큰을 꺼낸다
    token-verifier.ts            검증의 규칙에 이 앱의 설정과 키 저장소를 물린 서비스. 끊긴 세션의 토큰도 거부한다
    auth.guard.ts                문지기. 요청마다 토큰을 검증하고 결과를 응답으로 바꾼다
    public.decorator.ts          @Public(). 로그인 없이 부를 수 있다는 표시
    current-user.decorator.ts    @CurrentUser(). 토큰의 주인을 컨트롤러의 인자로 받는다
    auth.module.ts               위의 것들을 묶고 문지기를 앱 전체에 건다
  me/                            토큰의 주인을 돌려주는 API
  errors/
    error-body.ts                오류 응답의 모양({ detail })을 정한다
    all-exceptions.filter.ts     예외를 오류 응답으로 바꾼다. 앱 전체에 건다
    validation.ts                입력을 DTO 의 규칙대로 검사한다. 앱 전체에 건다
  boards/
    board.entity.ts              boards 테이블
    boards.service.ts            게시판을 읽는다
    boards.controller.ts         게시판 목록의 API
    board.response.ts            게시판을 응답의 모양으로 바꾼다
    board-slug.pipe.ts           주소의 게시판 이름을 검사한다
  posts/
    post.entity.ts               posts 테이블
    create-post.dto.ts           글을 쓸 때 받는 값의 규칙
    update-post.dto.ts           글을 고칠 때 받는 값의 규칙
    list-posts.query.ts          글 목록을 부를 때 주소에 붙이는 값의 규칙
    posts.policy.ts              누가 쓰고 고치고 지울 수 있는가
    posts.service.ts             글을 읽고, 쓰고, 고치고, 지운다
    posts.controller.ts          글의 API
    post.response.ts             글을 응답의 모양으로 바꾼다
    page.ts                      목록을 쪽으로 나누는 셈
    page.response.ts             쪽의 칸(page, size, total). 목록의 응답 클래스들이 이어받는다
    post-id.pipe.ts              주소의 글 번호를 검사한다
    posts.errors.ts              글을 다루다 거절할 때의 응답들
    pins.policy.ts               누가 고정하는가, 몇 개까지인가, 언제 끝나는가
    pins.service.ts              글을 고정하고, 풀고, 고정한 글을 읽는다
    pins.controller.ts           글 고정의 API
    pin-post.dto.ts              글을 고정할 때 받는 값의 규칙
    search.ts                    검색어를 낱말로 나누고 LIKE 의 모양으로 바꾸는 셈
    search-posts.query.ts        글을 검색할 때 주소에 붙이는 값의 규칙
    posts-search.service.ts      글을 검색한다
    posts-search.controller.ts   글 검색의 API
  comments/
    comment.entity.ts            comments 테이블. 댓글과 답글을 함께 둔다
    create-comment.dto.ts        댓글을 쓸 때 받는 값의 규칙
    update-comment.dto.ts        댓글을 고칠 때 받는 값의 규칙
    list-comments.query.ts       댓글 목록을 부를 때 주소에 붙이는 값의 규칙
    comments.policy.ts           누가 고치고 지울 수 있는가, 어디에 답글을 달 수 있는가
    comments.service.ts          댓글을 읽고, 쓰고, 고치고, 지운다
    comments.controller.ts       댓글의 API
    comment.response.ts          댓글을 응답의 모양으로 바꾼다
    threads.ts                   댓글과 답글을 묶는다
    slice.ts                     목록을 "이것 다음 몇 개"로 끊어 읽는 셈
    comment-id.pipe.ts           주소의 댓글 번호를 검사한다
    comments.errors.ts           댓글을 다루다 거절할 때의 응답들
  comment-counts/
    comment-counts.service.ts    글에 달린 댓글의 수를 센다
    counts.ts                    글 번호로 댓글 수를 찾는 셈
    comment-counts.module.ts     글 모듈이 가져다 쓴다. 댓글 모듈과 따로 둔다
  authors/
    author.entity.ts             authors 테이블. 사람마다 닉네임 한 줄
    nickname.ts                  토큰의 닉네임을 받아들일지 정한다
    nicknames.ts                 사용자 ID 로 닉네임을 찾는 표
    recent-nicknames.ts          최근에 적은 닉네임을 메모리에 기억한다
    authors.service.ts           닉네임을 적어 두고 읽는다
    authors.interceptor.ts       로그인한 요청마다 토큰의 닉네임을 적어 둔다. 앱 전체에 건다
    authors.module.ts            글 모듈과 댓글 모듈이 가져다 쓴다
  write-limits/
    write-limits.policy.ts       글과 댓글을 얼마나 자주 쓸 수 있는가, 신고를 얼마나 자주 할 수 있는가
    write-limits.service.ts      최근에 쓴 것과 한 신고를 세어 한도를 넘었는지 본다
    write-limits.errors.ts       한도에 걸렸을 때의 응답들
    write-limits.module.ts       글, 댓글, 신고 모듈이 가져다 쓴다
  reports/
    report.entity.ts             reports 테이블. 글의 신고와 댓글의 신고를 함께 둔다
    reports.policy.ts            사유와 처리 결과, 누가 무엇을 신고할 수 있는가
    report-target.ts             신고하는 것(글이나 댓글)을 가리키는 값
    create-report.dto.ts         신고할 때 받는 값의 규칙
    handle-reports.dto.ts        처리할 때 받는 값의 규칙
    list-reports.query.ts        신고 목록을 부를 때 주소에 붙이는 값의 규칙
    reports.service.ts           신고한다(신고한 사람의 쪽)
    reports.controller.ts        신고하기의 API
    report-reviews.service.ts    신고를 묶어 읽고 처리한다(운영자의 쪽)
    report-reviews.controller.ts 운영자의 API
    open-groups.ts               열린 신고를 신고당한 것마다 묶은 것
    report.response.ts           신고를 응답의 모양으로 바꾼다
    reports.errors.ts            신고를 다루다 거절할 때의 응답들
  ids/record-id.ts               순번으로 매긴 번호의 모양
  observability/
    identifiers.ts               요청, 작업, 추적의 식별자를 받아들이고 만드는 규칙
    request-context.ts           요청이나 작업이 도는 동안 식별자를 들고 있는 곳
    redaction.ts                 로그에 적히기 직전에 민감한 값을 가린다
    json-logger.ts               Nest 의 로그를 공통 규격의 JSON 한 줄로 내보낸다
    logger.factory.ts            설정으로 로거를 만든다
    request-logging.middleware.ts  요청마다 식별자를 걸고, 끝나면 한 줄을 남긴다
    spans.ts                     span 을 만들고 읽는 곳(OpenTelemetry 의 API)
    tracing.ts                   span 을 수집기에 미는 것(SDK)을 만들고 끈다
    request-spans.middleware.ts  요청마다 서버 span 을 건다
    http-spans.ts                다른 서버를 부르는 fetch 에 client span 을 건다
    db-spans.ts                  쿼리마다 span 을 거는 pg 의 연결
    jobs.ts                      작업 한 바퀴에 span 과 job_id 를 건다
    idle-rounds.ts               할 일이 없던 작업의 추적을 보내지 않는다
    metrics.ts                   메트릭의 계측기와, 수집기에 미는 것(SDK)을 만들고 끈다
    request-metrics.middleware.ts  요청마다 HTTP 메트릭 셋을 센다
    pool-metrics.ts              연결을 기다린 시간을 재는 pg 의 풀
    counted.interceptor.ts       글과 댓글을 쓴 것, 신고한 것을 결과마다 센다
    observability.module.ts      앱이 닫힐 때 모아 둔 span 과 메트릭을 보낸다
  database/
    database.options.ts          설정을 연결 옵션으로 바꾼다. 서버와 마이그레이션 도구가 함께 쓴다
    database.module.ts           서버의 DB 연결
    database.health.ts           DB 에 닿는지 확인한다
    pool-watch.ts                앱이 뜨면 연결 풀을 메트릭으로 내보내기 시작한다
    data-source.ts               마이그레이션 도구가 읽는 연결
  notifications/                 사용자의 알림함(알림 서버)에 넣기(#385)
    notices.ts                   새 댓글을 누구에게 무슨 알림으로 보낼지 정한다. DB 를 모른다
    outgoing-notification.entity.ts  발송함의 한 줄
    outbox.ts                    부른 쪽의 트랜잭션에서 발송함에 적는다
    notification-client.ts       알림 서버를 부르고 답을 보냈다·다시 보낸다·받지 않았다로 가른다
    notification-dispatcher.ts   한 바퀴: 오래된 것을 지우고, 차례가 된 것을 보내고, 결과를 적는다
    notification-dispatcher.runner.ts  그 바퀴를 5초마다 돌린다. 앱이 뜨면 시작하고 닫히면 멈춘다
    notifications.module.ts      위의 것들을 묶는다. 주소가 없으면 보내는 것이 없다
  service-auth/
    signing.ts                   우리 서버끼리의 요청에 서명한다(알림 서버에 보낼 때). 받은 요청의 서명을 확인한다(탈퇴)
  withdrawals/                   인증 서버가 알린 탈퇴를 받는다(#603)
    auth-server.guard.ts         인증 서버가 서명한 요청만 들여보낸다(AUTH_SERVER_SECRET)
    withdrawal.dto.ts            본문(withdrawn_at)
    withdrawals.service.ts       한 트랜잭션: 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 발송함을 지운다
    withdrawals.controller.ts    POST /service/users/:userId/withdrawal
  health/                        살아 있는지, 준비됐는지 확인하는 API
  openapi/                       API 목록(OpenAPI, #559)
    document.ts                  목록을 만든다. 기본값이 있는 입력과 오류의 모양을 더한다
    audience.ts                  @ForOperators(). 운영자의 API 라는 목록의 표시
    export.ts                    목록을 JSON 으로 표준 출력에 낸다(npm run openapi)
  migrations/                    마이그레이션 파일
test/
  setup.ts                       테스트의 환경 변수를 맞춘다(DB 주소, 테스트용 스키마, 닿지 않는 공개키 주소)
  app.ts                         테스트용 앱을 만든다
  tokens.ts                      테스트가 직접 만든 키로 토큰을 서명한다
  logs.ts                        서버의 로그를 화면 대신 모은다. 일부러 5xx 를 만드는 테스트가 쓴다
  data.ts                        테스트용 스키마의 글, 댓글, 신고, 닉네임을 비우고 채운다. 운영자를 넣고 뺀다
  *.e2e-spec.ts                  앱을 통째로 만들어 부르는 테스트
```

Nest 의 말을 다른 서버의 말로 옮기면 이렇다.

| Nest | 하는 일 | 게임 서버(FastAPI)에서 닮은 것 |
| --- | --- | --- |
| 모듈(`*.module.ts`) | 기능 하나에 어떤 컨트롤러와 서비스가 있는지 적은 목록 | 기능별 폴더와, 라우터를 앱에 붙이는 줄 |
| 컨트롤러(`*.controller.ts`) | 주소를 받아 서비스를 부른다 | `router.py` |
| 서비스(`*.service.ts`) | 실제 일을 한다 | `service.py` |
| 엔티티(`*.entity.ts`) | 테이블 하나의 모양 | SQLAlchemy 의 모델 |
| 의존성 주입 | 생성자에 적은 타입을 보고 Nest 가 넣어 준다 | `Depends(...)` |
| DTO(`*.dto.ts`) | 요청으로 받는 값의 모양과 규칙 | Pydantic 모델 |
| 파이프(`*.pipe.ts`) | 컨트롤러에 넘기기 전에 값을 검사하고 바꾼다 | 인자의 타입과 `Query(...)` |
| 필터(`*.filter.ts`) | 예외를 응답으로 바꾼다 | `add_exception_handler` |
| 가드(`*.guard.ts`) | 요청이 컨트롤러에 닿기 전에 들여보낼지 정한다 | `Depends(get_current_user)` |
| 인터셉터(`*.interceptor.ts`) | 가드를 지난 요청에 컨트롤러 앞뒤로 일을 하나 더 건다 | 모든 경로에 거는 `Depends` |
| 데코레이터(`@Public()`, `@CurrentUser()`) | 컨트롤러와 인자에 붙이는 표시 | `CurrentUser` 타입 |

## 로그와 요청 식별자

네 서버가 같은 규격으로 로그를 남긴다. 규격의 전부는 [docs/observability.md](../docs/observability.md)에 있다. 여기는 이 서버에서 알아 둘 것만 적는다.

- 로그는 표준 오류(stderr)에 **한 줄에 JSON 하나**로 나간다. 모든 줄에 `timestamp`, `level`, `service`(`board-server`), `environment`, `version`, `message` 가 있다.
- 요청마다 식별자가 붙는다. 요청의 `X-Request-ID` 머리말이 영문자, 숫자, `.`, `_`, `-` 로 된 8~64자면 그대로 쓰고, 아니면 새 UUID 로 바꾼다.
  정한 값은 **모든 응답의 `X-Request-ID` 머리말**로 돌려준다. 오류가 났을 때 이 값으로 로그를 찾는다.
- 요청이 끝나면 한 줄이 남는다. 주소는 실제 값이 아니라 틀로 적는다(`/api/v1/board/posts/:id`). 머리말, 주소 뒤에 붙은 값, 본문은 적지 않는다.
- 4xx 는 `info`, 5xx 는 `error` 다. 처리하지 못한 예외는 호출 기록과 함께 로그에만 남고, 응답에는 정해진 말과 `X-Request-ID` 만 간다.
- 비밀번호, 토큰, 이메일 주소 같은 값은 로그에 넘기지 않는다. 실수로 넘겨도 나가기 직전에 한 번 더 가린다(이름이 `password`, `token` 같은 칸, 글 속의 JWT 와 이메일의 모양).
- 식별자는 로그를 찾는 데만 쓴다. 누구의 요청인지는 토큰만이 말한다.

| 환경 변수 | 기본값 | 뜻 |
| --- | --- | --- |
| `APP_ENVIRONMENT` | `development` | 환경의 이름. 로그의 `environment` 칸. 운영에서는 `production` |
| `APP_VERSION` | `dev` | 배포한 코드의 버전. 로그의 `version` 칸. 운영에서는 git SHA 나 이미지 태그 |
| `LOG_LEVEL` | `info` | 이 수준부터 남긴다. `debug`, `info`, `warning`, `error` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | 비어 있음(보내지 않음) | span 과 메트릭을 OTLP(HTTP)로 미는 수집기(Alloy)의 주소. `http://alloy:4318` 처럼 경로 없이 적는다([추적](#추적), [메트릭](#메트릭)) |
| `OTEL_METRIC_EXPORT_INTERVAL` | `15000` | 메트릭을 보내는 간격(밀리초, 1000 이상). 다른 서버와 같은 이름이다 |

다섯 값 모두 비밀이 아니다. 모양이 틀리면 서버가 뜨지 않는다. 모든 로그 줄에 실리는 값이라 줄바꿈이나 따옴표가 든 값을 받지 않는다.

개발할 때 줄이 읽기 불편하면 `jq` 로 본다. JSON 이 아닌 줄(프레임워크가 뜰 때 찍는 안내)은 건너뛴다.

```bash
npm run start:dev 2>&1 | jq -rR 'fromjson? | [.timestamp, .level, .message, .route // "", .status_code // ""] | @tsv'
```

**이 서버에서 다른 것.**

- Nest 의 로거(`new Logger('이름')`)로 남긴 줄이 그대로 이 모양으로 나간다. `log` 는 `info`, `warn` 은 `warning`, `fatal` 은 `critical`, `verbose` 는 `debug` 다.
  칸을 더 실으려면 글 대신 객체를 넘긴다: `logger.warn({ message: '…', operation: 'post.create', post_id: id })`.
- 인증 서버에서 공개키를 받을 때와 알림 서버에 알림을 보낼 때 `traceparent` 머리말로 추적을 이어 준다. 두 서버의 로그가 같은 `trace_id` 로 묶인다.
- 발송함의 알림을 보내는 한 바퀴는 작업이다. 그 바퀴의 줄에는 `request_id` 대신 `job_id` 가 붙는다. 바퀴마다 새 값이다.
- 설정이 틀려 서버가 뜨지 못할 때의 줄은 Nest 의 기본 모양(글)으로 나온다. 로거는 설정을 읽은 뒤에 만들어진다.
- 테스트는 `warn` 이상만 Nest 의 기본 모양으로 찍는다(`test/app.ts`). 로그의 모양을 보는 테스트(`test/observability.e2e-spec.ts`)는 서버와 같은 로거를 꽂아 나간 줄을 모은다.

## 추적

요청, 다른 서버를 부르는 것, 쿼리, 알림을 보내는 작업을 span 으로 남겨 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 민다. 수집기가 Tempo 에 넘긴다.
규칙과 까닭은 [관측 규격](../docs/observability.md)의 "3. 추적"에 있다. 이 서버에서 다른 것은 "붙인 것 (게시판 서버의 추적)"에 있다.
주소가 비어 있으면 span 이 생기지 않고 로그는 지금과 같다. 테스트는 span 을 메모리에 모은다(`test/spans.ts`).

| span | 이름 | 코드 |
| --- | --- | --- |
| 요청 | `GET /api/v1/board/posts/:id`(메서드와 경로의 틀). 상태 확인은 걸지 않는다 | `src/observability/request-spans.middleware.ts` |
| 다른 서버를 부르는 것 | `HTTP GET`(공개키), `HTTP POST`(알림 서버) | `src/observability/http-spans.ts` |
| 쿼리 | `db SELECT posts`(종류와 첫 테이블) | `src/observability/db-spans.ts` |
| 알림을 보내는 작업 | `notification.send`. 한 바퀴가 새 추적 하나다 | `src/observability/jobs.ts` |

- 로그의 `trace_id` 가 span 의 trace id 와 같다. 요청의 span 에는 `request_id`, 작업의 span 에는 `job_id` 를 싣는다
- 싣지 않는 것: 주소의 경로와 뒤의 값, 머리말, 본문, SQL 의 문장과 값, 예외의 글. 쿼리가 실패하면 SQLSTATE 만 적는다
- 요청이나 작업 밖의 쿼리와 호출(끊긴 세션의 목록을 30초마다 받는 것)은 span 을 걸지 않는다
- 보낼 알림이 없던 바퀴(처리한 수 `handled` 가 0 이고 실패하지 않은 것)는 그 추적을 통째로 보내지 않는다(`src/observability/idle-rounds.ts`)
- 받은 `traceparent` 가 "기록하지 않음"(flags `00`)이어도 남긴다
- 끄라는 신호(SIGTERM)를 받으면 앱을 닫으며 모아 둔 span 을 보낸다(`main.ts` 의 `enableShutdownHooks`, 5초 안)

## 메트릭

요청, DB, 쓰기와 신고, 검색, 알림을 보내는 작업을 세어 `OTEL_EXPORTER_OTLP_ENDPOINT` 로 15초마다 민다. 수집기가 Prometheus 에 넘긴다.
이름과 label 은 [관측 규격](../docs/observability.md)의 "메트릭"에 있다. 이 서버에서 다른 것은 "붙인 것 (게시판 서버의 메트릭)"에 있다.
주소가 비어 있으면 세기만 하고 보내지 않는다. 테스트는 메모리에 모은다(`test/metrics.ts`).

| 메트릭 | label | 세는 곳 |
| --- | --- | --- |
| `http_server_requests_total`, `http_server_request_duration_seconds`, `http_server_active_requests` | `method`, `route`(경로의 틀), `status_code` | `src/observability/request-metrics.middleware.ts`. 미들웨어의 맨 앞이다 |
| `db_up` | 없음 | `src/health/readiness.controller.ts`. 준비 상태 확인이 본 DB |
| `db_pool_connections`, `db_pool_connections_max`, `db_pool_wait_seconds` | `state`(`idle`, `in_use`) | `src/observability/pool-metrics.ts`, `src/database/pool-watch.ts`. 풀은 10 이다 |
| `background_jobs_started_total`, `background_jobs_finished_total`, `background_jobs_running`, `background_job_duration_seconds` | `operation`(`notification.send`), `result` | `src/observability/jobs.ts` 의 `runAsJob`. 할 일이 없던 바퀴도 센다 |
| `board_writes_total` | `resource`(`post`, `comment`), `action`(`create`, `update`, `delete`), `result`(`success`, `rejected`, `rate_limited`) | `src/observability/counted.interceptor.ts`. 컨트롤러의 핸들러에 붙인다 |
| `board_reports_total` | `target`(`post`, `comment`), `result` | 같은 인터셉터 |
| `board_searches_total`, `board_search_duration_seconds` | `result`(`success`, `timeout`) | `src/posts/posts-search.service.ts` |

- 결과는 핸들러가 끝난 모양이다. 답을 돌려줬으면 `success`, 429 면 `rate_limited`, 그 밖의 4xx(모양, 권한, 없는 것, 이미 신고함)면 `rejected` 다. 5xx 는 세지 않는다(요청 수의 5xx 로 본다)
- 로그인하지 않은 쓰기(401)는 가드에서 끝나 쓰기로 세지 않는다
- 연결을 기다린 시간은 pg 의 풀이 꺼내는 자리(`connect`)를 감싸 잰다. TypeORM 에 Pool 만 바꾼 pg 를 넘긴다(`driver`)
- 대시보드는 Grafana 의 `board-server`(`docker/grafana/dashboards/board-server.json`), 경보는 `docker/prometheus/rules/ai-trpg.yml` 의 `board-server` 묶음이다
- 끄라는 신호(SIGTERM)를 받으면 앱을 닫으며 모아 둔 값을 한 번 보낸다(span 과 함께)


## CI

PR과 `main` 푸시마다 GitHub Actions가 게시판 서버를 검사한다. `board-server/`, DB 초기화 스크립트, 워크플로 파일이 바뀐 경우에만 돈다.
실제 PostgreSQL을 띄우고, 로컬과 같은 초기화 스크립트로 계정과 스키마를 만든다.

1. 의존성 설치 (`npm ci`): `package-lock.json`과 `package.json`이 어긋나면 실패한다
2. 린트 (`npm run lint`)
3. 모양 검사 (`npm run format:check`): 고치지 않고 검사만 한다
4. 의존성 취약점 검사 (`npm audit --omit=dev --audit-level=high`): 운영에 들어가는 의존성(devDependencies 제외)에 높음 이상의 알려진 취약점이 있으면 실패한다
5. 빌드 (`npm run build`): 타입 검사를 겸한다
6. 마이그레이션 적용 (`npm run migration:run`): 빈 DB 에 처음부터 끝까지 적용되는지 본다
7. 마이그레이션 누락 검사 (`npm run migration:check`): 엔티티를 바꾸고 마이그레이션을 만들지 않았으면 실패한다
8. 테스트용 스키마에 마이그레이션 적용
9. 테스트 (`npm run test:cov`, `npm run test:e2e:cov`): 두 테스트를 돌리며 지나간 줄을 따로 센다
10. 계약 시험 (`contract/` 의 `uv run pytest`): 빌드한 서버를 띄워 HTTP 로만 부른다. 그 전에 ruff 의 린트와 모양 검사를 한다
11. 커버리지 요약: 두 테스트의 합계를 작업 요약(Summary)에 적는다
12. 커버리지 기준: 줄 비율이 단위 60%, 앱 90% 아래면 실패한다(워크플로의 `UNIT_COVERAGE_MIN`, `E2E_COVERAGE_MIN`, 처음 잰 값은 62.3%, 92.7%). 단위 테스트는 DB 를 쓰는 코드를 지나지 않아 둘을 따로 본다. 기준은 처음 잰 값보다 조금 낮게 잡았다. 커버리지가 오르면 기준도 올리고, 내릴 때는 PR 에 까닭을 적는다.

## 설계 메모

**설정은 `@nestjs/config`로 읽고, 뜰 때 검사한다.** `.env`와 환경 변수를 읽어 검사 함수(`config/environment.ts`)에 넘긴다.
값이 틀리면 앱을 만드는 데서 예외가 나고 프로세스가 끝난다. 틀린 설정으로 떠서 요청을 받다가 실패하지 않는다.
검사 함수는 Nest 를 모르는 순수한 함수라 따로 테스트한다. 꺼내 쓰는 쪽은 `ConfigService<Environment, true>`로 받아서, 없는 이름을 꺼내면 컴파일러가 잡는다.
`.env`는 다른 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
예외의 글에 받은 값을 싣지 않는다. DB 주소에는 비밀번호가 들어 있다.

**토큰은 인증 서버의 공개키로 검증만 한다.** 회원가입과 로그인은 인증 서버의 일이다. 이 서버는 인증 서버의 DB 를 보지 않고, 요청마다 인증 서버에 묻지도 않는다.
서명 방식(RS256), 서명, 만료(`exp`), 발급자(`iss`), 대상(`aud`), 토큰의 종류(`token_type`이 `access`)를 본다. 게임 서버와 같은 규칙이다(`trpg-server/app/auth/`).
요청마다 인증 서버에 묻지 않으므로, 세션이 끊긴 것은 따로 받은 목록으로 안다(아래의 "끊긴 세션은 목록으로 안다").
서명 방식은 코드에 하나만 적는다. 토큰의 머리말에 적힌 방식을 믿으면 서명이 없는 토큰(`none`)이나 공개키를 비밀키처럼 써서 만든 토큰(`HS256`)이 통과한다.

**끊긴 세션은 목록으로 안다(#274).** 인증 서버에서 세션을 끊어도(비밀번호 변경, 계정 정지) 이 서버는 토큰만 보므로 그 access 토큰을 만료(15분)까지 받았다.
인증 서버가 끊긴 세션의 목록(`/api/v1/auth/session-revocations`)을 내주고, 이 서버가 30초마다 받아 기억한다(`auth/session-revocations.ts`). 결제 서버와 같은 규칙이다.
- 목록의 줄은 사용자(`sub` 의 SHA-256)와, 받아들이는 가장 낮은 세션 버전(`min_ver`)이다. 토큰의 세션 버전(`ver`, 없으면 0)이 그보다 낮으면 401 이다. 다른 틀린 토큰과 응답이 같다
- 끊은 뒤 30초쯤은 옛 토큰이 통한다. 요청마다 인증 서버에 묻지 않는 대가다. 다시 로그인해 받은 토큰은 버전이 올라 통한다
- 목록은 요청과 따로 받는다. 요청이 인증 서버를 기다리지 않는다. 앱이 뜨면 바로 한 번 받지만 기다리지 않는다. 인증 서버가 꺼져 있어도 이 서버는 뜬다
- 받지 못하면 마지막으로 받은 목록을 쓰고 경고(`error_code: auth.revocations_unavailable`, `reason` 에 종류)를 남긴다. 주소는 적지 않는다.
  한 번도 받지 못했으면 아무 세션도 끊긴 것으로 보지 않는다. 받지 못했다고 모든 토큰을 막으면 인증 서버가 잠깐 죽는 것으로 게시판 전체가 막힌다
- 한 줄이라도 모양이 틀리면 문서 전체를 받지 않는다. 틀린 줄만 건너뛰면 그 사용자의 끊긴 세션이 조용히 통한다. 문서는 8MB 까지만 읽는다

**토큰의 대상(`aud`)은 이 서버의 이름 하나다.** 인증 서버는 access 토큰 하나에 대상의 목록을 싣고, 서버마다 자기 이름(`ai-trpg-game`, `ai-trpg-board`, `ai-trpg-billing`)이 그 안에 있는지만 본다.
`JWT_AUDIENCE`에 쉼표로 여럿을 적으면 서버가 뜨지 않는다. 인증 서버의 목록을 그대로 옮겨 적은 실수를 뜰 때 잡는다.

**서명을 다루는 일은 `jose` 라이브러리에 맡기고, 키를 기억하는 규칙은 직접 적었다(`auth/jwks.ts`).** 암호를 직접 짜지 않는다.
`jose`에도 키를 기억하는 기능(`createRemoteJWKSet`)이 있지만, 기억한 키가 낡은 뒤 인증 서버가 죽어 있으면 토큰을 검증하지 못한다.
게임 서버와 같은 네 규칙으로 맞췄다: 한 시간이 지나면 다시 가져온다. 모르는 키 ID(`kid`)가 오면 다시 가져온다. 다시 가져오기는 60초에 한 번만 시도한다. 실패하면 기억하던 키를 계속 쓴다.
그래서 인증 서버가 잠깐 죽어도 이미 로그인한 사용자의 요청은 계속 처리하고, 가짜 `kid`를 쏟아부어도 인증 서버로 가는 요청은 60초에 한 번이다.
Nest 의 흔한 구성(`@nestjs/passport`와 `passport-jwt`, `jwks-rsa`)은 쓰지 않았다. 패키지 셋이 더 들고, 위의 규칙을 그 안에서 맞추기 어렵다.

**키를 구할 수 없으면 401 이 아니라 503 이다.** 기억한 키가 하나도 없는데 인증 서버에도 닿지 않으면 토큰이 맞는지 틀린지 알 수 없다.
401 을 주면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다. 503 과 `Retry-After`로 잠시 뒤 다시 부르게 한다.

**API 는 기본으로 닫혀 있다.** 문지기(`AuthGuard`)를 앱 전체에 걸고, 열어 둘 API 에만 `@Public()`을 붙인다.
API 마다 문지기를 붙이는 방식이면 붙이는 것을 빠뜨린 API 가 열린다. 인증 서버의 기본(`IsAuthenticated`)과 같은 생각이다.
게시판은 로그인 없이 읽는 API 가 많아서 `@Public()`이 자주 붙겠지만, 빠뜨렸을 때 닫히는 쪽이 안전하다. 테스트가 확인한다(`test/auth.e2e-spec.ts`의 "새로 만든 API").

**사용자는 인증 서버의 `public_id`로만 가리킨다.** 토큰의 `sub`다. 이 서버는 사용자의 이름이나 이메일을 모른다. UUID 의 모양이 아니면 거부한다.

**서버는 인증 서버 없이도 뜬다.** 공개키는 뜰 때가 아니라 첫 토큰이 올 때 가져온다. 끊긴 세션의 목록은 기다리지 않고 따로 받는다. `/health/ready`도 인증 서버를 보지 않는다.
인증 서버가 잠깐 죽었다고 게시판을 읽는 요청까지 막을 이유가 없다.

**마이그레이션 도구는 DB 에 관한 설정만 읽는다(`readDatabaseSettings`).** 마이그레이션을 돌리는 데 인증 서버의 주소까지 적게 하지 않는다. CI 의 마이그레이션 단계가 그대로 돈다.

**글 번호는 순번이다.** 1, 2, 3… 으로 매긴다(`bigint`, DB 가 매긴다). 게시판의 글은 어차피 공개 목록에 나오므로 번호를 숨길 까닭이 없고,
주소가 짧고(`/posts/1234`), 번호의 차례가 곧 쓴 차례라 목록을 번호로 줄 세운다. 게임 서버의 테이블은 UUID 다. 비공개 테이블의 주소를 추측당하면 안 되기 때문이다.
대신 글이 몇 개인지가 번호로 드러난다. 응답에서는 번호를 글자로 내보낸다(`"1234"`). JavaScript 의 숫자는 큰 정수를 정확히 담지 못한다.

**게시판은 테이블에 두고, 내용은 마이그레이션이 넣는다.** 코드에 고정하면 게시판을 더할 때 코드와 DB 제약을 함께 고친다. 운영자가 화면에서 만들게 하면 관리 API 와 권한까지 만들어야 한다.
그 사이를 골랐다. 게시판을 더하는 일은 행을 넣는 마이그레이션 하나다. "운영자만 쓴다" 같은 규칙도 코드가 아니라 게시판의 칸(`write_policy`)이다.

**운영자는 토큰이 알려 준다(#389).** 인증 서버가 access 토큰의 `roles` 에 `"operator"` 를 싣고, 이 서버는 토큰을 검증할 때 함께 읽는다(`auth/roles.ts`). 게임 서버와 같은 규칙이다.
예전에는 이 서버의 `operators` 테이블이 정했는데, 서비스마다 목록이 갈라지고(게시판에서는 운영자인데 게임에서는 아닌 사람) 권한을 볼 때마다 DB 에 물어야 해서 인증 서버 한 곳으로 옮겼다([운영자 권한](../docs/architecture/operators.md)).
대가는 권한을 뺏어도 이미 발급된 토큰이 만료될 때까지(15분) 통한다는 것이다. 급하면 인증 서버에서 세션을 끊는다(끊긴 세션은 30초쯤 안에 막힌다).
서비스는 사용자의 ID 하나 대신 요청한 사람(`Actor`: ID 와 운영자인지)을 받는다. 그래서 운영자인지 묻는 데 쿼리가 없다.

**권한의 규칙은 순수한 함수로 따로 둔다(`posts/posts.policy.ts`).** 쓰기는 게시판이 정한 대로, 고치기는 글쓴이만, 지우기는 글쓴이와 운영자다. 운영자만 쓰는 게시판(공지사항, 이벤트)의 글은 운영자만 지우고, 지금 운영자인 글쓴이만 고친다. 공지를 쓴 사람이 운영자에서 내려온 뒤에도 그 공지를 지우거나 고칠 수 있으면 안 된다. 다른 운영자도 남의 공지는 고치지 못한다. 글쓴이의 이름으로 다른 사람이 쓴 문장이 나가게 된다.
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

**검색어의 `%`, `_`, `\` 는 글자로 찾는다(`posts/search.ts`).** `LIKE` 는 `%`를 "아무 글자나", `_`를 "아무 한 글자"로 읽는다. 그대로 넘기면 `50%`를 찾는 사람이 `500`도 받는다.
앞에 역빗금을 붙여 뜻을 없애고 `ESCAPE` 로 그 역빗금을 알려 준다. 낱말은 SQL 에 이어 붙이지 않고 값으로 넘긴다.

**낱말은 2자 이상이다.** 한 글자로 찾으면 거의 모든 글이 걸린다. 색인 없이 훑는 검색에서 가장 비싼 요청이 가장 쓸모없는 결과를 낸다.

**검색의 주소는 게시판 아래에 두지 않았다(`GET /posts?q=`).** 모든 게시판에서 찾는 것이 기본이고 게시판 하나로 좁히는 것은 고르는 값(`board`)이다.
`/boards/{slug}/posts?q=` 로 두면 전체에서 찾는 주소가 하나 더 있어야 한다.

**쓰기 횟수는 따로 세어 두지 않고 DB 의 글과 댓글을 센다(`write-limits/`).** 횟수 제한은 보통 Redis 에 센다. 인증 서버도 그렇게 한다.
인증 서버가 세는 것은 실패한 로그인이다. DB 에 남는 행이 없어서 셀 곳이 따로 있어야 한다. 여기서 세는 것은 쓴 글이고, 그것은 `posts`에 이미 있다. 다른 곳에 한 번 더 세면 같은 숫자가 두 군데가 된다.
DB 의 행을 세면 서버를 다시 띄워도 여러 대로 늘려도 맞고, 새로 기댈 것(Redis, 그 설정, 죽었을 때의 처리)이 없다. 지운 것도 행이 남아서 "쓰고 지우고 또 쓰기"로 피하지 못한다.
값은 쓸 때마다 쿼리 하나다. 색인(`author_id, created_at`)만 읽고 끝난다. 운영자인지는 한도를 넘었을 때만 묻는다.
시각은 DB 의 것(`now()`)으로만 견준다. 쓴 시각을 DB 가 적으므로 서버의 시계와 견주면 둘의 차이만큼 어긋난다.

**한도는 대략 지킨다.** 세고 나서 쓰는 사이에 같은 사람의 다른 요청이 끼면 한두 개 넘을 수 있다. 정확히 막으려면 사용자마다 잠가야 한다. 도배를 막는 데에는 "대략 5개"로 충분하다.
숫자는 코드에 둔다(`write-limits.policy.ts`). 환경 변수로 빼지 않았다. 바꿀 일이 드물고, 잘못 넣으면 제한이 꺼지거나 아무도 쓰지 못한다.

**신고도 같은 방법으로 센다(1시간에 20건).** 신고는 행이 남으므로 글과 같은 함수로 센다. 세는 칸만 다르다(글쓴이 대신 신고한 사람).
한 사람이 신고로 운영자의 목록을 덮지 못하게 하는 것이 목적이다. 이미 신고한 것은 행을 만들지 않으므로 세기 전에 409 로 거절한다.

**검색은 횟수를 세지 않고 시간만 묶는다(3초).** 검색은 로그인 없이 부르고 남는 행도 없어서 위의 방법으로 셀 수 없다. 로그인 없는 요청을 IP 로 세는 것은 프록시의 일이다.
글 목록 같은 다른 읽기 주소도 똑같이 열려 있어서 앱에서 검색만 세는 것은 반쪽이다. 여기서는 검색 하나가 DB 를 오래 붙잡지 못하게만 한다.
제한은 트랜잭션 안에서 `SET LOCAL statement_timeout` 으로 건다. 그냥 `SET` 으로 걸면 연결에 남아서, 풀에 돌아간 그 연결을 받은 다른 요청에도 걸린다.

**글의 신고와 댓글의 신고는 한 테이블에 두고, 칸 둘(`post_id`, `comment_id`) 가운데 하나만 채운다.** 두 칸 모두 외래 키다. 없는 글이나 댓글을 가리키는 신고는 DB 가 받지 않는다.
"대상의 종류 + 번호" 한 칸으로 두는 방법도 흔하다. 대상이 늘어도 칸이 늘지 않는다. 대신 외래 키를 걸 수 없어서 정합성을 코드가 지켜야 한다.
테이블을 둘로 나누면 코드가 두 벌이 되고, 운영자의 목록을 UNION 으로 합쳐야 한다. 꼭 하나만 차는 것은 DB 의 CHECK 가 지킨다(`ck_reports_one_target`).
글과 댓글의 다른 점(어느 칸을 보는가)은 한 파일에 모았다(`reports/report-target.ts`). 서비스와 컨트롤러는 종류를 가리지 않고 그 값을 넘긴다.

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

**신고의 설명은 로그와 응답에 싣지 않는다.** 요청의 본문은 원래 로그에 남기지 않는다. 오류의 문장에도 받은 값을 넣지 않는다. 테스트가 접수, 다시 신고(409), 입력 오류(400)에서 확인한다.

**신고가 쌓여도 저절로 가리지 않는다.** 여럿이 짜고 멀쩡한 글을 가릴 수 있다. 사람이 본다. 사용자의 제재(쓰기 정지)와 신고한 사람에게 결과를 알리는 일도 하지 않았다. 계정은 인증 서버의 것이다.

**댓글과 답글은 한 테이블에 둔다.** 답글은 `parent_id`로 댓글을 가리킨다. 깊이는 두 단까지다. 답글에는 답글을 달 수 없다.
끝없이 깊어지게 두면 목록을 읽는 쿼리와 화면이 함께 복잡해진다. 답글에 답하고 싶으면 같은 댓글 아래에 답글을 하나 더 단다.
`parent_id`는 같은 글의 댓글이어야 한다. 이 글의 주소로 다른 글의 댓글 아래에 답글을 끼워 넣을 수 없다.

**댓글 목록은 "이것 다음 몇 개"로 이어 읽는다(`comments/slice.ts`).** 글 목록은 쪽 번호지만 댓글은 다르게 했다.
댓글은 몇 쪽으로 건너뛸 일이 없고 위에서부터 이어 읽는다. 읽는 사이에 새 댓글이 달려도 같은 댓글이 두 번 나오거나 빠지지 않는다. 뒤쪽을 읽어도 느려지지 않는다.
더 있는지는 하나를 더 읽어 보고 안다. 전체가 몇 개인지는 세지 않는다.

**댓글 목록은 쿼리 둘로 읽는다.** 글에 단 댓글을 한 토막 읽고, 그 댓글들의 답글을 한 번에 읽는다. 댓글마다 답글을 따로 읽으면 댓글 스무 개에 쿼리가 스물한 번 나간다.
두 쿼리와 "답글이 있는가"를 묻는 조건이 모두 색인 하나(`post_id`, `parent_id`, `id`)를 탄다.

**한 댓글의 답글에는 끝이 있다(100개).** 목록이 댓글마다 답글을 모두 실어 보내기 때문이다. 끝이 없으면 한 댓글에 답글을 쏟아부어 응답을 한없이 키울 수 있다.
수는 세어 보고 넣는다. 그사이에 다른 요청이 답글을 달면 한둘 넘을 수 있다. 응답의 크기를 막으려는 끝이라 그 정도는 넘어도 된다. 정확히 지키려면 댓글의 행을 잠그고 세야 한다.

**답글이 달린 댓글을 지우면 자리를 남긴다.** 답글은 그대로 두고, 그 댓글은 누가 무엇을 썼는지 비운 채 `deleted: true`로 내보낸다.
자리까지 없애면 답글들이 무엇에 답한 것인지 알 수 없게 된다. 답글이 없는 댓글과 지운 답글은 목록에서 그냥 빠진다.
지운 댓글에는 답글을 더 달 수 없다.

**댓글 수는 적어 두지 않고 물을 때마다 센다(`comment-counts/`).** 글에 숫자를 적어 두는 방법(`posts.comment_count`)도 있다. 큰 서비스가 흔히 그렇게 한다.
그러면 목록이 쿼리 하나로 끝나고 댓글 수로 줄을 세울 수 있다. 대신 댓글을 쓰고 지울 때마다 같은 트랜잭션에서 숫자를 고쳐야 하고, 동시에 달리는 댓글 때문에 글의 행을 잠가야 하고, 어긋났을 때 다시 세는 도구가 있어야 한다.
세는 쪽은 실제 행을 세므로 틀릴 수 없다. 값은 목록 한 쪽에 쿼리 하나다. 글마다 하나씩이 아니라 그 쪽의 글 번호를 모아 한 번에 센다(`GROUP BY post_id`). 댓글의 색인(`post_id, parent_id, id`)의 앞머리를 탄다.
"댓글 많은 순"이 필요해지면 적어 두는 쪽으로 옮긴다. 응답의 칸(`comment_count`)은 그대로라 화면은 모른다.

**댓글 수를 세는 것은 댓글 모듈이 아니라 따로 둔 모듈이다.** 댓글 모듈은 글이 있는지 확인하려고 글 모듈을 가져다 쓴다. 글 모듈이 댓글 수를 알려고 댓글 모듈을 가져다 쓰면 둘이 서로를 물고 돈다.
Nest 에는 그런 고리를 푸는 장치(`forwardRef`)가 있지만, 고리가 있다는 것은 경계가 틀렸다는 신호다. 세는 일은 `comments` 테이블만 읽으면 되므로 다른 모듈에 기대지 않는 작은 모듈로 뺐다.

**댓글은 로그인한 누구나 단다.** 운영자만 글을 쓰는 게시판(공지사항)의 글에도 그렇다. 글의 글쓴이라고 남의 댓글을 지울 수는 없다. 글쓴이 자신과 운영자만 지운다.

**글쓴이의 닉네임은 access 토큰에서 받아 이 서버의 표(`authors`)에 적어 둔다(`authors/`).** 닉네임은 인증 서버의 것이다. 길이 셋 있었다.
인증 서버에 "ID 들 → 닉네임"을 묻는 API 는 늘 최신이지만, 목록을 읽을 때마다 인증 서버를 부르고 인증 서버가 죽으면 이름이 빠진다.
인증 서버가 이름이 바뀔 때 알려 주는 길은 바로 반영되지만, 지금은 이름을 바꾸는 기능이 없어 알릴 일이 없다.
토큰에 실린 이름을 적어 두면 서버끼리 부르지 않는다. 인증 서버가 죽어도 이름이 나온다.

**이름은 사람마다 한 줄이고, 글과 댓글의 행에는 적지 않는다.** 글은 사람의 ID 만 가리킨다. 그래서 한 줄을 고치면 그 사람이 쓴 글 모두에 새 이름이 나온다.
글마다 쓸 때의 이름을 적으면 이름을 바꾼 뒤 같은 사람이 글마다 다른 이름으로 보인다.
응답에는 `author_id`를 그대로 두고 `author_nickname`을 더했다. 이미 쓰는 칸의 모양을 바꾸지 않는다.

**이름은 글을 쓸 때가 아니라 로그인한 요청마다 받는다(`authors/authors.interceptor.ts`).** 이름을 바꾸고 게시판에 들어오기만 해도 반영된다.
요청마다 DB 에 쓰지 않는다. 최근에 적은 이름을 서버의 메모리에 기억해 두고, 다를 때만 적는다. 기억에 없으면 한 번 적는데, DB 도 이름이 같으면 행을 고치지 않는다(`IS DISTINCT FROM`).
기억은 1만 명까지이고 넘으면 통째로 비운다. 서버를 다시 띄우거나 여러 대로 늘려도 틀리지 않는다. 한 번 더 적을 뿐이다.
문지기(`AuthGuard`)에 넣지 않았다. 문지기는 들여보낼지만 정한다.

**토큰의 이름은 한 번 더 본다(`authors/nickname.ts`).** 서명된 값이라 꾸며 낼 수는 없지만 화면에 그대로 나간다. 제어 문자, 보이지 않는 글자, 50자를 넘는 이름은 적지 않는다.
인증 서버의 규칙(한글·영문·숫자·밑줄, 20자)보다 넓게 받는다. 인증 서버가 규칙을 넓혔는데 여기만 그대로면 새 이름이 조용히 버려진다.
받아들일 수 없는 이름이어도 토큰은 받는다. 이름 때문에 로그인을 막지 않는다. 이름이 없는 토큰(이 클레임이 생기기 전에 발급한 것)도 같다. 적어 둔 이름을 지우지 않는다.

**이름을 바꾸는 기능이 생기면 인증 서버가 이 서버에 알리게 한다(#146).** 이름을 바꾸면 옛 이름이 풀린다. 다른 사람이 그 이름을 가져갔는데 바꾼 사람이 이 서버에 오지 않았다면 잠시 둘이 같은 이름으로 보인다.
탈퇴는 인증 서버가 알린다([탈퇴 받기](#탈퇴-받기), #603). 탈퇴한 사람의 글은 남기고, `author_id`와 `author_nickname`을 비운 채 "탈퇴한 사용자"로 보인다(`author_withdrawn`).
닉네임은 로그에 남기지 않는다. 사람은 ID 로만 적는다.

**제목과 본문은 받은 글자 그대로 저장한다.** HTML 로 해석하지도 태그를 지우지도 않는다. 화면이 글자로 그리면 된다.
서버가 태그를 지우면 코드를 설명하는 글이 망가지고, 지우는 규칙에 구멍이 하나만 있어도 뚫린다.

**오류 응답의 모양은 `{"detail": "문장"}`으로 통일한다(`errors/`).** 인증 서버, 게임 서버, 결제 서버와 같은 칸 이름이다. 화면이 오류를 읽는 코드를 서버마다 따로 짜지 않는다.
`detail`에는 이 서버가 적은 문장만 내보낸다. Nest 나 라이브러리가 만든 예외의 글은 상태 코드에 맞는 문장으로 바꾼다. 그 글에는 받은 주소나 파서의 오류 같은 내부 사정이 들어 있다.
뜻밖의 예외는 500 으로 답하고 예외의 글은 로그에만 남긴다. HTTP API 의 오류 표준(RFC 9457)은 쓰지 않았다. 네 서버 중 아무도 쓰지 않는다. `detail`은 그 표준의 칸 이름이기도 해서 나중에 옮기기는 쉽다.

**입력은 DTO 의 규칙대로 검사한다(`class-validator`).** Nest 의 표준 방식이다. 모르는 칸이 오면 조용히 버리지 않고 거부한다. 칸 이름을 잘못 적은 클라이언트가 왜 반영이 안 되는지 알 수 있다.
글쓴이를 본문으로 보내도(`author_id`) 거부된다. 글쓴이는 토큰에서만 안다.

**주소의 글 번호와 게시판 이름은 모양을 먼저 본다.** 모양이 아니면 DB 에 묻지 않고 404 다. 숫자가 아닌 값을 번호 칸에 묻거나 주소로 들어온 NUL 글자를 그대로 물으면 DB 가 오류를 내고, 그것은 500 이 된다.

**준비됐는지 묻는 API 는 예외를 던지지 않는다.** 준비되지 않았다는 것은 오류가 아니라 그 API 의 답이다. 상태 코드만 503 으로 바꾸고 `{"status": "unavailable"}`을 돌려준다.
예외로 던지면 오류 응답의 모양으로 바뀐다. 관리 도구가 읽는 주소라 답의 모양을 지킨다.

**제약과 색인의 이름을 직접 적는다(`pk_posts`, `fk_posts_board`).** TypeORM 이 지어 주는 이름(`PK_8c82d7f5...`)은 DB 의 오류 글에서 읽을 수 없다.

**DB 계정과 스키마는 이 서버의 것만 쓴다.** `board` 계정으로 `board` 스키마만 쓴다. 다른 서버(`auth`, `game`, `billing`)의 스키마에는 들어갈 수 없다.
약속이 아니라 DB 권한으로 지키고, 테스트가 확인한다(`test/database.e2e-spec.ts`): 읽을 권한이 없고, 테이블을 만들 권한이 없고, 스키마 이름을 직접 붙여 불러도 권한 없음이 난다.
권한을 잘못 넓히면(`GRANT USAGE ON SCHEMA game TO board`) 이 테스트가 실패한다.

**ORM 은 TypeORM 이다.** Nest 의 공식 문서가 기본으로 다루고, 엔티티와 리포지토리의 구조가 게임 서버의 SQLAlchemy 와 닮았다.
Prisma 를 먼저 골랐다가 바꿨다. Prisma 의 명령(클라이언트 만들기, 스키마 검사, 마이그레이션)은 실행할 때 Prisma 의 서버에서 실행 파일을 내려받는다.
패키지 저장소만 열린 환경(코드를 미리 돌려 보는 샌드박스)에서는 그 명령이 하나도 돌지 않았다. TypeORM 은 npm 패키지만으로 돈다.
대신 Prisma 만큼 타입을 촘촘히 잡아 주지 않고, 자동으로 만든 마이그레이션을 읽어 봐야 한다(위의 "DB와 마이그레이션").

**테이블은 마이그레이션으로만 바꾼다.** TypeORM 의 `synchronize`는 늘 끈다. 켜면 서버가 뜰 때 엔티티에 맞춰 테이블을 고친다. 칸을 지우면 데이터도 지워진다.
서버가 뜨면서 마이그레이션을 돌리지도 않는다(`migrationsRun`). 서버가 여러 대면 동시에 돌린다.

**스키마는 연결의 `search_path`로 정한다.** 코드와 마이그레이션에 스키마 이름을 적지 않는다. 연결할 때마다 설정의 스키마로 맞춘다.
그래서 같은 마이그레이션이 `board`에도 `board_test`에도 적용되고, 테스트는 설정만 바꿔 테스트용 스키마를 쓴다.
TypeORM 의 `schema` 옵션은 쓰지 않는다. 쓰면 만드는 SQL 에 스키마 이름이 박힌다.
스키마 이름은 연결의 설정 글자에 그대로 들어가므로 모양을 검사한다(영문 소문자, 숫자, 밑줄).

**서버와 마이그레이션 도구가 같은 함수로 연결 옵션을 만든다(`databaseOptions`).** 따로 적으면 서버는 한 스키마를 보는데 마이그레이션은 다른 스키마에 테이블을 만드는 일이 생긴다.

**마이그레이션 도구는 빌드된 파일로 돈다.** TypeScript 파일을 바로 읽게 하려면 도구가 하나 더 필요하고, 데코레이터와 ESM 을 함께 다루는 설정이 까다롭다.
명령마다 빌드가 먼저 돈다(`npm run build && ...`).

**테스트는 같은 DB의 다른 스키마(`board_test`)에서 돈다.** 게임 서버와 같은 방식이다. 테스트용 DB를 새로 만들려면 계정에 DB를 만드는 권한을 줘야 한다.
테스트용 스키마가 아니면 테스트용 앱이 만들어지지 않는다(`test/app.ts`). 설정을 잘못 건드려 개발용 데이터에서 테스트가 도는 일을 막는다.
테스트는 `.env`를 통째로 읽지 않고 DB 주소만 골라 읽는다. 개발자의 `.env`에 무엇이 적혀 있든 결과가 같아야 한다.

**서버는 뜰 때 DB 에 연결해 보고, 닿지 않으면 뜨지 않는다.** 게임 서버와 다른 점이다. 게임 서버는 처음 쓸 때 연결하므로 DB 없이도 뜬다.
Nest 의 TypeORM 연결이 그렇게 동작하고, 그대로 뒀다. DB 를 안 켰다는 것을 3초 안에 알 수 있다(기본은 30초를 기다린다).
떠 있는 동안 DB 가 끊기면 죽지 않는다. `/health/ready`가 503 을 돌려주고, DB 가 돌아오면 다시 200 이다.
DB 가 3초 안에 답하지 않아도 503 이다(`database.health.ts` 의 `PING_TIMEOUT_MS`, 결제 서버와 같다). 연결된 채 멈춘 DB 앞에서도 확인이 매달리지 않는다.

**`/health`는 프로세스가 살아 있는지만, `/health/ready`는 DB 에 닿는지를 본다.** 살아 있는지에 DB 까지 넣으면, DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
준비됐는지가 실패하면 관리 도구는 재시작하지 않고 요청만 잠시 보내지 않는다.
왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다. 로그에도 오류의 종류만 남긴다.
둘 다 HEAD 도 받는다(본문 없이 같은 상태 코드). 확인 요청이 끝난 줄은 성공이면 `debug`, 503 이면 `warning` 이라 운영의 로그를 메우지 않는다(`docs/observability.md` 의 "요청이 끝난 줄").

**기본으로 듣는 주소는 `127.0.0.1`이다.** Nest 는 주소를 주지 않으면 모든 주소에서 듣는다. 개발하는 컴퓨터에서 띄운 서버가 같은 공유기의 다른 기기에 열린다. 컨테이너에서는 `HOST=0.0.0.0`으로 바꾼다.

**앱에 거는 규칙을 한 함수에 둔다(`setupApp`).** 주소의 앞부분과 머리말의 규칙이다. 서버를 띄울 때와 테스트가 같은 함수를 부른다.
`main.ts`에만 적으면 테스트가 만든 앱에는 걸리지 않아서, 테스트는 통과하는데 실제 서버의 주소는 다른 일이 생긴다.

**응답에서 `X-Powered-By`를 뺀다.** 어떤 프레임워크로 만들었는지 알려 줄 이유가 없다.

**모듈 방식은 ESM 이다.** `import`와 `export`를 쓰는 지금의 표준이다. 같은 프로젝트의 파일을 가져올 때 `./app.module.js`처럼 끝에 `.js`를 붙인다. 파일은 `.ts`지만, 실행되는 것은 빌드된 `.js`이기 때문이다.

**패키지 관리자는 npm 이다.** Node.js 에 딸려 온다. 설치가 느려지면 pnpm 으로 옮길 수 있다(`pnpm import`가 잠금 파일을 바꿔 준다).

**외부 모니터링 서비스(`@nestjs/observe`)와 배포 도구(`@nestjs/mau`)는 넣지 않았다.** 프로젝트를 만드는 도구가 권하지만, 로그와 지표를 무엇으로 모을지는 아직 정하지 않았다.

**린트와 모양 검사를 처음부터 CI에 넣는다.** 코드가 쌓인 뒤에 넣으면 지적이 한꺼번에 나와 고치는 일이 따로 생긴다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다(supertest).** 네트워크의 포트를 열지 않아 빠르고, 포트가 겹칠 일이 없다.
