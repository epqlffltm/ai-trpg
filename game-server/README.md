# 게임 서버

[![game-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml)

[ai-trpg](../README.md)의 게임 서버. 방, 자산(세계관, 시나리오, 규칙 등), 판정, AI GM을 맡는다. FastAPI로 만든다.
회원가입과 로그인은 하지 않는다. [인증 서버](../auth-server/README.md)가 발급한 토큰을 공개키로 검증만 한다.

지금은 뼈대만 있다. 서버가 뜨고, DB에 연결되고, 상태를 확인하는 주소가 응답한다. 테이블은 아직 없다.

## 목차

- [실행](#실행)
- [DB와 마이그레이션](#db와-마이그레이션)
- [API](#api)
- [CI](#ci)
- [설계 메모](#설계-메모)

## 실행

명령은 모두 `game-server` 폴더 안에서 실행한다. 저장소 루트에서 `ruff format .`을 돌리면
인증 서버의 파일까지 이 서버의 규칙이 아닌 기본 규칙으로 바뀐다.

### 준비

루트의 [공용 인프라](../README.md)가 떠 있어야 한다. `game` 계정과 스키마는 초기화 스크립트
(`docker/postgres/init/02-game-role.sql`)가 만든다. 이 스크립트는 데이터 볼륨이 비어 있는 첫 기동 때만 실행된다.
스크립트를 추가하기 전에 만든 볼륨이라면 한 번 직접 실행한다. 루트의 `.env`에 `GAME_DB_PASSWORD`를 적고
컨테이너를 다시 만든 뒤(`docker compose up -d`), 저장소 루트에서 실행한다.
`trpg`는 루트 `.env`의 `POSTGRES_USER`와 `POSTGRES_DB` 값이다.

```
docker compose exec db psql -v ON_ERROR_STOP=1 -U trpg -d trpg -f /docker-entrypoint-initdb.d/02-game-role.sql
```

### 설치와 실행

```
cd game-server
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8001 --reload
```

`.env`의 `DATABASE_URL`에 루트 `.env`의 `GAME_DB_PASSWORD`와 같은 비밀번호를 적는다.

인증 서버가 8000번을 쓰므로 8001번으로 띄운다. `http://127.0.0.1:8001/health`가 `{"status":"ok"}`를 돌려주면 서버가 뜬 것이고,
`http://127.0.0.1:8001/health/ready`가 `{"status":"ok"}`를 돌려주면 DB까지 연결된 것이다.

`.env`의 `DEBUG=true`는 API 문서 화면을 켠다. `http://127.0.0.1:8001/api/v1/game/docs`에서 본다.

### 테스트와 검사

```
uv run pytest
uv run ruff check .
uv run ruff format .
```

테스트는 실제 PostgreSQL에서 돈다. 개발용과 같은 DB의 `game_test` 스키마를 쓰므로 개발용 데이터(`game` 스키마)를 건드리지 않는다.
DB가 꺼져 있으면 DB를 쓰는 테스트가 실패한다.

`ruff check`는 쓰지 않는 import나 정의되지 않은 이름 같은 문제를 실행하지 않고 찾는다.
`ruff format`은 코드의 모양을 정해진 규칙으로 맞춘다. 커밋하기 전에 둘 다 돌린다.

## DB와 마이그레이션

테이블 구조의 변경은 Alembic으로 관리한다. DB 주소와 스키마는 앱과 같은 설정에서 읽는다.

```
uv run alembic upgrade head                        # 마이그레이션 적용
uv run alembic revision --autogenerate -m "설명"    # 모델과 DB를 비교해 새 마이그레이션 만들기
uv run alembic check                               # 모델을 바꾸고 마이그레이션을 안 만들었는지 검사
```

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `DATABASE_URL` | 없음(필수) | `postgresql+asyncpg://game:<비밀번호>@127.0.0.1:5432/trpg` 형식 |
| `DB_SCHEMA` | `game` | 테이블이 놓이는 스키마. 테스트는 `game_test`로 고정한다 |
| `DEBUG` | `false` | API 문서 화면을 켠다 |

## API

게임 서버의 API는 `/api/v1/game/` 아래에 놓는다. 아직 없다.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/health` | 서버 프로세스가 살아 있는지 확인 | 불필요 |
| GET | `/health/ready` | 요청을 처리할 준비가 됐는지(DB 연결) 확인. 안 되면 503 | 불필요 |

두 주소는 API 주소 밖에 둔다. 프록시와 컨테이너 관리 도구가 부르는 주소라 버전이 없다.

## CI

PR과 `main` 푸시마다 GitHub Actions가 게임 서버를 검사한다. `game-server/`, DB 초기화 스크립트, 워크플로 파일이 바뀐 경우에만 돈다.
PostgreSQL을 띄우고, 로컬과 같은 초기화 스크립트로 계정과 스키마를 만든 뒤 검사한다.

1. 의존성 설치 (`uv sync --locked`): `uv.lock`과 `pyproject.toml`이 어긋나면 실패한다
2. 린트 (`ruff check`)
3. 모양 검사 (`ruff format --check`): 고치지 않고 검사만 한다
4. 마이그레이션 적용 (`alembic upgrade head`): 빈 DB에 처음부터 끝까지 적용되는지 본다
5. 마이그레이션 누락 검사 (`alembic check`): 모델을 바꾸고 마이그레이션을 만들지 않았으면 실패한다
6. 테스트 (`pytest`)

## 설계 메모

**앱을 함수로 만든다(`create_app`).** 모듈을 불러올 때 바로 만들면 설정이 그 순간에 고정된다.
함수로 두면 테스트가 설정을 바꿔 가며 앱을 여러 개 만들 수 있다.

**설정은 `pydantic-settings`로 읽는다.** 값의 형식을 검사해서, 잘못된 설정이면 서버가 뜨기 전에 오류가 난다.
`.env`는 인증 서버와 따로 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.
DB 주소에는 기본값을 두지 않는다. 기본 주소로 엉뚱한 DB에 붙는 것보다 서버가 뜨지 않는 쪽이 낫다.
테스트는 `.env`에서 DB 주소만 가져오고, 동작을 바꾸는 값(`DEBUG`, `DB_SCHEMA`)은 테스트 코드에서 고정한다.
개발자의 `.env`에 무엇이 적혀 있든 결과가 같아야 한다.

**API 문서 화면은 기본이 꺼짐이다.** 켜는 것을 잊으면 불편할 뿐이지만, 끄는 것을 잊으면 운영 서버의 API 구조가 드러난다.
문서 화면의 주소도 `/api/v1/game/` 아래에 둔다. 프록시가 주소 앞부분으로 서버를 가르기 때문이다.

**살아 있는지(`/health`)와 준비됐는지(`/health/ready`)를 나눈다.** `/health`는 프로세스만 본다. DB까지 확인하면,
DB가 잠깐 느려졌을 때 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다. `/health/ready`는 DB에 닿는지 보고,
안 되면 503을 준다. 이때는 서버를 재시작하지 않고 요청만 보내지 않으면 된다. 실패한 이유는 응답에 싣지 않는다.
오류 문구에 DB 주소와 계정 이름이 들어 있기 때문이다.

**DB 연결(엔진)을 전역 변수로 두지 않고 앱에 붙인다(`app.state`).** 전역으로 두면 모듈을 불러오는 순간에 설정이 고정되어,
테스트가 다른 DB 주소로 앱을 만들 수 없다.

**스키마는 연결할 때 `search_path`로 정한다.** 모델에 스키마 이름을 적지 않는다. 같은 모델과 같은 마이그레이션이
설정 하나(`DB_SCHEMA`)로 개발용 스키마와 테스트용 스키마에서 그대로 돈다.

**테스트는 같은 DB의 다른 스키마(`game_test`)에서 돈다.** 테스트용 DB를 새로 만드는 방식은 계정에 DB를 만드는 권한을 줘야 한다.
스키마를 나누면 그 권한이 필요 없다. 스키마 이름이 `_test`로 끝나지 않으면 테스트가 시작되지 않는다.

**세션을 내주는 함수는 커밋하지 않는다.** 어디까지를 한 묶음으로 저장할지는 서비스가 정한다.
요청이 끝날 때 자동으로 커밋하면, 응답을 만드는 중에 난 오류와 저장이 따로 놀게 된다.

**Alembic은 앱과 같은 방법으로 만든 엔진을 쓴다.** DB 주소를 `alembic.ini`에 따로 적으면 한쪽만 고쳤을 때 서로 다른 DB를 보게 된다.
`alembic.ini`에는 한글을 적지 않는다. 이 파일은 운영체제의 기본 인코딩으로 읽혀서, Windows에서 깨질 수 있다.

**린트와 모양 검사를 처음부터 CI에 넣는다.** 코드가 쌓인 뒤에 넣으면 지적이 한꺼번에 나와 고치는 일이 따로 생긴다.
따옴표는 인증 서버와 같이 작은따옴표로 맞춘다.

**테스트는 서버를 띄우지 않고 앱에 요청을 바로 넘긴다.** 네트워크를 거치지 않아 빠르고, 포트가 겹칠 일이 없다.
