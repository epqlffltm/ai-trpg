# ai-trpg

[![auth-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml)

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | `auth-server/` | 회원가입, 로그인, 토큰 갱신, 로그아웃, JWKS까지 완료. 이메일 인증은 부품만 완료 |
| 게임 서버 (FastAPI) | `game-server/` | 예정 |
| 프론트엔드 | `web/` | 예정 |

## 요구 사항

- Docker
- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## 실행

### 1. 인프라 환경 변수

`.env.example`을 복사해 `.env`를 만들고 `POSTGRES_PASSWORD`와
`AUTH_DB_PASSWORD`를 채운다. 이 파일은 커밋하지 않는다.

```
cp .env.example .env
```

### 2. 인프라

```
docker compose up -d
docker compose ps
```

`db`와 `redis`가 모두 `healthy`이면 정상이다.

첫 기동 때 `docker/postgres/init/`의 스크립트가 서버별 DB 계정과 스키마를 만든다.
이 스크립트는 데이터 볼륨이 비어 있을 때만 실행된다.

### 3. 인증 서버

```
cd auth-server
cp .env.example .env
uv sync
```

`auth-server/.env`에 `SECRET_KEY`를 채우고, `DATABASE_URL`의 비밀번호를
루트 `.env`의 `AUTH_DB_PASSWORD`와 같은 값으로 맞춘다.

JWT 서명용 개인키를 만든다. `keys/jwt-private.pem`에 저장되고 커밋되지 않는다.

```
uv run python scripts/generate_jwt_key.py
```

```
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

`http://127.0.0.1:8000/admin/` 에서 관리자 화면에 로그인한다.

### 4. 테스트

실제 PostgreSQL에서 돈다. 인프라가 떠 있어야 한다.

```
cd auth-server
uv run python manage.py test
```

## API

인증 서버의 API는 `/api/v1/auth/` 아래에 있다. 요청과 응답은 JSON이다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/signup` | 회원가입 | 불필요 |
| POST | `/api/v1/auth/login` | 로그인. access 토큰과 refresh 쿠키 발급 | 불필요 |
| POST | `/api/v1/auth/refresh` | refresh 쿠키로 새 access 토큰 발급 | refresh 쿠키 |
| POST | `/api/v1/auth/logout` | 이 기기의 refresh 토큰 폐기 | refresh 쿠키 |
| POST | `/api/v1/auth/logout-all` | 모든 기기의 세션 종료 | 필요 |
| GET | `/api/v1/auth/jwks` | 토큰 검증용 공개키 목록 | 불필요 |
| GET | `/api/v1/auth/me` | 내 계정 정보 | 필요 |

인증이 필요한 API에는 `Authorization: Bearer <access_token>` 헤더를 붙인다.

회원가입 요청 본문은 `username`, `email`, `nickname`, `password`다.
성공하면 `201`과 함께 `public_id`, `username`, `nickname`을 돌려준다.

로그인 요청 본문은 `username`, `password`다. 성공하면 `access_token`, `token_type`,
`expires_in`을 돌려준다. 아이디가 없든 비밀번호가 틀리든 같은 `401` 응답을 준다.

### 토큰 두 종류

| | access 토큰 | refresh 토큰 |
| --- | --- | --- |
| 수명 | 15분 | 14일 (쓸 때마다 새것으로 교체) |
| 전달 | 응답 본문 | httpOnly 쿠키 (`Path=/api/v1/auth`, `SameSite=Strict`) |
| 쓰는 곳 | 인증 서버와 다른 서버의 API | 인증 서버의 `/refresh`, `/logout` |
| 프론트의 보관 | 메모리 | 브라우저가 보관. 스크립트는 읽을 수 없음 |

access 토큰이 만료되면 프론트는 `/refresh`를 호출해 새 access 토큰을 받는다.
`/refresh`가 `401`이면 다시 로그인해야 한다.

프론트는 `/refresh`를 한 번에 하나만 호출해야 한다. 같은 refresh 토큰으로 두 요청이
동시에 가면 하나만 성공하고, 나머지는 폐기된 토큰의 재사용으로 처리되어 모든 세션이 끊긴다.

### 다른 서버에서 토큰을 검증하는 방법

1. 토큰 머리말의 `kid`를 읽는다
2. `/api/v1/auth/jwks`에서 `kid`가 같은 공개키를 고른다. 키 목록은 캐시해 둔다
3. 그 키로 서명을 검증한다. 알고리즘은 `RS256`만 허용한다
4. `iss`가 `ai-trpg-auth`인지, `aud`에 자기 서버 이름이 있는지, `exp`가 지나지 않았는지 확인한다

토큰의 `sub`는 회원의 `public_id`다.

## CI

PR과 `main` 푸시마다 GitHub Actions가 인증 서버를 검사한다. `auth-server/`,
`docker/postgres/init/`, 워크플로 파일 중 하나가 바뀐 경우에만 돈다.

1. 의존성 설치 (`uv sync --locked`): `uv.lock`과 `pyproject.toml`이 어긋나면 실패한다
2. 설정 검사 (`manage.py check`). 그 전에 이 실행에서만 쓰고 버릴 JWT 키를 만든다
3. 마이그레이션 누락 검사 (`makemigrations --check --dry-run`): 모델을 바꾸고
   마이그레이션을 만들지 않았으면 실패한다
4. 테스트 (`manage.py test`)

CI도 로컬과 같은 초기화 스크립트로 `auth` 계정을 만들어 그 계정으로 테스트한다.
슈퍼유저로 테스트하면 권한 때문에 실패할 코드가 CI를 통과하기 때문이다.

## 설계 메모

**설정 파일을 서버마다 따로 둔다.** 루트 `.env`는 인프라용이고, 서버의 비밀값은
각 서버 폴더의 `.env`에 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.

**아이디와 이메일을 분리한다.** 로그인은 아이디로 하고, 이메일은 인증 코드를 받는 용도로만 쓴다.
아이디는 영문 소문자, 숫자, 밑줄만 허용해 이메일 주소를 아이디로 쓸 수 없게 한다.
이메일 중복은 대소문자를 무시하는 DB 제약으로 막는다.

**토큰은 RS256으로 서명하고 공개키를 JWKS로 내보낸다.** 개인키는 인증 서버만 갖는다.
다른 서버는 공개키로 검증만 하므로 토큰을 만들 수 없다. 대칭키(HS256)를 서버끼리 공유하면
검증만 해야 할 서버도 토큰을 위조할 수 있다.

**키 ID(`kid`)는 공개키의 해시로 정한다.** 이름을 사람이 붙이지 않으므로, 키를 바꾸면 ID도
자동으로 바뀐다. JWKS가 목록인 것은 키를 교체하는 동안 옛 키와 새 키를 함께 내보내기 위해서다.

**access 토큰은 15분만 유효하다.** 다른 서버는 인증 서버에 묻지 않고 서명과 만료만 확인한다.
탈취된 토큰을 중간에 취소할 방법이 없으므로 수명을 짧게 잡는다.

**refresh 토큰은 httpOnly 쿠키에 담는다.** 14일짜리라 탈취 피해가 크다. 스크립트가 읽을 수 없는
곳에 두면 XSS로는 훔칠 수 없다. 쿠키 경로를 인증 API로 제한해 다른 요청에는 실리지 않고,
`SameSite=Strict`로 다른 사이트에서 시작된 요청에도 실리지 않는다. access 토큰은 다른 서버에도
보내야 해서 쿠키에 담지 않는다.

**refresh 토큰은 쓸 때마다 교체하고, 폐기된 토큰이 다시 쓰이면 모든 세션을 끊는다.**
폐기된 토큰이 다시 들어왔다는 것은 정상 사용자와 공격자 중 한쪽이 옛 토큰을 쓴 것이다.
누가 진짜인지 가릴 수 없으므로 양쪽 다 끊고 다시 로그인하게 한다.
같은 토큰으로 동시에 들어온 요청은 행 잠금으로 하나만 통과시킨다.

**세션을 한 번에 끊는 장치는 세션 버전(`token_version`)이다.** 토큰에 버전을 넣어 발급하고,
회원의 버전을 올리면 그 전의 토큰이 전부 무효가 된다. 토큰을 하나씩 찾아 폐기할 필요가 없다.
다른 서버는 버전을 확인할 수 없어 옛 access 토큰이 최대 15분 통한다.

**폐기 기록은 PostgreSQL에 둔다(simplejwt의 블랙리스트 테이블).** 폐기 여부는 갱신과 로그아웃
때만 확인하므로 조회가 드물다. Redis 캐시를 덧붙이면 두 저장소가 어긋나는 순간 폐기된 토큰이
통과할 수 있어 쓰지 않는다. 발급한 토큰의 원문은 저장하지 않고 토큰 ID만 남긴다.

**토큰의 서명과 검증, 폐기 기록 테이블은 simplejwt에 맡긴다.** 그 위에 세 가지를 직접 얹었다.
머리말의 `kid`(simplejwt는 넣지 않는다), 로그인 뷰, refresh 회전이다. simplejwt의 내장 갱신에는
폐기된 토큰이 다시 쓰였을 때 모든 세션을 끊는 동작이 없다. 발급은 함수 하나(`issue_token_pair`)로
감싸, 로그인 흐름이 바뀌어도 그대로 쓴다.

**이메일 인증 코드는 Redis가 아니라 PostgreSQL에 둔다.** 로그인마다 인증 코드가 필요한데,
로그인은 이미 PostgreSQL 없이는 동작하지 않는다. 코드를 Redis에 두면 로그인이 의존하는 것이
하나 더 늘어 Redis 장애가 곧 로그인 장애가 된다. 양도 로그인 한 번에 코드 하나라 Redis의 속도가
필요하지 않다. 회원과 용도마다 행을 하나만 두고 덮어써서 테이블이 불어나지 않는다.
Redis는 없어도 서비스가 도는 보조 장치(시도 횟수 제한)에만 쓸 예정이다.

**인증 코드는 원문이 아니라 비밀키를 섞은 해시로 저장한다.** 6자리는 100만 가지뿐이라 그냥
해시하면 전부 대입해 바로 풀린다. 회원과 용도도 함께 섞어 다른 행의 해시를 옮겨 쓸 수 없게 한다.

**코드 검증은 다른 트랜잭션 안에서 실행할 수 없게 막는다.** 틀린 횟수는 반드시 저장되어야 한다.
바깥 트랜잭션이 있으면 검증 실패 예외가 그 트랜잭션까지 되돌려 횟수가 사라지고, 횟수 제한 없이
코드를 추측할 수 있게 된다. 검증 블록을 `durable`로 선언해 중첩 자체를 오류로 만든다.

**검증, 생성, HTTP 처리를 나눈다.** Serializer는 입력 검증만, service는 계정 생성만,
뷰는 요청과 응답 변환만 한다. DRF 관례는 Serializer의 `create()`에 생성 로직을 두는 것인데,
그러면 검증과 상태 변경이 한 클래스에 섞인다.

**중복은 두 번 막는다.** Serializer의 사전 조회는 어느 값이 겹쳤는지 알려 주는 용도다.
동시에 들어온 요청은 사전 조회를 둘 다 통과할 수 있으므로, 최종 방어는 DB의 유니크 제약이고
그때는 `409`로 응답한다.

**API의 기본 권한은 "인증된 사용자만"이다.** 공개 API는 뷰에서 직접 열어야 한다.
권한 설정을 빠뜨린 뷰가 열려 있는 것보다 닫혀 있는 쪽이 안전하다.

**외부에는 정수 PK 대신 UUID(`public_id`)를 내보낸다.** 정수 PK는 가입자 수와
가입 순서를 추측하게 해 준다. 정수 PK는 내부 조인용으로 남긴다.

**DB 인스턴스는 하나, 계정과 스키마는 서버마다 따로 쓴다.** 인증 서버는 `auth` 계정으로
`auth` 스키마만 쓴다. 다른 서버의 테이블을 직접 읽는 코드는 DB 권한에서 거부된다.
서버 간 데이터 교환은 API로만 한다.

## 운영 메모

**만료된 토큰 기록 정리.** 발급 기록과 폐기 기록은 토큰이 만료된 뒤에도 테이블에 남는다.
배포 환경에서는 아래 명령을 하루에 한 번 실행한다.

```
uv run python manage.py flushexpiredtokens
```

## 자주 겪는 문제

**`docker compose ps`에서 db의 포트 칸이 비어 있다**

Windows에서 Hyper-V가 해당 포트를 예약한 경우다. 예약 구간을 확인하고
`.env`의 `POSTGRES_PORT`를 구간 밖의 값으로 바꾼다. `auth-server/.env`의
`DATABASE_URL` 포트도 함께 맞춘다.

```
netsh interface ipv4 show excludedportrange protocol=tcp
```

**`password authentication failed for user "auth"`**

`auth` 계정이 없거나 비밀번호가 다르다. 초기화 스크립트는 볼륨이 비어 있을 때만
실행되므로, 스크립트를 추가하기 전에 만든 볼륨에는 계정이 없다.
데이터를 지워도 되는 상태라면 볼륨을 지우고 다시 띄운다.

```
docker compose down -v
docker compose up -d
```

**로컬에서 로그인은 되는데 `/refresh`가 항상 `401`이다**

`auth-server/.env`에 `REFRESH_COOKIE_SECURE=false`가 없는 경우다. 기본값은 HTTPS에서만
쿠키를 보내는 것이라, HTTP로 도는 로컬에서는 브라우저가 쿠키를 싣지 않는다.

**인증 코드 메일이 오지 않는다**

지금은 메일을 실제로 보내지 않는다. `runserver`를 띄운 터미널에 메일 내용이 출력된다.

## 구조

```
.github/workflows/        서버별 CI
auth-server/              Django 인증 서버 (독립된 uv 프로젝트)
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docker-compose.yml        PostgreSQL, Redis
.env.example              인프라 환경 변수 목록
```