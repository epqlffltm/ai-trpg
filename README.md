# ai-trpg

[![auth-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/auth-server.yml)
[![game-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/game-server.yml)
[![board-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/board-server.yml)
[![billing-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/billing-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/billing-server.yml)
[![notification-server](https://github.com/epqlffltm/ai-trpg/actions/workflows/notification-server.yml/badge.svg)](https://github.com/epqlffltm/ai-trpg/actions/workflows/notification-server.yml)

AI GM이 진행하는 TRPG 플랫폼. 판정은 게임 엔진이 하고 LLM은 서술만 담당한다.

## 현재 상태

개발 초기 단계다. 아래 표에서 완료로 표시된 것만 동작한다.

| 구성 요소 | 폴더 | 상태 |
| --- | --- | --- |
| 공용 인프라 (PostgreSQL + pgvector, Redis) | 루트 | 완료 |
| 인증 서버 (Django) | [`auth-server/`](auth-server/README.md) | 회원가입(이메일 인증), 로그인(이메일 인증), 비밀번호 변경과 재설정, 메일 발송, 토큰 갱신, 로그아웃, JWKS, 시도 횟수 제한, 보안 이벤트 기록, 가입한 사용자의 환영 크레딧을 결제 서버에 맡기기, access 토큰에 닉네임 싣기까지 완료 |
| 게임 서버 (FastAPI) | [`game-server/`](game-server/README.md) | 뼈대(서버 실행, DB, 인증 서버 토큰 검증, CI)와 자산 네 종류(세계관, 룰북, 시나리오, 로어북)의 만들기, 목록, 읽기, 고치기, 지우기와 시나리오 게시(판으로 굳히기, 스타팅 여러 개, 추천 인원과 프리젠), 공개와 소개 페이지, 공개 목록, 테이블 만들기와 참가(초대 코드, 로비와 비밀번호, 캐릭터, 방장), 라운드(선언 모으기, 가짜 서술자), 이벤트 기록, 채팅, 실시간 스트림(SSE, "입력 중" 표시), 룰북의 규칙 데이터(내장 템플릿 `srd5`), 시나리오의 캐릭터 시트와 캐릭터 방식, 테이블의 캐릭터 시트, 주사위와 판정(순수 함수), 선언에 붙이는 행동, 라운드를 닫을 때의 판정, 피해와 회복과 쓰러짐, 능력치를 직접 적는 캐릭터 방식, 점수제로 능력치를 사는 캐릭터 방식, 주사위로 능력치를 정하는 캐릭터 방식과 다시 굴리기, 죽음의 굴림과 캐릭터의 죽음, 죽은 뒤에 새 캐릭터 들이기, 캐릭터 보관함, 라운드의 서술 값 받기(결제 서버의 홀드), 시나리오의 추천 서술 모델과 테이블마다 고르는 서술 모델까지 완료 |
| 게시판 서버 (NestJS) | [`board-server/`](board-server/README.md) | 뼈대(서버 실행, 설정, DB 연결과 마이그레이션, CI), 인증 서버 토큰 검증, 게시판 넷과 글(쓰기, 목록, 읽기, 고치기, 지우기, 운영자), 댓글과 답글, 글마다의 댓글 수, 글 고정(기한이 지나면 저절로 내려감), 글 검색, 쓰기 횟수 제한, 글과 댓글의 신고(운영자가 묶어 읽고 처리), 글쓴이의 닉네임 표시까지 완료 |
| 결제 서버 (Go) | [`billing-server/`](billing-server/README.md) | 뼈대, 인증 서버 토큰 검증, 지갑과 원장(산 크레딧과 기한이 있는 무료 크레딧), 주문과 충전(가짜 결제 대행사, 중복 방지 키, 알림), 토스페이먼츠 테스트 모드(결제위젯, 승인, 조회, 취소, 알림), 7일 안의 청약철회(주문마다 산 크레딧의 묶음), 환영 크레딧(인증 서버가 맡긴다), 홀드·확정·반환과 서버 간 서명, 홀드와 주문의 만료·연장과 정리 작업, 하루 한 번의 대사, DB 의 가격표(모델별 서술 값)까지 완료. 게임 서버가 라운드의 서술 값을 홀드로 받는다. 실제 결제가 아니라 연습용이다 |
| 알림 서버 (FastAPI) | [`notification-server/`](notification-server/README.md) | 뼈대(서버 실행, 설정, DB 연결과 마이그레이션, 상태 확인, CI), 알림 넣기(서버끼리의 서명), 알림함(목록, 읽지 않은 수, 읽음), 인증 서버 토큰 검증과 끊긴 세션, 공통 관측 규격, 보관 기간(30일) 정리, 컨테이너(compose 의 프로필 `app`)까지 완료. 게임 서버가 서술 모델의 은퇴를 방장에게, 운영자의 제재를 당사자에게 넣는다. 결제와 게시판 서버가 넣는 쪽은 아직이다 |
| 프론트엔드 | `web/` | 예정 |

## 문서

서버마다 설명서를 따로 둔다. 이 문서는 전체 안내와 공용 인프라만 다룬다.

| 문서 | 내용 |
| --- | --- |
| [auth-server/README.md](auth-server/README.md) | 인증 서버의 실행, API, 설계 메모, 운영 메모, 자주 겪는 문제 |
| [game-server/README.md](game-server/README.md) | 게임 서버의 실행, DB와 마이그레이션, API, 토큰 검증, 자산, 게시와 공개, 테이블, 라운드, 이벤트 기록, 채팅, 실시간 스트림, 설계 메모 |
| [board-server/README.md](board-server/README.md) | 게시판 서버의 실행, DB와 마이그레이션, API(글, 댓글, 고정, 검색, 쓰기 횟수 제한, 신고, 글쓴이의 닉네임), 구조, 로그와 요청 식별자, 설계 메모 |
| [notification-server/README.md](notification-server/README.md) | 알림 서버의 실행, 설정, 상태 확인, 알림함과 알림 넣기 API, 토큰 검증, 보관 기간, 로그, DB 와 마이그레이션, 테스트 |
| [billing-server/README.md](billing-server/README.md) | 결제 서버의 실행, 설정, API, 주문과 결제, 홀드, 크레딧, 정리 작업과 대사, 마이그레이션, 토큰 검증, 테스트, CI, 구조, 설계 메모 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 기여 지침. 서버의 경계, 기본 검사, 브랜치와 PR 의 모양 |
| [SECURITY.md](SECURITY.md) | 보안 정책. 취약점을 비공개로 알리는 길 |
| [docs/observability.md](docs/observability.md) | 서버들이 함께 지키는 관측 규격. 로그의 모양, 요청·추적·작업 식별자, 민감정보, health 와 readiness, 메트릭의 이름, 관리 서버의 경계 |
| [docs/README.md](docs/README.md) | 문서 안내. 서비스 구조 명세, 공용 코드 규칙, 플랫폼과 제품 방향, 화면 명세, AI 챗 서비스 조사 |

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
`GAME_DB_PASSWORD`, `BILLING_DB_PASSWORD`, `BOARD_DB_PASSWORD`, `NOTIFICATION_DB_PASSWORD`를 채운다. 이 파일은 커밋하지 않는다.
개발 PC 에서는 `AUTH_DB_ALLOW_TEST_DB=true` 를 그대로 둔다. 인증 서버의 테스트가 테스트용 DB 를 만든다. 운영에서는 이 줄을 지운다.

```
cp .env.example .env
```

### 2. 인프라

```
docker compose up -d
docker compose ps
```

`db`, `redis`, `db-backup`이 모두 `healthy`이면 정상이다. `db-backup`은 첫 백업을 뜬 뒤에 `healthy`가 된다([백업과 복원](#백업과-복원)).

첫 기동 때 `docker/postgres/init/`의 스크립트가 서버별 DB 계정과 스키마를 만든다.
이 스크립트는 데이터 볼륨이 비어 있을 때만 실행된다.

### 3. 서버

- 인증 서버: [auth-server/README.md](auth-server/README.md#실행)
- 게임 서버: [game-server/README.md](game-server/README.md#실행)
- 게시판 서버: [board-server/README.md](board-server/README.md#실행)
- 결제 서버: [billing-server/README.md](billing-server/README.md#실행)
- 알림 서버: [notification-server/README.md](notification-server/README.md#실행)

### 4. 모든 서버를 컨테이너로 (선택)

개발은 3번처럼 PC 에서 직접 띄운다. 모든 서버를 한꺼번에 컨테이너로 띄워 보려면 프로필 `app` 을 붙인다.
인증 서버와 같은 포트(8000)를 쓰므로 PC 에서 직접 띄운 인증 서버를 먼저 끈다.

```
docker compose --profile app up -d --build
docker compose --profile app ps -a
```

`*-migrate` 다섯이 `Exited (0)`, `*-server` 다섯과 `proxy` 와 워커 넷(`auth-mail`, `auth-welcome-credits`, `billing-sweeper`, `db-backup`)이 `healthy`,
cron 둘(`auth-cron`, `billing-cron`)이 `Up` 이면 된다.
서버의 `healthy` 는 그 서버가 DB 에 닿는다는 뜻이다(healthcheck 가 `/health/ready` 를 부른다). DB 가 죽으면 `unhealthy` 로 보이고, DB 가 돌아오면 저절로 `healthy` 가 된다.
워커의 `healthy` 는 그 워커가 DB 에 닿으며 돈다는 뜻이다(2분 안에 한 바퀴를 끝냈다. `docs/observability.md` 의 "워커의 상태").
끌 때는 `docker compose --profile app down` 이다. 켜 둔 채 Docker Desktop 을 껐다 켜면 다시 뜬다(`restart: unless-stopped`).

- 바깥에서는 프록시 하나로 들어온다. `http://127.0.0.1:8080/api/v1/<auth|game|board|billing|notification>/...` 이다. 서버들의 포트는 열지 않는다.
- 관리자 화면은 프록시가 막는다(404). 인증 서버만 `127.0.0.1:8000` 을 따로 열어 두었으니 `http://localhost:8000/admin/` 으로 연다.
  서버(VM)에 올린 뒤에는 SSH 터널로 붙는다. `ssh -L 8000:127.0.0.1:8000 <서버>` 를 띄워 두고 같은 주소를 연다.
  운영에서는 관리자 화면의 쿠키가 Secure 다. 브라우저는 `localhost` 에서만 HTTP 로도 그 쿠키를 주고받으므로 이 주소로 연다.
- 서버의 설정은 3번에서 만든 각 서버의 `.env` 를 그대로 쓴다. 그 안의 주소(`127.0.0.1`)만 compose 가
  컨테이너의 이름(`db`, `redis`, `auth-server` 등)으로 바꿔 넘긴다. DB 주소는 루트 `.env` 의 비밀번호로 만든다.
- 모든 서버를 함께 띄우므로 게임 서버와 인증 서버는 결제 서버에 붙는다. `game-server/.env` 와 `auth-server/.env` 에 `BILLING_SECRET` 이 있어야 한다.
  없으면 게임 서버가 뜨지 않고, 인증 서버의 환영 크레딧 워커가 오류로 끝나 다시 뜨기를 되풀이한다.
- 알림 서버는 `notification-server/.env` 가 있어야 뜬다. 알림을 넣는 서버의 서명 비밀(`*_SERVER_SECRET`)은 비어 있어도 뜨고, 그 서버의 알림만 401 로 받지 않는다.
- 게임 서버는 방장에게 보내는 알림을 알림 서버에 넣는다. `game-server/.env` 에 `NOTIFICATION_SECRET` 이 있어야 뜨고,
  그 값이 `notification-server/.env` 의 `GAME_SERVER_SECRET` 과 같아야 알림이 들어간다(다르면 401 로 발송함에 쌓인다).
  두 값을 맞추는 명령은 [게임 서버의 알림 보내기](game-server/README.md#알림-보내기)에 있다.
- 게임 서버의 언어 모델은 컨테이너 밖, 이 PC 의 Ollama(`host.docker.internal:11434`)로 간다.
  다른 곳의 모델을 쓰면 루트 `.env` 의 `GAME_LLM_BASE_URL` 에 적는다. `game-server/.env` 의 `LLM_BASE_URL` 은 덮인다.
- 인증 서버의 JWT 개인키는 `auth-server/keys/` 를 읽기 전용으로 붙인다. 이미지에는 넣지 않는다.
  토큰에 서명하는 `auth-server` 에만 붙인다. 인증의 워커와 마이그레이션은 키 없이 뜬다(`JWT_PRIVATE_KEY_PATH` 를 비운다).
  **리눅스에서는** 키 파일의 주인이 PC 의 사용자라 컨테이너의 사용자(번호 10001)가 읽지 못한다.
  `sudo chown 10001 auth-server/keys/jwt-private.pem` 으로 주인을 바꾼다(권한은 600 그대로). Docker Desktop(Windows, macOS)에서는 그대로 읽힌다.
- 서버의 `.env` 는 통째로 넘어가지만, 비밀은 그것을 쓰는 프로세스에만 간다(#274). 쓰지 않는 비밀은 compose 가 빈 값으로 덮는다.
  예를 들어 결제 서버의 정리 작업은 요청의 서명을 확인하는 비밀을, 게임 서버의 마이그레이션은 모델의 키를 받지 않는다.
  어느 프로세스가 무엇을 받는지는 `.github/scripts/secret_scope.py` 의 표에 있다. 새 비밀을 더하면 그 표에도 적는다. 표에 없으면 CI(`stack`)가 실패한다.
- 포트가 다른 프로그램과 겹치면 루트 `.env` 의 `PROXY_PORT`(8080), `AUTH_PORT`(8000)로 바꾼다.

## 백업과 복원

`db-backup` 이 DB 하나를 통째로 한 파일로 뜬다(#274). 인프라를 띄우면 함께 뜨고, 지금 한 번, 그 뒤로 하루에 한 번 뜬다.
파일은 PC 의 폴더(루트 `.env` 의 `BACKUP_DIR`, 기본은 저장소의 `backups/`)에 `trpg-<UTC 시각>.dump` 로 쌓이고 최근 14개(`BACKUP_KEEP`)만 남는다.

```
docker compose run --rm db-backup once     # 지금 한 번 뜬다
docker compose run --rm db-backup check    # 가장 최근 백업을 빈 DB 에 풀어 표마다 줄 수가 원본과 같은지 본다
```

- 모든 서버의 스키마가 같은 순간의 상태로 한 파일에 든다. 서버끼리 짝이 맞아야 하는 줄(게임의 홀드 기록과 결제의 홀드)이 있어서 서버마다 따로 뜨지 않는다
- 테스트용 스키마(`*_test`)와 DB 계정은 뜨지 않는다. 계정은 새 볼륨에서 초기화 스크립트가 만든다
- Redis 는 뜨지 않는다. 시도 횟수와 캐시뿐이라 사라져도 다시 쌓인다
- 복원이 되는지는 CI(`stack`)가 PR 마다 본다. 마이그레이션을 마친 DB 를 뜨고, 같은 DB 서버의 빈 DB 에 풀어 표마다 줄 수를 맞춰 본다
- **백업에는 이메일, 비밀번호 해시, 결제 원장이 들어 있다.** 파일은 주인만 읽게(600) 만든다. 리눅스에서는 주인이 root 라 `sudo` 로 읽는다.
  `docker compose down -v` 로 볼륨을 지워도 백업은 남지만, 같은 디스크라 디스크가 망가지면 함께 사라진다. 다른 장비(NAS 등)에 복사해 둔다.
  옮길 때는 암호화한다. 예: `gpg --symmetric --cipher-algo AES256 trpg-<시각>.dump`
- `.env` 와 JWT 키(`auth-server/keys/`)는 백업에 넣지 않는다. 백업과 같은 곳에 두면 그 하나로 모든 것이 열린다. 따로, 다른 곳에 둔다

**복원.** 서버를 모두 끄고 DB 를 새로 만든 뒤 푼다. 지금의 데이터는 백업 시점의 것으로 바뀐다.

```
docker compose --profile app stop          # 컨테이너로 띄운 서버가 있으면. PC 에서 띄운 서버도 끈다
docker compose down -v                     # 볼륨이 망가졌을 때만. 지금의 데이터가 사라진다
docker compose up -d db                    # 새 볼륨이면 초기화 스크립트가 계정과 스키마를 만든다
docker compose run --rm --entrypoint pg_restore db-backup --clean --if-exists --exit-on-error --dbname=trpg /backups/trpg-<시각>.dump
```

`--clean --if-exists` 는 백업에 든 것을 지우고 다시 만든다. 초기화 스크립트가 만든 빈 스키마 위에 그대로 풀린다.
`--dbname` 은 루트 `.env` 의 `POSTGRES_DB` 다(기본 `trpg`). 다 풀면 서버를 띄운다. 마이그레이션은 이미 백업에 든 상태라 할 일이 없다.
풀기 전에는 `db` 만 띄운다. `docker compose up -d` 로 모두 띄우면 `db-backup` 이 곧바로 빈 DB 를 하나 떠서 쌓는다.

## 외부에 열기 전

로컬에서는 모두 이 PC(127.0.0.1)에서만 닿는다. VM 에 올려 바깥에 열 때 지킬 것이다(#274, #353).
TLS(HTTPS)를 실제로 붙이는 일은 도메인과 배포할 곳이 정해진 뒤에 한다. 여기에는 그때 무엇을 바꾸는지를 적는다.

**바깥에서 닿는 길은 프록시 하나다.** compose 가 여는 포트는 넷이고 모두 `127.0.0.1` 에 묶었다.

| 서비스 | 포트 | 까닭 |
| --- | --- | --- |
| `proxy` | `127.0.0.1:8080` | 바깥의 요청이 들어오는 입구. 운영에서는 이 자리가 443 이 된다 |
| `auth-server` | `127.0.0.1:8000` | 관리자 화면. SSH 터널로만 붙는다(`ssh -L 8000:127.0.0.1:8000 <서버>`) |
| `db`, `redis` | `127.0.0.1` | PC 에서 직접 띄운 서버가 붙는다 |

- 게임, 게시판, 결제 서버와 워커는 포트를 열지 않는다. 열면 프록시의 요청 수 제한과 경로 차단을 건너뛰는 길이 된다
- **Docker 는 VM 의 방화벽(ufw 등)을 거치지 않고 포트를 연다.** `127.0.0.1:` 을 빼면 방화벽이 있어도 그 포트가 바로 바깥에 열린다.
  CI(`stack`)가 이것을 본다(`.github/scripts/port_scope.py`). 포트를 열어도 되는 서비스는 그 파일의 표에 까닭과 함께 적는다
- `network_mode: host` 는 쓰지 않는다. 컨테이너가 VM 의 네트워크를 그대로 쓰면 `ports` 와 상관없이 다 열린다

**프록시는 믿을 수 있는 머리말만 넘긴다.** 프록시 뒤의 서버는 프록시가 정한 머리말만 믿을 수 있다. 클라이언트가 지어 보낸 것은 지우거나 덮는다.

| 머리말 | 프록시가 하는 일 | 읽는 쪽 |
| --- | --- | --- |
| `X-Forwarded-For` | 받은 것 뒤에 연결한 상대의 주소를 덧붙인다. 앞쪽은 클라이언트가 지어낼 수 있다 | 인증 서버가 뒤에서 `TRUSTED_PROXY_COUNT`(1) 번째만 믿는다 |
| `X-Forwarded-Proto` | 프록시의 연결 방식(`$scheme`)으로 덮는다 | 인증 서버(`SECURE_PROXY_SSL_HEADER`, 프록시를 믿을 때만) |
| `X-Real-IP` | 연결한 상대의 주소로 덮는다 | 결제 서버의 gin 이 읽을 수 있다. 덮지 않으면 클라이언트가 주소를 지어낸다 |
| `Forwarded`, `X-Forwarded-Host` | 지운다 | 이 저장소의 서버는 읽지 않는다. 라이브러리가 읽게 되는 날을 막아 둔다 |
| `X-Request-ID` | nginx 가 정한 값으로 덮는다 | 모든 서버의 로그 |

IP 를 쓰는 것은 인증 서버(시도 횟수)와 프록시(요청 수 제한, 연결한 상대의 주소로 센다)뿐이다. 게임, 게시판, 결제, 알림 서버는 IP 를 쓰지 않는다.

**프록시는 모든 응답에 보안 머리말을 붙인다(#361).** 서버의 응답과 프록시가 직접 낸 404·429·502 모두다. 서버가 같은 머리말을 보내면 지우고 이 값 하나만 보낸다.

| 머리말 | 값 | 막는 것 |
| --- | --- | --- |
| `X-Content-Type-Options` | `nosniff` | JSON 을 HTML 이나 스크립트로 짐작해 실행하는 것. 게시판처럼 사용자의 글을 돌려주는 응답에서 특히 |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` | API 응답이 문서로 열려도 아무것도 불러오거나 실행하지 못한다. 다른 사이트의 iframe 에 들어가지 못한다 |
| `Referrer-Policy` | `no-referrer` | 주소에 든 값이 다른 사이트로 새는 것 |

- 값은 `docker/nginx/templates/security-headers.inc.template` 한 곳에 있다
- nginx 는 location 에 `add_header` 가 하나라도 있으면 server 의 `add_header` 를 모두 버린다. 그래서 `add_header` 를 쓰는 location 은 그 파일을 `include` 한다.
  빠뜨리면 그 응답에서만 조용히 빠진다. CI(`stack`)가 서버의 응답, 막은 주소의 404, 429 에서 본다
- 이 CSP 는 API 의 것이다. 화면(#290)을 이 프록시로 내주게 되면 화면에는 화면에 맞는 값을 따로 둔다. HSTS 는 TLS 를 붙일 때 함께 붙인다

**컨테이너의 로그는 서비스마다 상한이 있다(#358).** Docker 의 기본은 로그 파일을 끝없이 키운다. VM 에서 오래 띄우면 디스크가 차고, 그러면 DB 가 쓰지 못해 멈춘다.

- `docker-compose.yml` 의 `x-logging`(json-file, 파일 하나 10MB, 5개까지)을 모든 서비스가 `logging: *logging` 으로 쓴다. 서비스마다 최대 50MB, 17개면 850MB 쯤이다
- 새 서비스가 이것을 빠뜨리면 CI(`stack`)가 실패한다(`.github/scripts/logging_scope.py`). 띄운 컨테이너에 상한이 실제로 붙었는지도 본다
- 지난 로그는 상한을 넘으면 사라진다. 오래 남기고 찾아보는 일은 로그를 한곳에 모을 때(#25) 한다
- VM 을 만들 때 Docker 의 기본값에도 같은 상한을 둔다. compose 밖에서 띄운 컨테이너(`docker run` 으로 잠깐 띄운 것)도 디스크를 채우지 않는다.
  `/etc/docker/daemon.json` 에 아래를 적고 Docker 를 다시 띄운다. 이미 만든 컨테이너에는 붙지 않는다

  ```json
  { "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
  ```

**TLS 는 nginx 가 직접 끝낸다(기본).** VM 한 대라면 앞에 한 단계를 더 두지 않는다. 지금의 규칙(프록시가 하나)이 그대로라 바꿀 것이 가장 적다. 붙일 때 할 일:

- nginx 가 `8443`(TLS)과 `8080`(HTTP)을 듣는다. 이미지(nginx-unprivileged)는 1024 아래의 포트를 열 수 없으므로 compose 가 `443:8443`, `80:8080` 으로 잇는다
- 바깥에 여는 그 둘을 `port_scope.py` 의 `PUBLIC_PORTS` 에 적는다. 그 밖은 그대로 `127.0.0.1` 이다
- 인증서는 Let's Encrypt 로 받는다. 받는 일(HTTP-01, `/.well-known/acme-challenge/`)과 갱신은 보조 컨테이너(certbot 등)가 하고, 갱신하면 nginx 를 다시 읽힌다(reload)
- 인증서는 90일짜리다. 갱신이 조용히 실패하면 석 달 뒤 사이트가 멈춘다. 남은 날짜를 보는 검사를 함께 둔다
- HTTP 는 HTTPS 로 넘기고(301), HSTS(`Strict-Transport-Security`)를 nginx 가 붙인다. 인증 서버는 하지 않는다(`auth-server/config/security.py`)
- 인증 서버는 `TRUSTED_PROXY_COUNT=1` 그대로다

**앞에 한 단계가 더 생기면(다른 프록시, 클라우드 로드밸런서, Cloudflare) 셋을 함께 바꾼다.** 하나라도 빠지면 오류 없이 조용히 틀린다.

1. nginx 가 앞단을 믿고 진짜 주소를 꺼낸다(`set_real_ip_from <앞단의 주소 대역>`, `real_ip_header X-Forwarded-For`).
   빠뜨리면 요청 수 제한이 모든 사용자를 앞단의 주소 하나로 센다
2. 인증 서버의 `TRUSTED_PROXY_COUNT` 를 2 로 올린다. 빠뜨리면 시도 횟수를 앞단의 주소로 센다
3. `X-Forwarded-Proto` 를 앞단이 보낸 것으로 넘긴다(nginx 가 `$scheme` 으로 덮으면 늘 http 다). 빠뜨리면 인증 서버가 HTTPS 요청을 HTTP 로 본다(`request.is_secure()`)

그리고 서버(VM)는 앞단에서 온 요청만 받게 막는다(보안 그룹이나 방화벽). 앞단을 건너뛰어 바로 오면 1번의 믿음이 깨진다.

## 설계 메모

서버 하나에 속하지 않는 결정만 적는다. 서버별 결정은 각 서버의 설명서에 있다.

**설정 파일을 서버마다 따로 둔다.** 루트 `.env`는 인프라용이고, 서버의 비밀값은
각 서버 폴더의 `.env`에 둔다. 한 서버가 다른 서버의 비밀값을 읽을 수 없게 하기 위해서다.

**DB 인스턴스는 하나, 계정과 스키마는 서버마다 따로 쓴다.** 인증 서버는 `auth` 계정으로
`auth` 스키마만, 게임 서버는 `game` 계정으로 `game` 스키마만, 결제 서버는 `billing` 계정으로 `billing` 스키마만, 게시판 서버는 `board` 계정으로 `board` 스키마만, 알림 서버는 `notification` 계정으로 `notification` 스키마만 쓴다. 다른 서버의 테이블을 직접 읽는 코드는 DB 권한에서 거부된다.
게임 서버의 테스트(`game-server/tests/test_schema_isolation.py`)가 이 경계를 확인한다. 새 서버를 더하면 그 서버의 테스트에도 자기 계정으로 같은 검사를 둔다.
서버 간 데이터 교환은 API로만 한다.

**로그인은 인증 서버만 한다.** 다른 서버는 인증 서버의 공개키로 토큰을 검증만 한다.
인증 서버의 DB를 보지 않고, 요청마다 인증 서버를 부르지도 않는다. 사용자는 토큰의 `sub`(`public_id`)로만 가리킨다.

**`main` 은 보호 규칙으로 지킨다.** 지우기와 강제 푸시를 막고, PR 로만 넣는다(승인은 0). 소유자도 예외가 아니다.
머지하려면 필수 검사 `ci-ok` 가 통과해야 한다. `ci-ok` 는 PR 의 관문(`.github/workflows/ci.yml`)이 마지막에 내는 결과다.
관문은 바뀐 파일을 보고 그 서버의 CI 만 부른다(`.github/scripts/changed-servers.sh`). 부르지 않은 서버는 건너뛴 것이고 통과로 친다.
서버의 CI 를 따로 필수로 걸지 않은 이유: 서버마다 자기 폴더가 바뀔 때만 돈다. 돌지 않은 필수 검사를 GitHub 은 "기다리는 중"으로 두고 머지를 막는다.
`docker/` 아래(DB 초기화 스크립트, 프록시의 설정, crontab), compose 파일, 관문 자신이 바뀌면 모두 돈다. 파이썬 서버들이 함께 쓰는 ruff 규칙(루트의 `ruff.toml`)이 바뀌면 인증, 게임, 알림이 돈다. `main` 에 들어간 뒤에는 서버의 CI 가 예전처럼 제 폴더가 바뀔 때만 스스로 돈다. 위의 배지가 그 결과다.
서버가 하나라도 바뀌면 관문의 `stack` 이 모든 서버의 이미지를 만들어 compose 로 함께 띄우고, 마이그레이션이 성공했는지, 서버끼리 닿는지, 워커가 다시 뜨기를 되풀이하지 않는지, crontab 의 명령이 한 번씩 성공하는지, 비밀이 그것을 쓰는 프로세스에만 가는지, 바깥에 여는 포트가 127.0.0.1 에 묶였는지, 모든 컨테이너의 로그에 상한이 있는지, DB 의 백업이 풀리는지, 프록시가 주소를 나누고 막는지, 모든 응답에 보안 머리말을 붙이는지를 본다(`.github/scripts/stack-smoke.sh`).

**이미지는 서버마다 같은 규칙으로 만든다.** 여러 단계로 빌드해 실행에 필요한 것만 담고, root 가 아닌 사용자(번호로 적는다)로 돌린다.
기본 이미지는 버전을 고정한다. 비밀(`.env`, JWT 키)은 `.dockerignore` 로 막아 이미지에 넣지 않고, 띄울 때 compose 가 넘긴다.
파이썬과 노드는 Debian slim 을 쓴다. 미리 빌드된 패키지(휠)가 대부분 glibc 용이라 alpine 에서는 소스에서 빌드하느라 느리고 잘 깨진다.
결제 서버는 C 라이브러리에 기대지 않는 실행 파일 하나라 alpine 을 쓴다. 상태 확인에 쓰는 `wget` 이 들어 있다.

**바깥에서 들어오는 길은 프록시(nginx) 하나다.** `/api/v1/<서버>/` 앞부분만 보고 그 서버에 보낸다. 서버마다 주소의 앞부분이 이미 나뉘어 있어서 주소를 고쳐 쓰지 않는다.
그 밖의 주소는 모두 404 다. 관리자 화면(`/admin/`, `/static/`), 서버들의 `/health`, 결제 서버끼리만 부르는 `/api/v1/billing/service/` 가 여기에 든다.
막은 주소도 403 이 아니라 404 다. 그런 주소가 있다는 것조차 알리지 않는다. 결제 대행사의 웹훅은 열려 있다.
IP 마다 요청 수를 센다: 인증의 민감한 요청(로그인, 인증 코드, 가입, 비밀번호)은 1분에 10번, 게시판 검색은 1초에 2번, 그 밖은 1초에 20번(몰려도 40번까지), 게임 서버의 SSE 연결은 동시에 10개.
넘으면 429 와 `Retry-After` 다. 인증 서버의 시도 제한(Redis)이 꺼져 있어도 바깥에서 막고, 인증 서버에 제한이 없는 인증 코드 확인과 비밀번호 재설정 확인도 막는다.
요청 식별자(`X-Request-ID`)는 프록시가 정해 서버에 넘긴다. 프록시의 로그도 공통 규격의 JSON 이다([관측 규격](docs/observability.md#프록시의-줄)).
서버의 주소는 요청마다 Docker 의 DNS 에서 찾는다. 서버가 다시 떠서 주소가 바뀌어도 프록시를 다시 띄울 필요가 없다.
이미지는 `nginxinc/nginx-unprivileged` 다. root 가 아닌 사용자로 돈다.

**워커와 주기 명령은 서버와 같은 이미지의 컨테이너로 따로 돈다.** 컨테이너 하나에 프로세스 하나다. 워커가 죽어도 서버는 살아 있고, 따로 다시 뜬다.
계속 도는 것: 인증 서버의 메일 워커(`auth-mail`)와 환영 크레딧 워커(`auth-welcome-credits`), 결제 서버의 정리 작업(`billing-sweeper`).
정한 시각에 도는 것은 [supercronic](https://github.com/aptible/supercronic)(컨테이너용 cron)이 `docker/cron/` 의 crontab 대로 부른다(`auth-cron`, `billing-cron`).
시각은 UTC 다. 보안 이벤트 요약은 매시 5분, 오래된 가입 코드 정리와 만료된 토큰 정리, 결제의 대사는 매일 한국 시각 새벽 4시대에 10분씩 띄워 돈다.
앞의 실행이 끝나지 않았으면 다음 실행을 건너뛴다. supercronic 은 명령이 남기는 줄을 그대로 내보내고, 제 줄은 실패만 남긴다.
서버(VM)의 cron 에 맡기지 않은 이유: PC 와 CI 에서 돌려 볼 수 없고, 설정이 저장소 밖에 생긴다. Docker 소켓으로 다른 컨테이너를 부르는 도구(Ofelia 등)는 그 컨테이너가 호스트의 root 와 같은 권한을 갖게 되어 쓰지 않았다.

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

**인증 서버의 테스트가 `permission denied to create database` 로 실패한다**

`auth` 계정에 테스트용 DB 를 만들 권한이 없다. 루트 `.env` 에 `AUTH_DB_ALLOW_TEST_DB=true` 가 없는 채로 볼륨을 만든 경우다.
볼륨을 지워도 되면 그 줄을 넣고 다시 만든다. 데이터를 남겨야 하면 관리 계정으로 권한만 준다.

```
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "ALTER ROLE auth CREATEDB"'
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
.github/scripts/          관문이 검사할 서버를 고르는 스크립트와 그 테스트, 컨테이너로 띄워 보는 스크립트, 설정 검사(비밀, 열린 포트, 로그 상한)
auth-server/              Django 인증 서버 (독립된 uv 프로젝트)
game-server/              FastAPI 게임 서버 (독립된 uv 프로젝트)
board-server/             NestJS 게시판 서버 (독립된 npm 프로젝트)
billing-server/           Go 결제 서버 (독립된 Go 모듈). 연습용이고 실제 결제가 아니다
notification-server/      FastAPI 알림 서버 (독립된 uv 프로젝트)
docker/postgres/init/     서버별 DB 계정과 스키마를 만드는 초기화 스크립트
docker/nginx/templates/   프록시(nginx)의 설정
docker/cron/              주기 명령의 crontab (인증, 결제)
docker/backup/            DB 의 백업과 복원 확인 스크립트
docs/                     서버들이 함께 지키는 규격 (관측)
docker-compose.yml        PostgreSQL, Redis, DB 의 백업, 모든 서버와 워커, cron, 프록시(프로필 app)
.env.example              인프라 환경 변수 목록
```
