# ai-trpg

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | `auth-server/` | 프로젝트 생성만 완료 |
| 게임 서버 (FastAPI) | `game-server/` | 예정 |
| 프론트엔드 | `web/` | 예정 |

## 요구 사항

- Docker
- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## 실행

### 1. 환경 변수

`.env.example`을 복사해 `.env`를 만들고 `POSTGRES_PASSWORD`를 채운다.
이 파일은 커밋하지 않는다.

```
cp .env.example .env
```

### 2. 인프라

```
docker compose up -d
docker compose ps
```

`db`와 `redis`가 모두 `healthy`이면 정상이다.

## 자주 겪는 문제

**`docker compose ps`에서 db의 포트 칸이 비어 있다**

Windows에서 Hyper-V가 해당 포트를 예약한 경우다. 예약 구간을 확인하고
`.env`의 `POSTGRES_PORT`를 구간 밖의 값으로 바꾼다.

```
netsh interface ipv4 show excludedportrange protocol=tcp
```

## 구조

```
auth-server/          Django 인증 서버 (독립된 uv 프로젝트)
docker-compose.yml    PostgreSQL, Redis
.env.example          환경 변수 목록
```