# 게시판 서버

[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)

[ai-trpg](../README.md)의 게시판 서버. 사이트가 운영하는 커뮤니티를 맡는다. 공지, 이벤트, 잡담, 시나리오 이야기 같은 글과 댓글이다. NestJS(TypeScript)로 만든다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.
시나리오의 소개 페이지에 붙는 댓글(플레이한 사람들의 평)은 여기가 아니라 시나리오 쪽의 일이다.

지금은 뼈대와 토큰 검증까지 있다. 서버가 뜨고, DB 에 붙고, 인증 서버의 토큰으로 누가 보낸 요청인지 안다. 글과 댓글의 테이블은 아직 없다.

## 목차

- [실행](#실행)
- [DB와 마이그레이션](#db와-마이그레이션)
- [API](#api)
- [구조](#구조)
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
| `JWT_ISSUER` | `ai-trpg-auth` | 믿는 토큰의 발급자(`iss`). 인증 서버의 `JWT_ISSUER`와 같아야 한다 |
| `JWT_AUDIENCE` | `ai-trpg-board` | 이 서버의 이름. 토큰의 대상(`aud`)에 이 이름이 있어야 받는다. 하나만 적는다 |
| `HOST` | `127.0.0.1` | 서버가 듣는 주소. 컨테이너에서는 `0.0.0.0` |
| `PORT` | `8002` | 서버가 듣는 포트 |

### 로그인한 사용자로 불러 보기

인증 서버를 띄우고 로그인해서 받은 access 토큰을 붙여 부른다.

```
curl http://127.0.0.1:8002/api/v1/board/me -H "Authorization: Bearer <access 토큰>"
```

`{"user_id":"..."}`가 오면 인증 서버가 발급한 토큰을 이 서버가 검증한 것이다. 401 이 오면 둘을 본다.

- **인증 서버의 `JWT_AUDIENCE`에 `ai-trpg-board`가 있는가.** 인증 서버는 토큰에 대상의 목록을 싣고, 이 서버는 그 목록에 자기 이름이 있는지 본다.
  인증 서버의 기본값에는 들어 있다. `auth-server/.env`에 `JWT_AUDIENCE`를 직접 적어 둔 PC 라면 그 줄에 `ai-trpg-board`를 더하고 인증 서버를 다시 띄운다.
- **토큰이 그 뒤에 발급된 것인가.** 대상은 발급할 때 정해진다. 고치기 전에 받은 토큰에는 새 이름이 없다. access 토큰의 수명은 15분이다.

503 이 오면 이 서버가 인증 서버의 공개키를 한 번도 받지 못한 것이다. 인증 서버가 떠 있는지와 `AUTH_JWKS_URL`을 본다.

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

커밋하기 전에 다섯을 모두 돌린다.

앱 테스트는 개발용과 같은 DB의 `board_test` 스키마를 쓰므로 개발용 데이터(`board` 스키마)를 건드리지 않는다.
DB 주소는 환경 변수나 `.env`의 것을 그대로 읽고, 스키마는 테스트가 고정한다(`test/setup.ts`).
테스트용 스키마에도 테이블이 있어야 한다. 마이그레이션을 새로 만들거나 받으면 한 번 적용한다.

```
# PowerShell
$env:DB_SCHEMA='board_test'; npm run migration:run; Remove-Item Env:DB_SCHEMA

# bash
DB_SCHEMA=board_test npm run migration:run
```

DB가 꺼져 있으면 앱 테스트가 실패한다. 인증 서버는 띄우지 않아도 된다. 토큰은 테스트가 직접 만든 키로 서명하고,
그 공개키를 인증 서버가 내준 것처럼 앱에 꽂는다(`test/tokens.ts`, `test/app.ts`).
다른 서버들의 계정과 스키마(`auth`, `game`, `billing`)도 DB 에 만들어져 있어야 한다. 게시판 계정이 거기에 들어가지 못하는지 테스트가 확인한다.

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
npm run migration:generate -- src/migrations/CreatePosts     # 엔티티와 DB를 비교해 새 마이그레이션 만들기
npm run migration:check                                      # 엔티티를 바꾸고 마이그레이션을 안 만들었는지 검사
npm run migration:show                                       # 적용된 것과 안 된 것 보기
npm run migration:revert                                     # 마지막 하나 되돌리기
```

파이썬 쪽의 Alembic 과 짝을 지으면 `upgrade head`가 `migration:run`, `revision --autogenerate`가 `migration:generate`, `check`가 `migration:check`다.

**자동으로 만든 마이그레이션은 읽어 보고 커밋한다.** TypeORM 은 색인을 지우는 줄에 만들 때의 스키마 이름을 붙인다(`DROP INDEX "board"."IDX_..."`).
같은 파일을 `board`와 `board_test`에 함께 쓰므로 그 이름을 지운다. 지우지 않으면 `npm test`가 실패한다(`src/migrations/migrations.spec.ts`).
만든 뒤에는 `npm run format`으로 모양을 맞춘다.

적용한 기록은 스키마마다 `migrations` 테이블에 남는다.

## API

게시판 서버의 API는 `/api/v1/board/` 아래에 놓는다. 글과 댓글의 API 는 아직 없다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버가 살아 있는지 확인 | 불필요 |
| GET | `/health/ready` | 요청을 처리할 준비가 됐는지 확인(DB 에 닿는가). 닿지 않으면 503 | 불필요 |
| GET | `/api/v1/board/me` | 토큰의 주인이 누구인지 확인. `{"user_id": "..."}` | 필요 |

앞의 두 주소는 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다.

**API 는 기본으로 로그인이 필요하다.** 로그인 없이 열어 둘 API 에만 `@Public()`을 붙인다. 토큰은 `Authorization: Bearer <access 토큰>` 머리말로 보낸다.

| 상태 | 언제 | 응답 |
| --- | --- | --- |
| 401 | 토큰이 없거나 받아들일 수 없다 | `{"detail": "인증이 필요합니다."}`, `WWW-Authenticate: Bearer` |
| 503 | 인증 서버의 공개키를 구하지 못해 확인할 수 없다 | `{"detail": "지금은 인증을 확인할 수 없습니다. ..."}`, `Retry-After: 60` |

401 은 왜 틀렸는지 알리지 않는다. 만료든 서명이 틀렸든 응답이 같다. 클라이언트는 401 이면 토큰을 갱신하고, 503 이면 로그아웃시키지 않고 잠시 뒤 다시 부른다.
게임 서버와 같은 응답이다.

## 구조

```
src/
  main.ts                        서버를 띄우는 시작점
  app.module.ts                  이 서버를 이루는 모듈들을 모은다
  app.setup.ts                   주소의 앞부분 같은, 앱에 거는 규칙
  config/environment.ts          환경 변수를 검사해 설정으로 바꾼다
  auth/
    jwks.ts                      인증 서버의 공개키를 가져오고 기억한다
    tokens.ts                    토큰을 검증하는 규칙
    bearer.ts                    Authorization 머리말에서 토큰을 꺼낸다
    token-verifier.ts            검증의 규칙에 이 앱의 설정과 키 저장소를 물린 서비스
    auth.guard.ts                문지기. 요청마다 토큰을 검증하고 결과를 응답으로 바꾼다
    public.decorator.ts          @Public(). 로그인 없이 부를 수 있다는 표시
    current-user.decorator.ts    @CurrentUser(). 토큰의 주인을 컨트롤러의 인자로 받는다
    auth.module.ts               위의 것들을 묶고 문지기를 앱 전체에 건다
  me/                            토큰의 주인을 돌려주는 API
  database/
    database.options.ts          설정을 연결 옵션으로 바꾼다. 서버와 마이그레이션 도구가 함께 쓴다
    database.module.ts           서버의 DB 연결
    database.health.ts           DB 에 닿는지 확인한다
    data-source.ts               마이그레이션 도구가 읽는 연결
  health/                        살아 있는지, 준비됐는지 확인하는 API
  migrations/                    마이그레이션 파일
test/
  setup.ts                       테스트의 환경 변수를 맞춘다(DB 주소, 테스트용 스키마, 닿지 않는 공개키 주소)
  app.ts                         테스트용 앱을 만든다
  tokens.ts                      테스트가 직접 만든 키로 토큰을 서명한다
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
| 가드(`*.guard.ts`) | 요청이 컨트롤러에 닿기 전에 들여보낼지 정한다 | `Depends(get_current_user)` |
| 데코레이터(`@Public()`, `@CurrentUser()`) | 컨트롤러와 인자에 붙이는 표시 | `CurrentUser` 타입 |

## CI

PR과 `main` 푸시마다 GitHub Actions가 게시판 서버를 검사한다. `board-server/`, DB 초기화 스크립트, 워크플로 파일이 바뀐 경우에만 돈다.
실제 PostgreSQL을 띄우고, 로컬과 같은 초기화 스크립트로 계정과 스키마를 만든다.

1. 의존성 설치 (`npm ci`): `package-lock.json`과 `package.json`이 어긋나면 실패한다
2. 린트 (`npm run lint`)
3. 모양 검사 (`npm run format:check`): 고치지 않고 검사만 한다
4. 빌드 (`npm run build`): 타입 검사를 겸한다
5. 마이그레이션 적용 (`npm run migration:run`): 빈 DB 에 처음부터 끝까지 적용되는지 본다
6. 마이그레이션 누락 검사 (`npm run migration:check`): 엔티티를 바꾸고 마이그레이션을 만들지 않았으면 실패한다
7. 테스트용 스키마에 마이그레이션 적용
8. 테스트 (`npm test`, `npm run test:e2e`)

## 설계 메모

**설정은 `@nestjs/config`로 읽고, 뜰 때 검사한다.** `.env`와 환경 변수를 읽어 검사 함수(`config/environment.ts`)에 넘긴다.
값이 틀리면 앱을 만드는 데서 예외가 나고 프로세스가 끝난다. 틀린 설정으로 떠서 요청을 받다가 실패하지 않는다.
검사 함수는 Nest 를 모르는 순수한 함수라 따로 테스트한다. 꺼내 쓰는 쪽은 `ConfigService<Environment, true>`로 받아서, 없는 이름을 꺼내면 컴파일러가 잡는다.
`.env`는 다른 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
예외의 글에 받은 값을 싣지 않는다. DB 주소에는 비밀번호가 들어 있다.

**토큰은 인증 서버의 공개키로 검증만 한다.** 회원가입과 로그인은 인증 서버의 일이다. 이 서버는 인증 서버의 DB 를 보지 않고, 요청마다 인증 서버에 묻지도 않는다.
서명 방식(RS256), 서명, 만료(`exp`), 발급자(`iss`), 대상(`aud`), 토큰의 종류(`token_type`이 `access`)를 본다. 게임 서버와 같은 규칙이다(`game-server/app/auth/`).
그래서 인증 서버에서 로그아웃하거나 계정이 정지돼도 이미 발급된 access 토큰은 만료될 때까지(15분) 통한다.
서명 방식은 코드에 하나만 적는다. 토큰의 머리말에 적힌 방식을 믿으면 서명이 없는 토큰(`none`)이나 공개키를 비밀키처럼 써서 만든 토큰(`HS256`)이 통과한다.

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

**서버는 인증 서버 없이도 뜬다.** 공개키는 뜰 때가 아니라 첫 토큰이 올 때 가져온다. `/health/ready`도 인증 서버를 보지 않는다.
인증 서버가 잠깐 죽었다고 게시판을 읽는 요청까지 막을 이유가 없다.

**마이그레이션 도구는 DB 에 관한 설정만 읽는다(`readDatabaseSettings`).** 마이그레이션을 돌리는 데 인증 서버의 주소까지 적게 하지 않는다. CI 의 마이그레이션 단계가 그대로 돈다.

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

**`/health`는 프로세스가 살아 있는지만, `/health/ready`는 DB 에 닿는지를 본다.** 살아 있는지에 DB 까지 넣으면, DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
준비됐는지가 실패하면 관리 도구는 재시작하지 않고 요청만 잠시 보내지 않는다.
왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다. 로그에도 오류의 종류만 남긴다.

**기본으로 듣는 주소는 `127.0.0.1`이다.** Nest 는 주소를 주지 않으면 모든 주소에서 듣는다. 개발하는 컴퓨터에서 띄운 서버가 같은 공유기의 다른 기기에 열린다. 컨테이너에서는 `HOST=0.0.0.0`으로 바꾼다.

**앱에 거는 규칙을 한 함수에 둔다(`setupApp`).** 주소의 앞부분과 머리말의 규칙이다. 서버를 띄울 때와 테스트가 같은 함수를 부른다.
`main.ts`에만 적으면 테스트가 만든 앱에는 걸리지 않아서, 테스트는 통과하는데 실제 서버의 주소는 다른 일이 생긴다.

**응답에서 `X-Powered-By`를 뺀다.** 어떤 프레임워크로 만들었는지 알려 줄 이유가 없다.

**모듈 방식은 ESM 이다.** `import`와 `export`를 쓰는 지금의 표준이다. 같은 프로젝트의 파일을 가져올 때 `./app.module.js`처럼 끝에 `.js`를 붙인다. 파일은 `.ts`지만, 실행되는 것은 빌드된 `.js`이기 때문이다.

**패키지 관리자는 npm 이다.** Node.js 에 딸려 온다. 설치가 느려지면 pnpm 으로 옮길 수 있다(`pnpm import`가 잠금 파일을 바꿔 준다).

**외부 모니터링 서비스(`@nestjs/observe`)와 배포 도구(`@nestjs/mau`)는 넣지 않았다.** 프로젝트를 만드는 도구가 권하지만, 로그와 지표를 무엇으로 모을지는 아직 정하지 않았다.

**린트와 모양 검사를 처음부터 CI에 넣는다.** 코드가 쌓인 뒤에 넣으면 지적이 한꺼번에 나와 고치는 일이 따로 생긴다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다(supertest).** 네트워크의 포트를 열지 않아 빠르고, 포트가 겹칠 일이 없다.
