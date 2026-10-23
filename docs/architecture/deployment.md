# 배포 설계

저장소의 서버들을 클라우드의 서버(VM) 한 대에 처음 올리는 일을 적는다. 어디에, 어떻게 올리고, 무엇으로 막고, 무엇을 아직 하지 않는지다.

- 기준: `main` `36f679c` (2026-10-19)
- **첫 배포의 목표는 운영자 혼자 쓰는 서버다**(2026-10-19 결정). 바깥 사람은 들어오지 못하게 막고, 실제 서버에서 띄우고 지키고 되살리는 일을 연습한다. 지인 베타와 정식 공개는 그다음이고 [정식 공개 전에 더 필요한 것](#정식-공개-전에-더-필요한-것)에 있다.
- **VM 은 TRPG, chat, story 세 서비스와 그 화면이 다 된 뒤에 띄운다**(2026-10-20 결정, [화면 명세의 첫 출시의 범위](../product/screens.md#첫-출시의-범위)의 1단계). 그 VM 이 그대로 지인 베타(2단계)의 서버가 된다. 순서서와 도구는 준비되어 있다(#491).
- **그 전에 집 PC 의 VM 에서 순서서를 한 번 따라 해 본다**(2026-10-22 결정, [로컬 VM 리허설](../operations/local-vm-rehearsal.md)). 순서는 로컬 VM 리허설 → 화면(#290) → 클라우드 VM(#491)이다. 리허설은 순서서의 틀린 곳과 아무도 쓰지 않을 때의 메모리(바닥값)를 본다. 사용자가 있을 때의 숫자(연결, 메모리, 디스크가 느는 양)는 클라우드 VM 에서 잰다.
- 로컬에서 바깥에 열 때 지킬 것(열린 포트, 프록시의 머리말, 보안 머리말, 로그 상한, TLS)은 루트 README 의 "외부에 열기 전"이 원본이다. 이 문서는 그것을 어느 서버에서 어떤 값으로 하는지를 적는다.
- 운영 설정은 `docker-compose.staging.yml` 하나다(#451). 무엇을 덮어쓰는지는 그 파일의 머리에 있다.
- 남은 점검 목록은 이슈 #274 다.

## 목차

- [정한 것](#정한-것)
- [한눈에](#한눈에)
- [서버](#서버)
- [혼자 쓰는 동안 막기](#혼자-쓰는-동안-막기)
- [환경 이름](#환경-이름)
- [도메인과 TLS](#도메인과-tls)
- [모델](#모델)
- [올리는 방식](#올리는-방식)
- [비밀과 설정](#비밀과-설정)
- [외부 서비스](#외부-서비스)
- [백업](#백업)
- [그림 저장소](#그림-저장소)
- [디스크](#디스크)
- [지켜보기](#지켜보기)
- [VM 준비 순서](#vm-준비-순서)
- [만드는 순서](#만드는-순서)
- [정식 공개 전에 더 필요한 것](#정식-공개-전에-더-필요한-것)
- [열린 질문](#열린-질문)

## 정한 것

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 목표 | 운영자 혼자 쓰는 서버(2026-11) | 화면(#290)과 실제 본인인증(#336)이 아직 없다. 실제 서버를 다루는 일부터 연습한다 |
| 클라우드 | AWS Lightsail 서울 | 월 고정 요금, 서울 리전, 메일(SES)과 백업 저장소(S3)가 한 계정에 있다. 커지면 EC2 로 옮기기 쉽다 |
| 서버 수 | VM 한 대에 Docker Compose | `services.md` 의 배포 형태 그대로. 쿠버네티스는 쓰지 않는다 |
| 크기 | 8GB 메모리(2 vCPU) | 서버와 워커, PostgreSQL, Redis, nginx 에 로그·메트릭 모으기(1~1.5GB)와 임베딩의 Ollama(1~1.5GB)가 더해진다(추정, [열린 질문](#열린-질문)). 4GB 는 빌드와 함께 돌리기에 빠듯하다 |
| 환경 이름 | `staging` | `production` 은 가짜 본인인증으로 뜨지 않는다([환경 이름](#환경-이름)) |
| 막는 법 | Lightsail 방화벽 + nginx 의 허용 주소 | 인증서를 받는 길과 가동 확인은 열어 두고 나머지는 내 주소만 |
| TLS | nginx 가 직접 끝낸다, Let's Encrypt(HTTP-01), certbot 컨테이너가 갱신 | README "외부에 열기 전"의 기본안 |
| 가동 확인 | `https://<도메인>/healthz`. 프록시 자신만 답한다 | 서버의 준비 상태를 바깥에 이으면 DB 의 상태가 밖에서 보이고, 부를 때마다 DB 를 부른다. 서버의 상태는 안에서 Prometheus 와 경보가 본다 |
| 서술 모델 | Z.ai 의 GLM-4.7-Flash(무료, 이름표 `glm-4-7-flash`)와 집 PC 의 Ollama | 운영자 본인의 시험용이다. 집 PC 는 사설망(Tailscale)으로 부른다([모델](#모델)) |
| 임베딩 | VM 의 Ollama(CPU)가 `bge-m3` 를 돌린다 | 로어 검색의 기준(`LORE_MAX_DISTANCE`)이 이 모델로 잰 값이다. 모델이 같아 다시 잴 필요가 없고, 바깥에 보내는 데이터가 늘지 않는다 |
| 결제 | 가짜 결제 대행사(`PAYMENT_PROVIDER=fake`) | `staging` 에서 허용된다. 누구나 크레딧을 얻으므로 허용 주소가 꼭 있어야 한다. 토스의 웹훅 주소는 열지 않는다 |
| 바깥 백업 | age 로 잠가 S3(서울)에 날마다. 일주일에 한 번 버킷의 것을 받아 실제로 풀어 본다 | 열쇠를 둘(주, 확인)로 잠근다. 주 열쇠는 VM 밖에만, 확인 열쇠는 VM 에 둔다. 버킷의 접근 키는 지우지 못한다([백업](#백업)) |
| 그림 | S3(서울)의 비공개 버킷 하나, 백업과 나눈다. asset-server 가 권한을 보고 nginx 가 내준다. 로컬은 SeaweedFS 로 흉내 낸다(2026-10-20) | 그림은 사용자가 만든 자산이라 VM 과 함께 잃으면 안 된다([그림 저장소](#그림-저장소)) |
| 올리는 법 | 처음은 VM 에서 빌드, 다음은 GHCR 의 이미지 | 처음에는 단계를 줄이고, 버전 추적이 필요해지면 옮긴다 |
| 프런트 | 화면의 디자인은 Stitch, 아이콘 같은 그림은 나노 바나나가 만든다. 백엔드가 거의 다 된 뒤 화면 명세와 API 목록(OpenAPI)을 맡기고, 디자인의 요소만 뽑아 React(Vite, SPA)로 쓴다. 같은 nginx 가 정적 파일로 내준다(2026-10-21). 화면은 프록시의 이미지에 굽는다(`web/Dockerfile`, #290) | 화면 명세(`docs/product/screens.md`)와 `docs/api/` 를 의뢰서로 쓴다. 출처가 하나라 쿠키와 CORS 를 그대로 쓴다 |

## 한눈에

```
  나 (집 PC, 브라우저)                       집 PC 의 Ollama (GPU)
     │ HTTPS 443        SSH 22 (내 주소만)          ▲
     ▼                     ▼                        │ Tailscale(사설망), 11434
  Lightsail 방화벽 ── 80, 443 은 모두에게, 22 는 내 주소만
     │                                              │
  VM (Ubuntu, Docker) ──────────────────────────────┘
     │
  proxy (nginx) ── 80: 인증서의 확인 파일과 HTTPS 로 넘기기
     │             443: TLS 를 끝내고, 허용 주소가 아니면 403. /healthz 는 모두에게
     │
  auth / game / board / billing / notification 서버와 워커들 (포트를 열지 않는다)
     │                    └── ollama (CPU, bge-m3 임베딩. 포트를 열지 않는다)
  db (PostgreSQL), redis (127.0.0.1 에만)
     │
  certbot ── 12시간마다 갱신, 받은 인증서를 프록시가 읽는 곳에 옮긴다
  db-backup ── 날마다 덤프(VM 의 디스크, 14개)
  backup-offsite ── 덤프를 age 로 잠가 S3(서울)로. 일주일에 한 번 받아 풀어 본다
  Alloy, Loki, Prometheus, Grafana (프로필 observability. Grafana 는 127.0.0.1 에만)
```

## 서버

- **Lightsail 서울(ap-northeast-2), Linux 범용 8GB 번들.** 2026-10 기준 월 $44, IPv4 포함, SSD 160GB, 전송량 5TB. 4GB 는 $24 다([요금](https://aws.amazon.com/ko/lightsail/pricing/)). 서울 리전의 값은 콘솔에서 한 번 더 확인한다.
- 운영체제는 Ubuntu LTS. Docker 는 공식 저장소에서 설치한다(Ubuntu 의 `docker.io` 패키지가 아니다).
- **고정 IP** 를 붙인다. 붙어 있는 동안은 따로 요금이 없다. 도메인의 A 레코드가 이 주소를 가리킨다.
- **자동 스냅샷**을 켠다. 디스크 전체를 하루에 한 번 떠 둔다. DB 백업과는 다른 것이다. 스냅샷은 VM 을 통째로 되살리고, DB 백업은 데이터를 다른 곳에 풀게 해 준다.
- 메모리가 모자라 컨테이너가 죽지 않게 스왑을 2GB 둔다. 빌드를 VM 에서 하는 동안 특히 필요하다.

대안과 대가:

| 곳 | 고르지 않은 까닭 |
| --- | --- |
| 네이버 클라우드 | 원화 청구와 세금계산서, 한국어 지원이 장점이다. 요금 구조가 복잡하고 자료가 적다. 사업자를 내고 세금계산서가 필요해지면 다시 본다 |
| Vultr 서울 등 | 싸고 단순하다. 메일과 백업 저장소를 따로 구해야 한다 |
| Oracle 무료 | 2026-06 에 무료 한도가 절반으로 줄었다는 보도가 있고, 한가하면 회수 대상이 되며, 용량이 없어 못 받는 일이 있다. 연습용으로도 서버가 사라지는 일이 잦으면 연습이 안 된다 |

## 혼자 쓰는 동안 막기

바깥 사람이 들어오면 안 되는 까닭이 넷이다. 가짜 본인인증이라 누구나 성인이 된다. 가입하면 환영 크레딧이 나간다. 가짜 결제로 누구나 크레딧을 얻는다. 모델의 API 키로 남이 서술을 부르면 원가가 내 돈으로 나간다.

| 층 | 무엇을 | 왜 이렇게 |
| --- | --- | --- |
| Lightsail 방화벽 | 22(SSH)는 내 주소만. 80, 443 은 모두에게 | 인증서를 받으려면(HTTP-01) Let's Encrypt 가 80 에 닿아야 한다 |
| nginx | 80 은 인증서의 확인 파일(`/.well-known/acme-challenge/`)과 HTTPS 넘기기만 답한다. 443 은 가동 확인(`/healthz`) 말고는 허용 주소(`allow`)가 아니면 403 | 방화벽에서 80, 443 을 내 주소로 막으면 인증서를 받지 못한다. 인증서를 DNS 로 받는 길(DNS-01)은 DNS 의 API 키가 VM 에 있어야 해서 고르지 않았다 |
| SSH | 키로만, 비밀번호와 root 로그인을 끈다 | Lightsail 의 기본값을 확인한다 |

- 허용 주소는 VM 의 `docker/nginx/allowlist/allow.conf` 에 `allow <주소>;` 줄로 적는다(보기: `allow.conf.example`). 이 폴더의 `*.conf` 는 git 에 올리지 않는다.
- 파일을 고치면 1분 안에 nginx 가 다시 읽는다(`docker/nginx/staging/start.sh`). 바로 읽히려면 `docker compose exec proxy nginx -s reload`. 집의 주소가 바뀌면 이 파일과 방화벽의 22 를 고친다.
- **파일이 없거나 줄이 하나도 없으면 아무도 서버에 닿지 못한다.** 닫힌 쪽으로 실패한다.
- 막는 것은 서버에 넘기는 주소다. nginx 가 직접 404 로 답하는 주소(관리자 화면, 서버끼리의 주소, 그 밖의 주소)는 허용 주소 밖에서도 404 다. 허용 주소 밖에서는 API 의 앞부분(`/api/v1/<서버>/`)이 403, 나머지가 404 로 갈린다. API 의 주소는 비밀이 아니라 그대로 둔다.
- 기본 인증(Basic Auth)으로 막지 않는다. `Authorization` 머리말을 쓰는데, 서버들이 이미 그 머리말로 access 토큰을 받는다.
- 막는 것은 nginx 한 곳이다. 서버들의 코드는 바꾸지 않는다. 베타를 열 때 허용 주소에 `allow all;` 을 적거나 막는 줄을 뺀다.

## 환경 이름

`APP_ENVIRONMENT` 는 `staging` 으로 둔다. 서버마다의 `.env` 에 무엇을 적었든 `docker-compose.staging.yml` 이 모든 서버와 워커, 프록시에 같은 값을 준다. 로그의 `environment` 가 `staging` 이 된다(`docs/observability.md`).

- 인증 서버는 `production` 이면 안전한 값이 저절로 켜지고 위험한 값으로는 뜨지 않는다. 그중 하나가 가짜 본인인증(`IDENTITY_PROVIDER=fake`)의 거부다. 실제 업체가 없으니 `production` 으로는 뜨지 못한다.
- `staging` 은 바깥에 연 환경이라 전송의 안전(DEBUG, refresh 쿠키의 Secure, https 인 쿠키의 출처)은 `production` 처럼 검사한다(#466, `auth-server/config/environments.py`). 가짜 본인인증과 터미널 메일은 허용한다.

| 값 | `staging` 에서 | 누가 적나 |
| --- | --- | --- |
| `DEBUG` | `false`. 인증, 게임, 결제, 알림 서버의 모든 프로세스 | `docker-compose.staging.yml` |
| `REFRESH_COOKIE_SECURE` | `true` | `docker-compose.staging.yml`. 끄면 인증 서버가 뜨지 않는다 |
| `REFRESH_COOKIE_ALLOWED_ORIGINS` | `https://<도메인>` | `docker-compose.staging.yml`(루트 `.env` 의 `DOMAIN`) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,auth-server,<도메인>` | `docker-compose.staging.yml`. `auth-server` 는 다른 서버가 공개키를 받을 때의 Host 다 |
| `SMTP_HOST` 등 | 비워 둬도 뜬다 | `auth-server/.env`. 비우면 인증 코드가 컨테이너의 로그에 찍히고, 그 줄이 Loki 에 14일 남는다. 혼자 쓰는 동안은 괜찮지만 SMTP 를 붙이기 전까지 그렇다 |
| 관리자 화면 쿠키의 Secure | 붙지 않는다 | `production` 에서만 붙는다. 관리자 화면은 SSH 터널(`http://localhost`)로 열고, 브라우저는 localhost 를 안전한 곳으로 본다 |
| `PAYMENT_PROVIDER` | `fake` | `billing-server/.env` |

- 결제는 실제 돈을 받지 않는다.

## 도메인과 TLS

- 도메인을 산다. DNS 는 산 곳의 것이나 Lightsail 의 DNS 를 쓴다. **Cloudflare 의 프록시는 켜지 않는다.** 앞단이 하나 생기면 README 의 "앞에 한 단계가 더 생기면" 셋을 함께 바꿔야 한다.
- nginx 가 8443(TLS)과 8080(HTTP)을 듣고 compose 가 `443:8443`, `80:8080` 으로 잇는다(`docker/nginx/staging/default.conf.template`). 이미지(nginx-unprivileged)는 root 가 아니라 1024 아래를 열지 못한다.
- 바깥에 여는 포트는 이 둘뿐이다. `.github/scripts/port_scope.py` 는 `--public` 을 줄 때(staging 의 설정)만 이 둘을 허용한다. 로컬의 설정은 그대로 루프백이다.
- TLS 1.2, 1.3 만 받는다(Mozilla 의 intermediate). OCSP stapling 은 켜지 않는다(Let's Encrypt 가 OCSP 를 끝냈다).
- HSTS 는 `max-age=31536000` 이다. 하위 도메인(`includeSubDomains`)과 preload 는 붙이지 않는다. HTTPS 의 응답에만 붙는다(로컬의 HTTP 에는 없다).

인증서:

| 일 | 어떻게 |
| --- | --- |
| 처음 받기 | `docker compose run --rm -p 80:80 certbot issue`. 프록시를 띄우기 전이라 certbot 이 직접 80 을 듣는다(standalone). 먼저 `issue --dry-run` 으로 시험한다(Let's Encrypt 의 시험 서버라 발급 한도에 세지 않는다) |
| 갱신 | certbot 컨테이너가 12시간마다 `certbot renew` 를 부른다. 30일 남았을 때부터 갱신한다. 확인 파일은 nginx 가 80 에서 내준다(webroot). 처음에 standalone 으로 받았어도 갱신 설정이 webroot 로 바뀐다 |
| nginx 가 읽게 하기 | 받거나 갱신하면 `docker/certbot/deploy-hook.sh` 가 인증서와 키를 `tls` 볼륨에 옮긴다(키는 nginx 의 사용자 101 만 읽는다). 프록시가 그 파일이 바뀐 것을 보고 1분 안에 다시 읽는다 |
| 남은 날짜 | certbot 의 healthcheck 가 10분마다 본다(`docker/certbot/cert_check.py`). 14일보다 적게 남으면, 즉 갱신이 2주 넘게 실패하면 `unhealthy` 다 |

- certbot 에 Docker 소켓을 주지 않는다. 주면 그 컨테이너가 VM 의 root 와 같아진다. 그래서 nginx 에 신호를 보내지 않고 nginx 가 제 쪽에서 파일을 지켜본다.
- 프록시는 `tls` 볼륨만 읽기 전용으로 붙인다. Let's Encrypt 의 계정 키와 지난 인증서(`letsencrypt` 볼륨)는 프록시에 닿지 않는다.
- 인증서를 처음 받기 전에는 프록시가 뜨지 않는다(인증서 파일이 없다). [VM 준비 순서](#vm-준비-순서)대로 인증서를 먼저 받는다.

## 모델

- **서술.** 테이블마다 모델을 고른다(게임 서버의 모델 목록 `ai_models` + 결제 서버의 가격표). 첫 모델은 Z.ai 의 GLM-4.7-Flash(무료)다. 필요한 키는 `ZAI_API_KEY` 하나다. `LLM_MODEL=glm-4-7-flash`, `LLM_FALLBACK_MODELS` 는 비운다(모델을 고르지 않았던 옛 테이블의 기본이다).
- **로컬 모델(집 PC 의 Ollama).** VM 에는 GPU 가 없어 VM 안에서 돌리지 않는다. VM 이 사설망(Tailscale)으로 집 PC 를 부른다. 루트 `.env` 의 `GAME_LLM_BASE_URL=http://<집 PC 의 Tailscale 주소>:11434/v1` 이다. 적지 않으면 게임 서버가 뜨지 않는다(로컬의 기본값 `host.docker.internal` 은 VM 자신이다).
  - 집 PC 의 Ollama 는 사설망 쪽에만 듣게 한다(`OLLAMA_HOST=<Tailscale 주소>:11434`). 공인 IP 로 열지 않는다.
  - VM 에 Tailscale 을 설치하면 컨테이너도 VM 을 거쳐 사설망의 주소에 닿는다.
  - Tailscale 의 접근 규칙(ACL)으로 VM 이 집 PC 의 11434 에만 닿게 좁힌다. VM 을 빼앗겨도 집의 다른 기기에 닿지 않는다.
  - 집 PC 가 꺼져 있으면 로컬 모델만 실패한다. 서술의 실패 정책이 그대로 적용된다.
- **임베딩.** VM 의 `ollama` 컨테이너가 CPU 로 `bge-m3` 를 돌린다. 처음 뜰 때 `ollama-pull` 이 모델을 받아 두고(이미 있으면 받지 않는다), 게임 서버는 그것이 끝나야 뜬다. 한 번 올린 모델은 내리지 않는다(`OLLAMA_KEEP_ALIVE=-1`).
  - `EMBEDDING_BASE_URL=http://ollama:11434/v1` 을 compose 가 적는다. 비우면 `LLM_BASE_URL`(집 PC)로 가 버린다.
  - 메모리의 상한은 2GB 다. 넘으면 이 컨테이너만 죽는다. 임베딩이 실패하면 로어 검색은 키워드로만 돌고 경고 로그를 남긴다. 서술은 멈추지 않는다.
- **모델 목록을 넣는다.** 목록이 비어 있으면 시나리오를 저장하지 못한다. staging 의 DB 를 띄운 뒤 `docker compose exec trpg-server python -m scripts.models sync` 로 모델 목록의 원본 파일을 들여오고 `enable` 로 `glm-4-7-flash` 를 켠다. 쓸 로컬 모델은 그 환경의 파일을 따로 두고 `sync --file` 로 들여온다(운영 문서 [staging VM](../operations/staging-vm.md) 9번).
- **가격표.** 결제 서버가 떠 있으면 "지금 팔고 있는 모델"만 고를 수 있다. staging 의 가격표에 로컬 모델의 이름표가 없으면 그 모델이 목록에 나오지 않는다([열린 질문](#열린-질문)).

## 올리는 방식

**1단계(첫 배포): VM 에서 빌드한다.** VM 에 저장소를 받고, `main` 의 커밋 하나를 꺼내 `docker compose up -d --build` 한다(루트 `.env` 의 `COMPOSE_FILE` 과 `COMPOSE_PROFILES` 가 운영 설정과 프로필을 고른다).

- 단계가 가장 적다. 이미지 저장소도, 저장소 인증도 필요 없다.
- 대가: 서버 일곱과 워커를 빌드하는 동안 VM 의 메모리와 CPU 를 쓴다(그동안 서버가 느려진다). 어느 이미지가 어느 커밋인지는 VM 에서 꺼낸 커밋으로만 안다.
- 되돌리기는 앞 커밋을 꺼내 다시 빌드하는 것이다. 마이그레이션은 되돌리지 않는다(되돌려야 하면 백업에서 푼다).

**2단계: CI 가 이미지를 만들어 GHCR 에 올린다.** `main` 에 머지되면 서버마다 이미지를 만들고 커밋 해시를 이름표로 붙여 올린다. VM 은 이름표를 골라 받기만 한다.

- 버전이 이름표로 남고, 되돌리기가 이름표 바꾸기다. VM 은 빌드하지 않는다.
- 대가: 워크플로가 하나 늘고, VM 이 GHCR 에서 받을 토큰(읽기만)이 필요하다.
- 1단계를 몇 번 해 보고, 빌드가 VM 을 느리게 하거나 되돌릴 일이 생기면 옮긴다.

운영 설정은 지금의 `docker-compose.yml` 에 덮어쓰는 파일(`docker-compose.staging.yml`) 하나다. 바꾸는 것은 프록시의 포트와 TLS, certbot, 허용 주소, 환경 이름, 인증 서버의 도메인과 쿠키, 모델의 주소, 임베딩의 Ollama 다. 로컬의 파일을 고쳐 로컬과 갈라지게 하지 않는다. 망(networks)은 덮어쓰지 않는다(서버마다 메트릭을 붙이는 PR 이 망을 더한다).

CI(`stack`)가 운영 설정도 본다(`.github/scripts/stack-smoke.sh check-staging`). 두 파일을 겹친 설정에서 비밀의 범위, 바깥에 여는 포트, 로그 상한을 보고, staging 의 프록시를 자체 서명 인증서로 하나 더 띄워 HTTPS, 넘기기, 허용 주소, HSTS 를 본다.

## 비밀과 설정

- VM 에 서버마다의 `.env` 와 루트 `.env`, JWT 키(`auth-server/keys/`)를 둔다. 저장소에는 넣지 않는다. 파일은 주인만 읽게(600) 한다.
- 루트 `.env` 에 staging 의 값을 더 적는다(`.env.example` 의 "staging" 절): `COMPOSE_FILE`, `COMPOSE_PROFILES`, `DOMAIN`, `ACME_EMAIL`, `GAME_LLM_BASE_URL`, `GRAFANA_ADMIN_PASSWORD`, `OTEL_EXPORTER_OTLP_ENDPOINT`, 바깥 백업의 `BACKUP_S3_BUCKET`, `BACKUP_AWS_ACCESS_KEY_ID`, `BACKUP_AWS_SECRET_ACCESS_KEY`, `BACKUP_AGE_RECIPIENTS`.
- 비밀번호 관리자에 둘 것: 각 `.env`, JWT 키, 바깥 백업의 주 열쇠와 확인 열쇠, S3 의 접근 키.
- **로컬의 값을 그대로 옮기지 않는다.** DB 비밀번호, 서버끼리의 서명 비밀, JWT 키를 VM 에서 새로 만든다. 로컬의 값은 이 PC 의 여러 곳(작업 폴더 넷)에 퍼져 있다.
- 서버끼리 같아야 하는 비밀은 짝을 맞춘다. `tools/fill_env.py` 가 맞추고 예시에서 주석으로 막힌 짝의 줄도 켠다. 짝의 표는 그 도구의 `SECRETS` 하나다. staging 에서는 `tools/staging_env.py` 가 그 도구를 부른 뒤, 한 파일만 아는 비밀의 줄(`SIGNAL_SECRET` 등)도 켠다.

| 이쪽 | 저쪽(같은 값) |
| --- | --- |
| `auth-server/.env` 의 `BILLING_SECRET` | `billing-server/.env` 의 `AUTH_SERVER_SECRET` |
| `trpg-server/.env` 의 `BILLING_SECRET` | `billing-server/.env` 의 `GAME_SERVER_SECRET` |
| `trpg-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `GAME_SERVER_SECRET` |
| `billing-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `BILLING_SERVER_SECRET` |
| `board-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `BOARD_SERVER_SECRET` |
| `asset-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `ASSET_SERVER_SECRET` |
| `chat-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `CHAT_SERVER_SECRET` |

- 비밀의 원본은 비밀번호 관리자 하나에 둔다. VM 이 사라지면 거기서 다시 만든다. `.env` 를 백업 파일과 같은 곳에 두지 않는다(README "백업과 복원").
- 어느 프로세스가 어느 비밀을 받는지는 지금처럼 `secret_scope.py` 의 표가 지킨다. 운영 설정을 겹친 뒤에도 CI 가 같은 표로 본다.

## 외부 서비스

| 것 | 혼자 쓰는 동안 | 공개 전에 |
| --- | --- | --- |
| AI 모델 | Z.ai(GLM-4.7-Flash, 무료)와 집 PC 의 Ollama([모델](#모델)). 다른 회사의 키를 붙이면 각 콘솔에서 월 사용 한도를 낮게 걸어 둔다 | 같다 |
| 메일 | 비워 두거나 Gmail SMTP 와 앱 비밀번호(이미 쓰는 것) | 하루 발송 한도가 있어 SES 로 바꾼다. SES 는 도메인 인증과 샌드박스를 나오는 신청이 필요하다 |
| 본인인증 | 가짜 업체(`fake`) | 실제 업체와 계약(#336). 보통 사업자등록이 먼저다 |
| 백업 저장소 | S3(서울), 이것만 쓰는 IAM 사용자 | 같다 |
| 그림 저장소 | S3(서울), 그림 버킷만 쓰는 IAM 사용자. asset-server 를 만들 때 만든다 | 같다 |
| 결제 | 가짜 결제 대행사(`fake`) | 사업자등록과 전자결제 계약. 토스 테스트 모드를 쓰면 웹훅 주소(`POST /api/v1/billing/webhooks/toss`)만 허용 주소 밖에 연다(서버가 결과를 토스에 다시 물어 믿는다) |
| 사설망 | Tailscale(VM ↔ 집 PC) | 집 PC 를 쓰지 않으면 뺀다 |

## 백업

- 지금의 `db-backup` 이 날마다 DB 를 한 파일로 뜨고 14개를 남긴다(README "백업과 복원"). VM 의 디스크다.
- **바깥에 한 벌 더 둔다(`backup-offsite`).** 같은 디스크에만 있으면 디스크가 망가질 때 함께 사라진다. 한 시간마다 로컬의 덤프 가운데 버킷에 없는 것을 암호화해 S3(서울)에 올린다. 늦어도 덤프를 뜬 지 한 시간 안에 올라간다.
- **일주일에 한 번 실제로 풀어 본다.** 버킷의 가장 최근 것을 받아 확인 열쇠로 풀고, 올릴 때 적어 둔 원본의 SHA-256 과 맞추고, 같은 DB 서버의 빈 DB 에 풀어 서버마다의 스키마가 다 들어 있는지 본다. 다 보면 그 DB 와 푼 파일을 지운다(`docker/backup-offsite/offsite.sh verify`).
  - 줄 수는 맞춰 보지 않는다. 지금의 DB 는 덤프를 뜬 뒤에도 바뀐다. 줄 수까지 맞추는 것은 CI 의 `db-backup check` 가 PR 마다 한다.
  - 실패하면 컨테이너가 곧바로 `unhealthy` 가 되고, 한 시간마다 다시 풀어 본다. 26시간 넘게 올리지 못해도 `unhealthy` 다.

**암호화(age).** 덤프마다 받는 쪽 열쇠 둘로 잠근다. 어느 열쇠로도 풀린다.

| 열쇠 | 비밀키를 두는 곳 | 쓰는 때 |
| --- | --- | --- |
| 주 열쇠 | VM 에 두지 않는다. 비밀번호 관리자와 오프라인 사본(USB 등) 두 곳 | 손으로 되살릴 때. VM 을 잃어도 이것으로 푼다 |
| 확인 열쇠 | VM 의 `backup-keys/check.key`(600, git 에 올리지 않는다). 비밀번호 관리자에도 한 벌 | 주마다 풀어 보는 데 |

- 두 공개키를 루트 `.env` 의 `BACKUP_AGE_RECIPIENTS` 에 적는다. 하나만 적으면 올리지 않는다. 확인 열쇠의 공개키가 그 안에 없으면 풀어 보기가 실패한다.
- **대가: VM 을 빼앗기면 확인 열쇠로 버킷의 지난 백업도 풀린다.** 그때는 지금의 DB 와 `.env` 도 이미 넘어간 뒤라, 더 새는 것은 지난 며칠의 지운 데이터다. 주마다 저절로 풀어 보는 것을 그것보다 앞에 두었다(2026-10-19 결정). 암호화가 막는 것은 버킷 쪽에서 새는 일(접근 키가 새거나 버킷의 설정을 잘못 여는 것)이다.
- 열쇠를 잃으면 그 열쇠로 잠근 백업은 영영 풀지 못한다. 그래서 주 열쇠는 두 곳에 둔다. 처음 한 번은 주 열쇠로도 풀어 본다([VM 준비 순서](#vm-준비-순서)).
- 열쇠를 바꿀 때: 새 열쇠를 만들어 `BACKUP_AGE_RECIPIENTS` 를 바꾼다. 이미 올린 것은 옛 열쇠로만 풀리므로, 옛 비밀키는 그 백업이 버킷에서 지워질 때(35일)까지 둔다.

**버킷(S3, Lightsail 의 버킷이 아니다).** 처음에는 Lightsail 의 버킷을 쓰려 했다. Lightsail 버킷의 접근 키는 버킷에 대한 모든 권한(읽기, 쓰기, 지우기)을 주고 좁힐 수 없다. 지우지 못하는 키가 필요해서 같은 계정의 S3 를 쓴다. 덤프 몇 MB 라 요금은 거의 없다.

- 버킷: 서울(`ap-northeast-2`), 공개 접근 차단을 켠다, **버전 관리를 켠다**(덮어써도 옛 판이 남는다).
- 수명 주기: 지금의 판은 35일 뒤에 지우고, 지난 판은 그 뒤 30일에 지운다. 지우는 것은 S3 가 하고 VM 의 키는 하지 못한다.
- 접근 키: 이것만 쓰는 IAM 사용자를 만든다. 권한은 `docker/backup-offsite/iam-policy.json`(올리기, 받기, 목록. `trpg-` 로 시작하는 이름만. `BUCKET_NAME` 을 버킷의 이름으로 바꾼다). 지우기(`DeleteObject`, `DeleteObjectVersion`)와 버킷의 설정을 바꾸는 권한이 없다. VM 을 빼앗겨도 버킷의 백업을 지우지 못하고, 덮어써도 옛 판이 남는다.
- 키는 루트 `.env` 의 `BACKUP_AWS_ACCESS_KEY_ID`, `BACKUP_AWS_SECRET_ACCESS_KEY` 다. 버킷의 이름은 `BACKUP_S3_BUCKET`.

**손으로 되살리기(VM 을 잃었을 때).** 새 VM 이나 PC 에서 버킷의 것을 받아 주 열쇠로 풀고 README 의 복원 순서대로 푼다.

```
aws s3 cp s3://<버킷>/trpg-<시각>.dump.age .
age -d -i master.key -o trpg-<시각>.dump trpg-<시각>.dump.age
```

## 그림 저장소

chat 과 story 의 그림(배경, 캐릭터, 일러스트)을 둔다(#540, 2026-10-20 결정). 그림을 올리고 누가 볼 수 있는지 정하는 것은 asset-server 이고, 아직 없다. 지금 있는 것은 로컬의 흉내(`object-store`)와 CI 의 확인이다.

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 저장소 | staging 은 S3(서울). 로컬과 CI 는 SeaweedFS | 로컬에서도 같은 S3 API 로 쓰고, staging 에서 갈아 끼우는 것은 주소와 키뿐이다 |
| 로컬의 흉내 | SeaweedFS(`chrislusf/seaweedfs`)를 한 프로세스(`weed mini`)로 | MinIO 의 무료판은 2025년 10월부터 이미지를 내지 않고, 2026년 4월에 저장소가 보관되었다(보안 패치가 없다). SeaweedFS 는 Apache-2.0 이고 꾸준히 관리된다. 디스크에 남아 껐다 켜도 그림이 그대로다. 바깥 백업의 CI 가 쓰는 moto 는 메모리에만 둔다 |
| 버킷 | 그림 버킷 하나(비공개). 백업의 버킷과 나눈다 | 열쇠의 권한이 정반대다. 백업의 키는 지우지 못하고, 그림의 키는 지워야 한다. 보관 규칙(버전, 수명)도 다르다. 모든 그림이 서버를 거쳐 나가므로 공개 버킷이 필요 없다 |
| 내주는 길 | asset-server 가 권한(소유자, 공개 범위, 등급)을 보고 `X-Accel-Redirect` 로 nginx 에 넘긴다. nginx 가 S3 에서 받아 캐시하고 내준다 | 비공개 캐릭터의 그림은 주소를 알아도 남이 받지 못한다. 성인 등급도 같은 자리에서 막는다. S3 의 열쇠는 서버에만 있다. 캐시를 그림의 id 로 찾으므로 서명이 바뀌어도 캐시가 맞는다 |
| 서명 | 로컬의 흉내도 서명한 요청만 받는다(익명은 403). 없는 버킷에 올리면 만들지 않고 404 다 | 서명하는 코드와 버킷의 이름이 로컬에서도 진짜 S3 와 같은 길을 거친다 |
| nginx 가 받는 법(#566) | asset-server 가 60초 산 서명 주소를 `X-Image-Source` 에 실어 넘기고, nginx 의 내부 위치(`/_images/{id}`)가 그 주소로 받는다. 저장소의 주소가 아니면 받지 않는다 | 키가 asset-server 에만 있다. 표준 nginx 로 되고, nginx 에 서명 모듈이나 서명 프록시 컨테이너가 필요 없다. 약속은 [asset-server 의 그림](asset-server.md#그림) |
| 캐시(#566) | nginx 의 디스크 캐시. 그림의 id 가 키, 1GB, 7일 동안 안 보면 지운다. 컨테이너 안에 둔다(다시 만들면 비고, 다시 받는다) | 그림은 바뀌지 않아 틀어질 일이 없다. S3 의 요청과 대역이 준다 |
| 브라우저(#566) | `private, max-age=3600` | 비공개로 돌린 그림이 남의 브라우저에 한 시간 넘게 남지 않는다. 같은 화면을 다시 그릴 때는 묻지 않는다 |

고르지 않은 것:

| 안 | 고르지 않은 까닭 |
| --- | --- |
| 서명한 주소(presigned URL)를 브라우저에 주고 S3 에서 바로 받게 한다 | 가장 흔한 방식이지만, 주소가 살아 있는 동안은 남에게 넘겨도 열린다. 주소가 매번 달라 브라우저의 캐시가 잘 맞지 않는다 |
| 공개 그림만 nginx 가 바로, 비공개는 서명한 주소 | 길이 둘이 되고, 비공개 쪽은 위의 약점을 그대로 가진다 |
| 로컬은 디스크, staging 은 S3(저장 코드를 둘로) | 컨테이너가 하나 준다. 내주는 길과 서명이 로컬과 staging 에서 달라져 S3 쪽의 버그를 VM 에서야 본다 |
| 백업의 버킷에 접두사로 함께 | 권한이 섞인다. 그림의 키로 백업이 보일 수 있다 |

- **로컬.** `docker compose up -d` 가 DB, Redis 와 함께 띄운다. S3 는 `127.0.0.1:8333`(`IMAGE_STORE_PORT`)이다. 비밀 키는 루트 `.env` 의 `IMAGE_STORE_SECRET_ACCESS_KEY` 이고 `tools/fill_env.py` 가 채운다. 접근 키의 이름은 `ai-trpg-local`, 버킷은 `ai-trpg-images` 다. 그림은 볼륨 `objectdata` 에 남는다.
- **CI.** stack 이 서명해 올리고 받고 지워 보고, 서명 없는 요청과 틀린 키와 없는 버킷을 막는지 본다(`check_object_store`). 서명한 주소로 받기와 올리기는 SeaweedFS 4.48 에서 손으로 확인했다(200, 바꾼 주소는 403). CI 에서는 asset-server 를 만들 때 그 서버의 코드로 본다.
- **staging.** `object-store` 를 띄우지 않는다. 그림 버킷(서울, 공개 접근 차단)과 그 버킷만 쓰는 IAM 사용자(`docker/object-store/iam-policy.json`: 올리기, 받기, 지우기)를 만들고, 그 키를 루트 `.env` 의 `IMAGE_STORE_ACCESS_KEY_ID`, `IMAGE_STORE_SECRET_ACCESS_KEY` 에 사람이 적는다([staging VM 준비](../operations/staging-vm.md)의 1번과 6번). `tools/staging_env.py` 는 버킷의 이름(`--image-bucket`)을 적고 두 키를 비워 둔다. 비어 있으면 compose 가 뜨기를 거부한다. 백업과 같은 버킷을 주면 그 도구가 거절한다.
- 아직 정하지 않은 것은 [열린 질문](#열린-질문)에 있다.

## 디스크

크게 자라는 데이터를 기본 디스크와 나눈다(#539, 2026-10-21 결정). staging 에서만이다. 로컬과 CI 는 Docker 의 볼륨 그대로다.

| 디스크 | 크기(시작값) | 두는 것 | 까닭 |
| --- | --- | --- | --- |
| 기본(system) | 인스턴스의 것 | OS, Docker 의 이미지와 컨테이너, 백업의 덤프, Ollama 의 모델, 인증서 | 백업의 덤프가 DB 와 다른 디스크에 있어 DB 디스크를 잃어도 남는다 |
| DB(`/mnt/db`) | 16GB | PostgreSQL | 관측 데이터가 폭주해도 DB 가 쓰기를 멈추지 않는다. 크기를 따로 재고 따로 키운다 |
| 관측(`/mnt/observability`) | 32GB | Loki, Prometheus(8GB 상한), Alertmanager, Tempo, Grafana, Alloy | 가장 빨리, 예측하기 어렵게 자란다. 잃어도 서비스는 그대로다 |

- **붙이는 법.** Lightsail 의 블록 스토리지 둘을 ext4 로 포맷해 이름표(LABEL)로 마운트한다(`nofail`). Docker 는 두 디스크가 마운트된 뒤에 뜬다(`After=`). `docker-compose.staging.yml` 이 로컬의 볼륨 자리에 그 디스크의 폴더를 붙인다. 폴더가 없으면 컨테이너가 뜨지 않는다(`create_host_path: false`). 마운트를 빠뜨렸을 때 기본 디스크에 몰래 쓰지 않게 한다.
- **폴더.** `docker/disks/prepare-disks.sh` 가 컨테이너마다 그 사용자(uid)의 것으로 만든다. 디스크가 마운트되지 않았으면 만들지 않는다. CI(stack)가 그 표의 uid 와 컨테이너가 실제로 도는 uid 를 견주고, 임시 디스크로 스크립트를 돌려 본다.
- **재기와 경보.** Alloy 안의 node_exporter 가 디스크마다(system, db, observability) 잰다. node_exporter 의 경보 묶음을 따라 남은 비율(15%, 5%)과 "지금 속도면 곧 찬다"(24시간, 4시간)를 함께 본다. 화면은 대시보드 `disks` 다([관측 규격의 디스크](../observability.md#붙인-것-디스크)).
- **크기를 정하는 법.** 띄운 뒤 일주일 동안 대시보드 `disks` 의 "하루에 느는 양"을 보고 정한다. 볼륨마다의 내역은 손으로 한 번 본다(`du`, [staging VM 준비](../operations/staging-vm.md)의 11번). 붙인 채로는 키우지 못하고 스냅샷에서 큰 디스크를 만들어 바꾼다.

고르지 않은 것:

| 안 | 고르지 않은 까닭 |
| --- | --- |
| 관측 데이터만 나눈다(디스크 하나) | DB 의 크기를 따로 재고 키울 수 없다 |
| 데이터를 모두 한 디스크에 | OS 는 지키지만 로그가 폭주하면 같은 디스크의 DB 가 멈춘다 |
| Docker 의 데이터 폴더(`data-root`)를 통째로 옮긴다 | 설정 하나로 되지만 나누는 것이 없다 |
| 볼륨마다 크기를 지표로(du 를 도는 cron 컨테이너) | 정석이 아니다. 훑을 때마다 디스크를 읽고, DB 의 데이터까지 읽을 수 있는 컨테이너가 하나 는다. 디스크를 나누면 디스크의 지표가 곧 저장소의 크기다 |

## 지켜보기

혼자 쓰는 동안은 가볍게 간다. 로그를 모으는 것(Alloy, Loki, Grafana)과 메트릭의 저장소(Prometheus)는 compose 의 프로필 `observability` 로 붙였다(#25, [README 의 로그와 메트릭 모으기](../../README.md#로그와-메트릭-모으기)). `staging` 에서 켠다(`COMPOSE_PROFILES=app,observability`). Grafana 는 VM 의 `127.0.0.1:3000` 에만 열고 사설망(Tailscale)으로 넘겨 연다(`tailscale serve`, #539). 인터넷에는 열지 않는다. 서버의 메트릭은 서버마다 붙이는 중이다.
수집기, 보관 기간, Grafana 를 여는 곳은 [관측 규격](../observability.md#수집기grafana-alloy를-붙일-자리)에 정했다.
같은 VM 에 올리므로 메모리를 다시 잰다(아래 [열린 질문](#열린-질문)). 문제가 생기면 로그와 메트릭을 S3 에 따로 두고 VM 을 나눈다.

- **가동 확인.** 바깥의 무료 감시(UptimeRobot 등)가 몇 분마다 `https://<도메인>/healthz` 를 부르고, 죽으면 메일을 보낸다. 프록시 자신만 답한다(`{"status":"ok"}`). VM, nginx, TLS 가 살아 있는지를 본다. 감시가 인증서의 만료도 보면 켠다.
- **인증서의 남은 날짜.** certbot 의 `healthy` 다([도메인과 TLS](#도메인과-tls)). 지금은 `docker compose ps` 로 본다. 컨테이너의 상태를 경보로 잇는 일은 #25 의 경보에서 한다.
- **디스크.** 디스크마다 남은 비율과 "곧 찬다"를 경보로 본다(위의 [디스크](#디스크)). 경보는 다른 경보와 같은 길(Alertmanager)로 온다.
- **바깥 백업.** `backup-offsite` 의 `healthy` 다. 26시간 넘게 올리지 못했거나 주마다 풀어 보기가 실패하면 `unhealthy` 다([백업](#백업)).
- **컨테이너의 상태**(`docker compose ps` 의 `healthy`).
- 장애 판정은 이 수치와 조건이 한다. 관리 서버와 요약은 나중이다(`docs/observability.md`).

## VM 준비 순서

처음 한 번 하는 일이다. 순서마다의 실제 명령은 [staging VM 준비](../operations/staging-vm.md)에 있다. 여기에는 무엇을 하는지만 둔다.

1. Lightsail 에 인스턴스를 만든다(서울, Ubuntu, 8GB). 고정 IP 를 붙이고, 방화벽에서 22 를 내 주소로 좁히고 80, 443 을 연다. 자동 스냅샷을 켠다. 데이터 디스크 둘(DB 16GB, 관측 32GB)을 만들어 붙이고 그 자동 스냅샷도 켠다([디스크](#디스크)).
2. SSH 를 키로만 받게 한다. 패키지를 올리고 보안 업데이트를 저절로 받게 한다(unattended-upgrades).
3. 스왑 2GB 를 만든다.
4. Docker 와 compose 를 공식 저장소에서 설치한다. `/etc/docker/daemon.json` 에 로그 상한을 적는다(README "외부에 열기 전"). 데이터 디스크 둘을 포맷해 마운트하고, Docker 가 그 뒤에 뜨게 한다.
5. Tailscale 을 VM 과 집 PC 에 설치하고 같은 사설망에 넣는다. 접근 규칙(ACL)으로 VM 이 집 PC 의 11434 에만 닿게 한다. 집 PC 의 Ollama 를 사설망 주소에만 듣게 한다. Grafana 를 사설망에 연다(`tailscale serve`).
6. 도메인을 사서 A 레코드를 고정 IP 로 가리킨다.
7. 저장소를 받고, 데이터 디스크에 컨테이너의 폴더를 만들고(`docker/disks/prepare-disks.sh`), 비밀과 `.env` 를 새로 만든다. `tools/staging_env.py` 가 여덟을 한 번에 만든다. 비밀과 짝은 `tools/fill_env.py` 가 채우고, 그 위에 staging 의 값을 적는다([비밀과 설정](#비밀과-설정)).
8. 허용 주소를 적는다: `cp docker/nginx/allowlist/allow.conf.example docker/nginx/allowlist/allow.conf` 그다음 내 공인 IP 를 `allow` 줄로.
9. 바깥 백업을 준비한다([백업](#백업)).
   - S3 에 버킷을 만들고(서울, 공개 접근 차단, 버전 관리, 수명 주기), IAM 사용자에 `docker/backup-offsite/iam-policy.json` 의 권한을 주고 접근 키를 만든다.
   - 주 열쇠는 VM 밖(집 PC)에서 만든다: `age-keygen -o master.key`(Windows 는 `winget install FiloSottile.age`). 비밀번호 관리자와 오프라인 사본에 둔다.
   - 확인 열쇠는 VM 에서 만든다: `sudo apt install age` 그다음 `mkdir -m 700 backup-keys && age-keygen -o backup-keys/check.key && chmod 600 backup-keys/check.key`. 비밀번호 관리자에도 둔다.
   - 두 공개키(`age1...`)를 빈칸으로 이어 루트 `.env` 의 `BACKUP_AGE_RECIPIENTS` 에 적는다.
   - 그림 버킷도 따로 만든다(공개 접근 차단, 버전 관리 끔). 그 버킷만 쓰는 IAM 사용자에 `docker/object-store/iam-policy.json` 의 권한을 준다([그림 저장소](#그림-저장소)).
10. 인증서를 처음 받는다: `docker compose run --rm -p 80:80 certbot issue --dry-run` 이 통과하면 `docker compose run --rm -p 80:80 certbot issue`.
11. 띄운다: `docker compose up -d --build`. 처음에는 `ollama-pull` 이 `bge-m3`(1GB 남짓)를 받느라 게임 서버가 늦게 뜬다.
12. 모델 목록을 넣는다([모델](#모델)). 결제 서버의 가격표에 쓸 모델이 있는지 본다.
13. 확인: HTTPS 로 닿는지, 내 주소가 아니면 403 인지(휴대폰의 데이터망으로), `/healthz` 가 어디서나 답하는지, 서버들과 certbot, `backup-offsite` 가 `healthy` 인지, 가동 확인이 메일을 보내는지. `docker stats` 로 메모리를 재서 [열린 질문](#열린-질문)에 적는다.
14. 주 열쇠로 한 번 풀어 본다. 집 PC 에서 버킷의 가장 최근 것을 받아 `age -d -i master.key` 로 풀리는지 본다([백업](#백업)의 "손으로 되살리기"). 주마다 저절로 하는 것은 확인 열쇠뿐이다.
15. 운영자 계정을 만들고 인증 서버 관리자 화면에서 `operators` 그룹에 넣는다(SSH 터널로 연다).

## 만드는 순서

PR 하나에 한 가지다.

1. **이 문서.** (#449)
2. **운영 설정과 TLS.** (#451) `docker-compose.staging.yml`(프록시의 80/443, certbot, 허용 주소, 환경 이름, 인증 서버의 도메인과 쿠키, 모델의 주소, 임베딩의 Ollama), nginx 의 TLS 와 허용 주소와 HSTS, `port_scope.py --public`, 가동 확인 주소, CI 의 `check-staging`.
3. **바깥 백업.** `backup-offsite`(age 로 잠가 S3 에 올리기, 주마다 풀어 보기), 버킷과 접근 키의 권한, 되살리는 순서, CI 의 `check-staging` 에서 S3 흉내(moto)로 보기.
4. **VM 준비.** 위 순서의 명령([staging VM 준비](../operations/staging-vm.md)), staging 의 `.env` 여섯을 만드는 도구(`tools/staging_env.py`, 비밀은 `tools/fill_env.py` 에 맡긴다), CI 가 그 도구로 만든 설정을 읽어 보기.
5. (나중) **GHCR 로 올리기.**

## 정식 공개 전에 더 필요한 것

혼자 쓰는 서버에서 베타나 공개로 갈 때 할 일이다. 자세한 점검은 #274 에 있다.

지인 베타(2단계)에서는 이렇게 한다(2026-10-20):

- 초대한 지인과 방송인만 쓴다. 시청자는 방송으로 보기만 한다. 허용 주소에 그 사람들의 주소를 더한다. 주소가 자주 바뀌어 번거로워지면 초대 코드로 바꾼다.
- 미성년자가 없다. 본인인증은 가짜 업체 그대로 둔다.
- 베이직(집 PC 의 로컬 AI) 모델을 연다. 하는 동안 집 PC 가 켜져 있어야 한다. 공개 베타에서는 모델 목록에서 끄고 가격표에서 내린다.
- 결제는 테스트 모드다.

공개 베타 전에:

- 화면(#290). 디자인은 Stitch, 그림은 나노 바나나로 만든다. 화면이 사용자 글, 채팅, AI 서술을 HTML 로 실행하지 않는다(#274).
- 실제 본인인증(#336)과 `APP_ENVIRONMENT=production`. 그 전에 지인 베타를 연다면 성인 콘텐츠와 환영 크레딧을 막는 방법을 정한다.
- 가입 때의 약관과 개인정보 동의(#450). 개인정보 처리방침과 이용약관(운영자가 기록을 볼 수 있다는 것, `docs/architecture/operators.md` 의 "사용자에게 알릴 것").
- 메일을 SES 로.
- 사업자등록, 실제 결제, 청소년 보호와 콘텐츠 관련 규정의 확인(법률 검토가 아니다).
- 허용 주소를 뺀다. 그때부터 요청 수 제한과 시도 제한이 실제 방어선이 된다.

## 열린 질문

- 실제 메모리 사용량. 처음 띄운 뒤 `docker stats` 로 잰다. 세 서비스를 다 만든 뒤에 띄우므로 chat-server 와 asset-server 가 더해진다. 4GB 로 줄일 수 있는지도 본다.
  - 로컬 VM 의 바닥값(2026-10-22, 2코어 8GB, 아무도 쓰지 않을 때): 2.3Gi 를 쓰고 5.4Gi 가 남는다. 관측(Grafana 451MiB, Alloy 362MiB, Tempo 260MiB, Loki 179MiB, Prometheus 154MiB)이 서버 일곱(하나에 90~120MiB)보다 크다. 임베딩의 Ollama 는 173MiB 다. DB 의 연결은 17. 기본 디스크는 이미지와 빌드 캐시로 21GB 를 쓴다([로컬 VM 리허설의 결과](../operations/local-vm-rehearsal.md#결과-2026-10-22)). 클라우드 VM 의 값이 나오면 바꾼다.
- staging 의 가격표에 시험용 모델(GLM-4.7-Flash, 집 PC 의 Ollama)의 이름표를 넣을지와 그 값. 결제 서버가 떠 있으면 가격표에 있는 모델만 고를 수 있다. 무료 모델은 가격표에 올리지 않기로 했으므로(게임 서버 README), 지금 그대로는 staging 에서 서술 모델로 고를 수 없다.
- 모델 회사마다의 월 사용 한도를 어디에 기록해 둘지.
- 그림 저장소(#540): 올리는 크기의 상한, 이미지 디코딩의 격리. asset-server 를 만들 때 정한다([그림 저장소](#그림-저장소)). nginx 가 받는 법과 캐시는 정했다(#566).
