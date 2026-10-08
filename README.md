# ai-trpg

[![auth-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml)
[![game-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml)

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | [`auth-server/`](auth-server/README.md) | 회원가입(이메일 인증), 로그인(이메일 인증), 비밀번호 변경과 재설정, 메일 발송, 토큰 갱신, 로그아웃, JWKS, 시도 횟수 제한, 보안 이벤트 기록까지 완료 |
| 게임 서버 (FastAPI) | [`game-server/`](game-server/README.md) | 뼈대(서버 실행, DB, 인증 서버 토큰 검증, CI)와 자산 네 종류(세계관, 룰북, 시나리오, 로어북)의 만들기, 목록, 읽기, 고치기, 지우기와 시나리오 게시(판으로 굳히기, 스타팅 여러 개, 추천 인원과 프리젠), 공개와 소개 페이지, 공개 목록, 테이블 만들기와 참가(초대 코드, 로비와 비밀번호, 캐릭터, 방장), 라운드(선언 모으기, 가짜 서술자), 이벤트 기록, 채팅, 실시간 스트림(SSE, "입력 중" 표시), 룰북의 규칙 데이터(내장 템플릿 `srd5`), 시나리오의 캐릭터 시트와 캐릭터 방식, 테이블의 캐릭터 시트, 주사위와 판정(순수 함수), 선언에 붙이는 행동, 라운드를 닫을 때의 판정, 피해와 회복과 쓰러짐, 능력치를 직접 적는 캐릭터 방식, 점수제로 능력치를 사는 캐릭터 방식, 주사위로 능력치를 정하는 캐릭터 방식과 다시 굴리기, 죽음의 굴림과 캐릭터의 죽음, 죽은 뒤에 새 캐릭터 들이기, 캐릭터 보관함까지 완료 |
| 프론트엔드 | `web/` | 예정 |

## 문서

서버마다 설명서를 따로 둔다. 이 문서는 전체 안내와 공용 인프라만 다룬다.

| 문서 | 내용 |
| --- | --- |
| [auth-server/README.md](auth-server/README.md) | 인증 서버의 실행, API, 설계 메모, 운영 메모, 자주 겪는 문제 |
| [game-server/README.md](game-server/README.md) | 게임 서버의 실행, DB와 마이그레이션, API, 토큰 검증, 자산, 게시와 공개, 테이블, 라운드, 이벤트 기록, 채팅, 실시간 스트림, 설계 메모 |

## 요구 사항

- Docker
- Python 3.13
- [uv](https://docs.astral.sh/uv/)

## 실행

인프라를 먼저 띄우고, 그다음 각 서버의 설명서를 따른다.

### 1. 인프라 환경 변수

`.env.example`을 복사해 `.env`를 만들고 `POSTGRES_PASSWORD`, `AUTH_DB_PASSWORD`,
`GAME_DB_PASSWORD`를 채운다. 이 파일은 커밋하지 않는다.

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

### 3. 서버

- 인증 서버: [auth-server/README.md](auth-server/README.md#실행)
- 게임 서버: [game-server/README.md](game-server/README.md#실행)

## 설계 메모

서버 하나에 속하지 않는 결정만 적는다. 서버별 결정은 각 서버의 설명서에 있다.

**설정 파일을 서버마다 따로 둔다.** 루트 `.env`는 인프라용이고, 서버의 비밀값은
각 서버 폴더의 `.env`에 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.

**DB 인스턴스는 하나, 계정과 스키마는 서버마다 따로 쓴다.** 인증 서버는 `auth` 계정으로
`auth` 스키마만, 게임 서버는 `game` 계정으로 `game` 스키마만 쓴다. 다른 서버의 테이블을 직접 읽는 코드는 DB 권한에서 거부된다.
서버 간 데이터 교환은 API로만 한다.

**로그인은 인증 서버만 한다.** 다른 서버는 인증 서버의 공개키로 토큰을 검증만 한다.
인증 서버의 DB를 보지 않고, 요청마다 인증 서버를 부르지도 않는다. 사용자는 토큰의 `sub`(`public_id`)로만 가리킨다.

## 자주 겪는 문제

인프라에 관한 것만 적는다. 서버별 문제는 각 서버의 설명서에 있다.

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
game-server/              FastAPI 게임 서버 (독립된 uv 프로젝트)
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docker-compose.yml        PostgreSQL, Redis
.env.example              인프라 환경 변수 목록
```
