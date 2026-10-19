# 배포 설계

저장소의 서버들을 클라우드의 서버(VM) 한 대에 처음 올리는 일을 적는다. 어디에, 어떻게 올리고, 무엇으로 막고, 무엇을 아직 하지 않는지다.

- 기준: `main` `67175b8` (2026-10-19)
- **첫 배포의 목표는 운영자 혼자 쓰는 서버다**(2026-10-19 결정). 바깥 사람은 들어오지 못하게 막고, 실제 서버에서 띄우고 지키고 되살리는 일을 연습한다. 지인 베타와 정식 공개는 그다음이고 [정식 공개 전에 더 필요한 것](#정식-공개-전에-더-필요한-것)에 있다.
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
- [지켜보기](#지켜보기)
- [VM 준비 순서](#vm-준비-순서)
- [만드는 순서](#만드는-순서)
- [정식 공개 전에 더 필요한 것](#정식-공개-전에-더-필요한-것)
- [열린 질문](#열린-질문)

## 정한 것

| 항목 | 정한 것 | 까닭 |
| --- | --- | --- |
| 목표 | 운영자 혼자 쓰는 서버(2026-11) | 화면(#290)과 실제 본인인증(#336)이 아직 없다. 실제 서버를 다루는 일부터 연습한다 |
| 클라우드 | AWS Lightsail 서울 | 월 고정 요금, 서울 리전, 메일(SES)과 백업 저장소가 한 계정에 있다. 커지면 EC2 로 옮기기 쉽다 |
| 서버 수 | VM 한 대에 Docker Compose | `services.md` 의 배포 형태 그대로. 쿠버네티스는 쓰지 않는다 |
| 크기 | 8GB 메모리(2 vCPU) | 서버와 워커, PostgreSQL, Redis, nginx 에 로그·메트릭 모으기(1~1.5GB)와 임베딩의 Ollama(1~1.5GB)가 더해진다(추정, [열린 질문](#열린-질문)). 4GB 는 빌드와 함께 돌리기에 빠듯하다 |
| 환경 이름 | `staging` | `production` 은 가짜 본인인증으로 뜨지 않는다([환경 이름](#환경-이름)) |
| 막는 법 | Lightsail 방화벽 + nginx 의 허용 주소 | 인증서를 받는 길과 가동 확인은 열어 두고 나머지는 내 주소만 |
| TLS | nginx 가 직접 끝낸다, Let's Encrypt(HTTP-01), certbot 컨테이너가 갱신 | README "외부에 열기 전"의 기본안 |
| 가동 확인 | `https://<도메인>/healthz`. 프록시 자신만 답한다 | 서버의 준비 상태를 바깥에 이으면 DB 의 상태가 밖에서 보이고, 부를 때마다 DB 를 부른다. 서버의 상태는 안에서 Prometheus 와 경보가 본다 |
| 서술 모델 | Z.ai 의 GLM-4.7-Flash(무료, 이름표 `glm-4-7-flash`)와 집 PC 의 Ollama | 운영자 본인의 시험용이다. 집 PC 는 사설망(Tailscale)으로 부른다([모델](#모델)) |
| 임베딩 | VM 의 Ollama(CPU)가 `bge-m3` 를 돌린다 | 로어 검색의 기준(`LORE_MAX_DISTANCE`)이 이 모델로 잰 값이다. 모델이 같아 다시 잴 필요가 없고, 바깥에 보내는 데이터가 늘지 않는다 |
| 결제 | 가짜 결제 대행사(`PAYMENT_PROVIDER=fake`) | `staging` 에서 허용된다. 누구나 크레딧을 얻으므로 허용 주소가 꼭 있어야 한다. 토스의 웹훅 주소는 열지 않는다 |
| 올리는 법 | 처음은 VM 에서 빌드, 다음은 GHCR 의 이미지 | 처음에는 단계를 줄이고, 버전 추적이 필요해지면 옮긴다 |
| 프런트 | 화면의 디자인은 Stitch, 아이콘 같은 그림은 나노 바나나가 만든다 | 화면 명세(`docs/product/screens.md`)를 의뢰서로 쓴다. 코드로 옮기는 것은 [열린 질문](#열린-질문) |

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
  db-backup ── 날마다 덤프 → 암호화해 Lightsail 버킷으로(다음 PR)
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
- **모델 목록을 넣는다.** 목록이 비어 있으면 시나리오를 저장하지 못한다. staging 의 DB 를 띄운 뒤 `docker compose exec game-server python -m scripts.models add ...` 로 `glm-4-7-flash` 와 쓸 로컬 모델을 넣는다(값은 게임 서버의 `scripts/models.py`).
- **가격표.** 결제 서버가 떠 있으면 "지금 팔고 있는 모델"만 고를 수 있다. staging 의 가격표에 로컬 모델의 이름표가 없으면 그 모델이 목록에 나오지 않는다([열린 질문](#열린-질문)).

## 올리는 방식

**1단계(첫 배포): VM 에서 빌드한다.** VM 에 저장소를 받고, `main` 의 커밋 하나를 꺼내 `docker compose up -d --build` 한다(루트 `.env` 의 `COMPOSE_FILE` 과 `COMPOSE_PROFILES` 가 운영 설정과 프로필을 고른다).

- 단계가 가장 적다. 이미지 저장소도, 저장소 인증도 필요 없다.
- 대가: 서버 다섯과 워커를 빌드하는 동안 VM 의 메모리와 CPU 를 쓴다(그동안 서버가 느려진다). 어느 이미지가 어느 커밋인지는 VM 에서 꺼낸 커밋으로만 안다.
- 되돌리기는 앞 커밋을 꺼내 다시 빌드하는 것이다. 마이그레이션은 되돌리지 않는다(되돌려야 하면 백업에서 푼다).

**2단계: CI 가 이미지를 만들어 GHCR 에 올린다.** `main` 에 머지되면 서버마다 이미지를 만들고 커밋 해시를 이름표로 붙여 올린다. VM 은 이름표를 골라 받기만 한다.

- 버전이 이름표로 남고, 되돌리기가 이름표 바꾸기다. VM 은 빌드하지 않는다.
- 대가: 워크플로가 하나 늘고, VM 이 GHCR 에서 받을 토큰(읽기만)이 필요하다.
- 1단계를 몇 번 해 보고, 빌드가 VM 을 느리게 하거나 되돌릴 일이 생기면 옮긴다.

운영 설정은 지금의 `docker-compose.yml` 에 덮어쓰는 파일(`docker-compose.staging.yml`) 하나다. 바꾸는 것은 프록시의 포트와 TLS, certbot, 허용 주소, 환경 이름, 인증 서버의 도메인과 쿠키, 모델의 주소, 임베딩의 Ollama 다. 로컬의 파일을 고쳐 로컬과 갈라지게 하지 않는다. 망(networks)은 덮어쓰지 않는다(서버마다 메트릭을 붙이는 PR 이 망을 더한다).

CI(`stack`)가 운영 설정도 본다(`.github/scripts/stack-smoke.sh check-staging`). 두 파일을 겹친 설정에서 비밀의 범위, 바깥에 여는 포트, 로그 상한을 보고, staging 의 프록시를 자체 서명 인증서로 하나 더 띄워 HTTPS, 넘기기, 허용 주소, HSTS 를 본다.

## 비밀과 설정

- VM 에 서버마다의 `.env` 와 루트 `.env`, JWT 키(`auth-server/keys/`)를 둔다. 저장소에는 넣지 않는다. 파일은 주인만 읽게(600) 한다.
- 루트 `.env` 에 staging 의 값을 더 적는다(`.env.example` 의 "staging" 절): `COMPOSE_FILE`, `COMPOSE_PROFILES`, `DOMAIN`, `ACME_EMAIL`, `GAME_LLM_BASE_URL`, `GRAFANA_ADMIN_PASSWORD`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **로컬의 값을 그대로 옮기지 않는다.** DB 비밀번호, 서버끼리의 서명 비밀, JWT 키를 VM 에서 새로 만든다. 로컬의 값은 이 PC 의 여러 곳(작업 폴더 넷)에 퍼져 있다.
- 서버끼리 같아야 하는 비밀은 짝을 맞춘다. 명령은 README 의 "모든 서버를 컨테이너로"에 있다.

| 이쪽 | 저쪽(같은 값) |
| --- | --- |
| `auth-server/.env` 의 `BILLING_SECRET` | `billing-server/.env` 의 `AUTH_SERVER_SECRET` |
| `game-server/.env` 의 `BILLING_SECRET` | `billing-server/.env` 의 `GAME_SERVER_SECRET` |
| `game-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `GAME_SERVER_SECRET` |
| `billing-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `BILLING_SERVER_SECRET` |
| `board-server/.env` 의 `NOTIFICATION_SECRET` | `notification-server/.env` 의 `BOARD_SERVER_SECRET` |

- 비밀의 원본은 비밀번호 관리자 하나에 둔다. VM 이 사라지면 거기서 다시 만든다. `.env` 를 백업 파일과 같은 곳에 두지 않는다(README "백업과 복원").
- 어느 프로세스가 어느 비밀을 받는지는 지금처럼 `secret_scope.py` 의 표가 지킨다. 운영 설정을 겹친 뒤에도 CI 가 같은 표로 본다.

## 외부 서비스

| 것 | 혼자 쓰는 동안 | 공개 전에 |
| --- | --- | --- |
| AI 모델 | Z.ai(GLM-4.7-Flash, 무료)와 집 PC 의 Ollama([모델](#모델)). 다른 회사의 키를 붙이면 각 콘솔에서 월 사용 한도를 낮게 걸어 둔다 | 같다 |
| 메일 | 비워 두거나 Gmail SMTP 와 앱 비밀번호(이미 쓰는 것) | 하루 발송 한도가 있어 SES 로 바꾼다. SES 는 도메인 인증과 샌드박스를 나오는 신청이 필요하다 |
| 본인인증 | 가짜 업체(`fake`) | 실제 업체와 계약(#336). 보통 사업자등록이 먼저다 |
| 결제 | 가짜 결제 대행사(`fake`) | 사업자등록과 전자결제 계약. 토스 테스트 모드를 쓰면 웹훅 주소(`POST /api/v1/billing/webhooks/toss`)만 허용 주소 밖에 연다(서버가 결과를 토스에 다시 물어 믿는다) |
| 사설망 | Tailscale(VM ↔ 집 PC) | 집 PC 를 쓰지 않으면 뺀다 |

## 백업

- 지금의 `db-backup` 이 날마다 DB 를 한 파일로 뜨고 14개를 남긴다(README "백업과 복원").
- **바깥 저장소에 한 벌 더 둔다.** 같은 디스크에만 있으면 디스크가 망가질 때 함께 사라진다. Lightsail 의 버킷(객체 저장소)에 올린다.
  - 올리기 전에 암호화한다. 백업에는 이메일, 비밀번호 해시, 결제 원장이 있다. 열쇠는 VM 에 두지 않고 비밀번호 관리자에 둔다(공개키로 잠그는 방식이면 VM 에는 공개키만 둔다).
  - 버킷의 열쇠는 그 버킷에 올리는 권한만 갖게 만든다. 지우는 권한은 주지 않는다. VM 을 빼앗겨도 백업을 지우지 못한다.
- **되살려 본다.** 한 달에 한 번 버킷의 파일을 내려받아 로컬에서 푼다(README 의 `check` 와 복원 순서). 되살려 보지 않은 백업은 있는지 모르는 것과 같다.

## 지켜보기

혼자 쓰는 동안은 가볍게 간다. 로그를 모으는 것(Alloy, Loki, Grafana)과 메트릭의 저장소(Prometheus)는 compose 의 프로필 `observability` 로 붙였다(#25, [README 의 로그와 메트릭 모으기](../../README.md#로그와-메트릭-모으기)). `staging` 에서 켠다(`COMPOSE_PROFILES=app,observability`). Grafana 는 지금처럼 `127.0.0.1:3000` 에만 열고 SSH 터널로 붙는다. 서버의 메트릭은 서버마다 붙이는 중이다.
수집기, 보관 기간, Grafana 를 여는 곳은 [관측 규격](../observability.md#수집기grafana-alloy를-붙일-자리)에 정했다.
같은 VM 에 올리므로 메모리를 다시 잰다(아래 [열린 질문](#열린-질문)). 문제가 생기면 로그와 메트릭을 S3 에 따로 두고 VM 을 나눈다.

- **가동 확인.** 바깥의 무료 감시(UptimeRobot 등)가 몇 분마다 `https://<도메인>/healthz` 를 부르고, 죽으면 메일을 보낸다. 프록시 자신만 답한다(`{"status":"ok"}`). VM, nginx, TLS 가 살아 있는지를 본다. 감시가 인증서의 만료도 보면 켠다.
- **인증서의 남은 날짜.** certbot 의 `healthy` 다([도메인과 TLS](#도메인과-tls)). 지금은 `docker compose ps` 로 본다. 컨테이너의 상태를 경보로 잇는 일은 #25 의 경보에서 한다.
- **디스크.** 로그에는 상한이 있지만 백업과 이미지가 쌓인다. 남은 공간이 줄면 알린다(Lightsail 의 경보나 cron 한 줄).
- **컨테이너의 상태**(`docker compose ps` 의 `healthy`).
- 장애 판정은 이 수치와 조건이 한다. 관리 서버와 요약은 나중이다(`docs/observability.md`).

## VM 준비 순서

처음 한 번 하는 일이다. 명령을 README 의 배포 절로 옮기는 일은 [만드는 순서](#만드는-순서)의 4번이다.

1. Lightsail 에 인스턴스를 만든다(서울, Ubuntu, 8GB). 고정 IP 를 붙이고, 방화벽에서 22 를 내 주소로 좁히고 80, 443 을 연다. 자동 스냅샷을 켠다.
2. SSH 를 키로만 받게 한다. 패키지를 올리고 보안 업데이트를 저절로 받게 한다(unattended-upgrades).
3. 스왑 2GB 를 만든다.
4. Docker 와 compose 를 공식 저장소에서 설치한다. `/etc/docker/daemon.json` 에 로그 상한을 적는다(README "외부에 열기 전").
5. Tailscale 을 VM 과 집 PC 에 설치하고 같은 사설망에 넣는다. 접근 규칙(ACL)으로 VM 이 집 PC 의 11434 에만 닿게 한다. 집 PC 의 Ollama 를 사설망 주소에만 듣게 한다.
6. 도메인을 사서 A 레코드를 고정 IP 로 가리킨다.
7. 저장소를 받고, 비밀과 `.env` 를 새로 만들어 둔다. 루트 `.env` 에 staging 의 값을 적는다([비밀과 설정](#비밀과-설정)).
8. 허용 주소를 적는다: `cp docker/nginx/allowlist/allow.conf.example docker/nginx/allowlist/allow.conf` 그다음 내 공인 IP 를 `allow` 줄로.
9. 인증서를 처음 받는다: `docker compose run --rm -p 80:80 certbot issue --dry-run` 이 통과하면 `docker compose run --rm -p 80:80 certbot issue`.
10. 띄운다: `docker compose up -d --build`. 처음에는 `ollama-pull` 이 `bge-m3`(1GB 남짓)를 받느라 게임 서버가 늦게 뜬다.
11. 모델 목록을 넣는다([모델](#모델)). 결제 서버의 가격표에 쓸 모델이 있는지 본다.
12. 확인: HTTPS 로 닿는지, 내 주소가 아니면 403 인지(휴대폰의 데이터망으로), `/healthz` 가 어디서나 답하는지, 서버들과 certbot 이 `healthy` 인지, 백업이 쌓이는지, 가동 확인이 메일을 보내는지. `docker stats` 로 메모리를 재서 [열린 질문](#열린-질문)에 적는다.
13. 운영자 계정을 만들고 인증 서버 관리자 화면에서 `operators` 그룹에 넣는다(SSH 터널로 연다).

## 만드는 순서

PR 하나에 한 가지다.

1. **이 문서.** (#449)
2. **운영 설정과 TLS.** (#451) `docker-compose.staging.yml`(프록시의 80/443, certbot, 허용 주소, 환경 이름, 인증 서버의 도메인과 쿠키, 모델의 주소, 임베딩의 Ollama), nginx 의 TLS 와 허용 주소와 HSTS, `port_scope.py --public`, 가동 확인 주소, CI 의 `check-staging`.
3. **바깥 백업.** 암호화하고 버킷에 올리는 단계, 그 열쇠의 권한, 되살리는 순서.
4. **VM 준비.** 위 순서의 명령과 README 의 배포 절.
5. (나중) **GHCR 로 올리기.**

## 정식 공개 전에 더 필요한 것

혼자 쓰는 서버에서 베타나 공개로 갈 때 할 일이다. 자세한 점검은 #274 에 있다.

- 화면(#290). 디자인은 Stitch, 그림은 나노 바나나로 만든다. 화면이 사용자 글, 채팅, AI 서술을 HTML 로 실행하지 않는다(#274).
- 실제 본인인증(#336)과 `APP_ENVIRONMENT=production`. 그 전에 지인 베타를 연다면 성인 콘텐츠와 환영 크레딧을 막는 방법을 정한다.
- 가입 때의 약관과 개인정보 동의(#450). 개인정보 처리방침과 이용약관(운영자가 기록을 볼 수 있다는 것, `docs/architecture/operators.md` 의 "사용자에게 알릴 것").
- 메일을 SES 로.
- 사업자등록, 실제 결제, 청소년 보호와 콘텐츠 관련 규정의 확인(법률 검토가 아니다).
- 허용 주소를 뺀다. 그때부터 요청 수 제한과 시도 제한이 실제 방어선이 된다.

## 열린 질문

- 실제 메모리 사용량. 처음 띄운 뒤 `docker stats` 로 잰다. 로그·메트릭 모으기(1~1.5GB)와 임베딩의 Ollama(1~1.5GB, 상한 2GB)를 함께 켜면 8GB 에서 빠듯할 수 있다. 4GB 로 줄일 수 있는지도 본다.
- staging 의 가격표에 로컬 모델(집 PC 의 Ollama)의 이름표를 넣을지와 그 값. 결제 서버의 가격표에 없으면 그 모델을 고를 수 없다.
- 화면의 코드는 누가 쓰는가. Stitch 가 내주는 것(디자인과 HTML)을 React 로 옮기는 일이 남는다.
- 화면을 어디서 내주는가. 같은 nginx 가 정적 파일로 낼지, 따로 둘지. API 의 CSP 와 화면의 CSP 를 나눠야 한다(README "외부에 열기 전").
- 바깥 백업의 암호화 방식(gpg, age)과 열쇠를 두는 곳.
- 모델 회사마다의 월 사용 한도를 어디에 기록해 둘지.
- 이름 바꾸기(`game-server` → `trpg-server`). 운영 설정과 nginx 의 틀에 `game-server` 가 들어 있다. 바꿀 때 함께 바꾸고, 로그의 `service` 가 바뀌는 날을 적어 둔다(Loki 와 Prometheus 에서 그 앞뒤로 두 이름을 함께 찾는다).
