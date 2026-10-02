# ai-trpg

[![auth-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml)

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | `auth-server/` | 회원가입, 로그인(access 토큰), JWKS까지 완료 |
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
| POST | `/api/v1/auth/login` | 로그인. access 토큰 발급 | 불필요 |
| GET | `/api/v1/auth/jwks` | 토큰 검증용 공개키 목록 | 불필요 |
| GET | `/api/v1/auth/me` | 내 계정 정보 | 필요 |

인증이 필요한 API에는 `Authorization: Bearer <access_token>` 헤더를 붙인다.

회원가입 요청 본문은 `username`, `email`, `nickname`, `password`다.
성공하면 `201`과 함께 `public_id`, `username`, `nickname`을 돌려준다.

로그인 요청 본문은 `username`, `password`다. 성공하면 `access_token`, `token_type`,
`expires_in`을 돌려준다. 아이디가 없든 비밀번호가 틀리든 같은 `401` 응답을 준다.

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

**토큰 발급과 검증은 simplejwt에 맡긴다.** 다만 simplejwt는 머리말에 `kid`를 넣지 않아
그 부분만 상속으로 덧붙였다. 로그인 뷰는 직접 두고 발급은 함수 하나(`issue_access_token`)로
감쌌다. 로그인 흐름이 바뀌어도 발급 코드는 그대로 쓴다.

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

## 구조

```
.github/workflows/        서버별 CI
auth-server/              Django 인증 서버 (독립된 uv 프로젝트)
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docker-compose.yml        PostgreSQL, Redis
.env.example              인프라 환경 변수 목록
```