# ai-trpg

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | `auth-server/` | 설정과 DB 연결까지 완료, 기능 없음 |
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

```
uv run python manage.py check --database default
```

## 설계 메모

**설정 파일을 서버마다 따로 둔다.** 루트 `.env`는 인프라용이고, 서버의 비밀값은
각 서버 폴더의 `.env`에 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.

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
auth-server/              Django 인증 서버 (독립된 uv 프로젝트)
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docker-compose.yml        PostgreSQL, Redis
.env.example              인프라 환경 변수 목록
```
