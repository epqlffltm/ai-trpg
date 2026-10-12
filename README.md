# ai-trpg

[![auth-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml)
[![game-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml)
[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)
[![billing-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/billing-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/billing-server.yml)

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | [`auth-server/`](auth-server/README.md) | 회원가입(이메일 인증), 로그인(이메일 인증), 비밀번호 변경과 재설정, 메일 발송, 토큰 갱신, 로그아웃, JWKS, 시도 횟수 제한, 보안 이벤트 기록, 가입한 사용자의 환영 크레딧을 결제 서버에 맡기기, access 토큰에 닉네임 싣기까지 완료 |
| 게임 서버 (FastAPI) | [`game-server/`](game-server/README.md) | 뼈대(서버 실행, DB, 인증 서버 토큰 검증, CI)와 자산 네 종류(세계관, 룰북, 시나리오, 로어북)의 만들기, 목록, 읽기, 고치기, 지우기와 시나리오 게시(판으로 굳히기, 스타팅 여러 개, 추천 인원과 프리젠), 공개와 소개 페이지, 공개 목록, 테이블 만들기와 참가(초대 코드, 로비와 비밀번호, 캐릭터, 방장), 라운드(선언 모으기, 가짜 서술자), 이벤트 기록, 채팅, 실시간 스트림(SSE, "입력 중" 표시), 룰북의 규칙 데이터(내장 템플릿 `srd5`), 시나리오의 캐릭터 시트와 캐릭터 방식, 테이블의 캐릭터 시트, 주사위와 판정(순수 함수), 선언에 붙이는 행동, 라운드를 닫을 때의 판정, 피해와 회복과 쓰러짐, 능력치를 직접 적는 캐릭터 방식, 점수제로 능력치를 사는 캐릭터 방식, 주사위로 능력치를 정하는 캐릭터 방식과 다시 굴리기, 죽음의 굴림과 캐릭터의 죽음, 죽은 뒤에 새 캐릭터 들이기, 캐릭터 보관함, 라운드의 서술 값 받기(결제 서버의 홀드), 테이블마다 고르는 서술 등급(standard·premium)까지 완료 |
| 게시판 서버 (NestJS) | [`board-server/`](board-server/README.md) | 뼈대(서버 실행, 설정, DB 연결과 마이그레이션, CI), 인증 서버 토큰 검증, 게시판 넷과 글(쓰기, 목록, 읽기, 고치기, 지우기, 운영자), 댓글과 답글, 글마다의 댓글 수, 글 고정(기한이 지나면 저절로 내려감), 글 검색, 쓰기 횟수 제한, 글과 댓글의 신고(운영자가 묶어 읽고 처리), 글쓴이의 닉네임 표시까지 완료 |
| 결제 서버 (Go) | [`billing-server/`](billing-server/README.md) | 뼈대, 인증 서버 토큰 검증, 지갑과 원장(산 크레딧과 기한이 있는 무료 크레딧), 주문과 충전(가짜 결제 대행사, 중복 방지 키, 알림), 환영 크레딧(인증 서버가 맡긴다), 홀드·확정·반환과 서버 간 서명, 홀드와 주문의 만료·연장과 정리 작업, 하루 한 번의 대사, DB 의 가격표(모델별 서술 값)까지 완료. 게임 서버가 라운드의 서술 값을 홀드로 받는다. 실제 결제가 아니라 연습용이다 |
| 프론트엔드 | `web/` | 예정 |

## 문서

서버마다 설명서를 따로 둔다. 이 문서는 전체 안내와 공용 인프라만 다룬다.

| 문서 | 내용 |
| --- | --- |
| [auth-server/README.md](auth-server/README.md) | 인증 서버의 실행, API, 설계 메모, 운영 메모, 자주 겪는 문제 |
| [game-server/README.md](game-server/README.md) | 게임 서버의 실행, DB와 마이그레이션, API, 토큰 검증, 자산, 게시와 공개, 테이블, 라운드, 이벤트 기록, 채팅, 실시간 스트림, 설계 메모 |
| [board-server/README.md](board-server/README.md) | 게시판 서버의 실행, DB와 마이그레이션, API(글, 댓글, 고정, 검색, 쓰기 횟수 제한, 신고, 글쓴이의 닉네임), 구조, 로그와 요청 식별자, 설계 메모 |
| [billing-server/README.md](billing-server/README.md) | 결제 서버의 실행, 설정, API, 주문과 결제, 홀드, 크레딧, 정리 작업과 대사, 마이그레이션, 토큰 검증, 테스트, CI, 구조, 설계 메모 |
| [docs/observability.md](docs/observability.md) | 네 서버가 함께 지키는 관측 규격. 로그의 모양, 요청·추적·작업 식별자, 민감정보, health 와 readiness, 메트릭의 이름, 관리 서버의 경계 |

## 요구 사항

- Docker
- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Node.js 24 (게시판 서버)
- Go 1.27 (결제 서버)

## 실행

인프라를 먼저 띄우고, 그다음 각 서버의 설명서를 따른다.

### 1. 인프라 환경 변수

`.env.example`을 복사해 `.env`를 만들고 `POSTGRES_PASSWORD`, `AUTH_DB_PASSWORD`,
`GAME_DB_PASSWORD`, `BILLING_DB_PASSWORD`, `BOARD_DB_PASSWORD`를 채운다. 이 파일은 커밋하지 않는다.

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
- 게시판 서버: [board-server/README.md](board-server/README.md#실행)
- 결제 서버: [billing-server/README.md](billing-server/README.md#실행)

### 4. 서버 넷을 컨테이너로 (선택)

개발은 3번처럼 PC 에서 직접 띄운다. 네 서버를 한꺼번에 컨테이너로 띄워 보려면 프로필 `app` 을 붙인다.
PC 에서 직접 띄운 서버와 같은 포트(8000~8003)를 쓰므로 그것들을 먼저 끈다.

```
docker compose --profile app up -d --build
docker compose --profile app ps -a
```

`*-migrate` 넷이 `Exited (0)`, `*-server` 넷이 `healthy` 면 된다. 끌 때는 `docker compose --profile app down` 이다.

- 서버의 설정은 3번에서 만든 각 서버의 `.env` 를 그대로 쓴다. 그 안의 주소(`127.0.0.1`)만 compose 가
  컨테이너의 이름(`db`, `redis`, `auth-server` 등)으로 바꿔 넘긴다. DB 주소는 루트 `.env` 의 비밀번호로 만든다.
- 모든 서버를 함께 띄우므로 게임 서버는 결제 서버에 붙는다. `game-server/.env` 에 `BILLING_SECRET` 이 있어야 뜬다.
- 게임 서버의 언어 모델은 컨테이너 밖, 이 PC 의 Ollama(`host.docker.internal:11434`)로 간다.
  다른 곳의 모델을 쓰면 루트 `.env` 의 `GAME_LLM_BASE_URL` 에 적는다. `game-server/.env` 의 `LLM_BASE_URL` 은 덮인다.
- 인증 서버의 JWT 개인키는 `auth-server/keys/` 를 읽기 전용으로 붙인다. 이미지에는 넣지 않는다.
  **리눅스에서는** 키 파일의 주인이 PC 의 사용자라 컨테이너의 사용자(번호 10001)가 읽지 못한다.
  `sudo chown 10001 auth-server/keys/jwt-private.pem` 으로 주인을 바꾼다(권한은 600 그대로). Docker Desktop(Windows, macOS)에서는 그대로 읽힌다.
- 포트가 다른 프로그램과 겹치면 루트 `.env` 의 `AUTH_PORT`, `GAME_PORT`, `BOARD_PORT`, `BILLING_PORT` 로 바꾼다.

## 설계 메모

서버 하나에 속하지 않는 결정만 적는다. 서버별 결정은 각 서버의 설명서에 있다.

**설정 파일을 서버마다 따로 둔다.** 루트 `.env`는 인프라용이고, 서버의 비밀값은
각 서버 폴더의 `.env`에 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.

**DB 인스턴스는 하나, 계정과 스키마는 서버마다 따로 쓴다.** 인증 서버는 `auth` 계정으로
`auth` 스키마만, 게임 서버는 `game` 계정으로 `game` 스키마만, 결제 서버는 `billing` 계정으로 `billing` 스키마만, 게시판 서버는 `board` 계정으로 `board` 스키마만 쓴다. 다른 서버의 테이블을 직접 읽는 코드는 DB 권한에서 거부된다.
게임 서버의 테스트(`game-server/tests/test_schema_isolation.py`)가 이 경계를 확인한다. 새 서버를 더하면 그 서버의 테스트에도 자기 계정으로 같은 검사를 둔다.
서버 간 데이터 교환은 API로만 한다.

**로그인은 인증 서버만 한다.** 다른 서버는 인증 서버의 공개키로 토큰을 검증만 한다.
인증 서버의 DB를 보지 않고, 요청마다 인증 서버를 부르지도 않는다. 사용자는 토큰의 `sub`(`public_id`)로만 가리킨다.

**`main` 은 보호 규칙으로 지킨다.** 지우기와 강제 푸시를 막고, PR 로만 넣는다(승인은 0). 소유자도 예외가 아니다.
머지하려면 필수 검사 `ci-ok` 가 통과해야 한다. `ci-ok` 는 PR 의 관문(`.github/workflows/ci.yml`)이 마지막에 내는 결과다.
관문은 바뀐 파일을 보고 그 서버의 CI 만 부른다(`.github/scripts/changed-servers.sh`). 부르지 않은 서버는 건너뛴 것이고 통과로 친다.
서버의 CI 넷을 따로 필수로 걸지 않은 이유: 서버마다 자기 폴더가 바뀔 때만 돈다. 돌지 않은 필수 검사를 GitHub 은 "기다리는 중"으로 두고 머지를 막는다.
DB 초기화 스크립트, compose 파일, 관문 자신이 바뀌면 넷 다 돈다. `main` 에 들어간 뒤에는 서버의 CI 가 예전처럼 제 폴더가 바뀔 때만 스스로 돈다. 위의 배지가 그 결과다.
서버가 하나라도 바뀌면 관문의 `stack` 이 네 서버의 이미지를 만들어 compose 로 함께 띄우고, 마이그레이션이 성공했는지와 서버끼리 닿는지를 본다(`.github/scripts/stack-smoke.sh`).

**이미지는 서버마다 같은 규칙으로 만든다.** 여러 단계로 빌드해 실행에 필요한 것만 담고, root 가 아닌 사용자(번호로 적는다)로 돌린다.
기본 이미지는 버전을 고정한다. 비밀(`.env`, JWT 키)은 `.dockerignore` 로 막아 이미지에 넣지 않고, 띄울 때 compose 가 넘긴다.
파이썬과 노드는 Debian slim 을 쓴다. 미리 빌드된 패키지(휠)가 대부분 glibc 용이라 alpine 에서는 소스에서 빌드하느라 느리고 잘 깨진다.
결제 서버는 C 라이브러리에 기대지 않는 실행 파일 하나라 alpine 을 쓴다. 상태 확인에 쓰는 `wget` 이 들어 있다.

**마이그레이션은 서버가 뜰 때 돌리지 않는다.** 서버마다 한 번 돌고 끝나는 컨테이너(`*-migrate`)가 하고, 서버는 그것이 성공해야 뜬다.
서버를 여럿 띄워도 마이그레이션은 한 번만 돈다. 실패하면 서버가 뜨지 않아서 바로 드러난다.

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
.github/workflows/        서버별 CI 와 PR 의 관문(ci.yml)
.github/scripts/          관문이 검사할 서버를 고르는 스크립트와 그 테스트, 컨테이너로 띄워 보는 스크립트
auth-server/              Django 인증 서버 (독립된 uv 프로젝트)
game-server/              FastAPI 게임 서버 (독립된 uv 프로젝트)
board-server/             NestJS 게시판 서버 (독립된 npm 프로젝트)
billing-server/           Go 결제 서버 (독립된 Go 모듈). 연습용이고 실제 결제가 아니다
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docs/                     서버들이 함께 지키는 규격 (관측)
docker-compose.yml        PostgreSQL, Redis, 서버 넷(프로필 app)
.env.example              인프라 환경 변수 목록
```
