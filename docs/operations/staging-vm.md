# staging VM 준비

[배포 설계](../architecture/deployment.md)의 "VM 준비 순서"를 실제 명령으로 적는다. 처음 한 번 하는 일이다. 무엇을 왜 그렇게 정했는지는 배포 설계에 있고, 여기에는 순서와 명령만 둔다.

- 기준: `main` `38c3292` (2026-10-19). 명령은 VM 을 실제로 만들 때 한 번 따라 해 보고 고친다.
- 명령마다 어디서 치는지 붙인다: **[웹]** AWS·도메인·Tailscale 의 콘솔, **[집 PC]** Windows 의 PowerShell, **[VM]** VM 에 SSH 로 붙은 bash.
- `<...>` 는 사람마다 다른 값이다. 처음 정할 때 비밀번호 관리자에 함께 적어 둔다: 도메인, VM 의 고정 IP, 집 PC 의 Tailscale 주소, S3 버킷의 이름.
- 순서를 바꾸지 않는다. 특히 인증서는 프록시를 띄우기 전에 받는다(인증서 파일이 없으면 프록시가 뜨지 않는다).

## 목차

1. [AWS 와 도메인](#1-aws-와-도메인)
2. [VM 의 기본](#2-vm-의-기본)
3. [Docker](#3-docker)
4. [Tailscale 과 집 PC 의 Ollama](#4-tailscale-과-집-pc-의-ollama)
5. [저장소와 열쇠](#5-저장소와-열쇠)
6. [.env](#6-env)
7. [허용 주소와 첫 인증서](#7-허용-주소와-첫-인증서)
8. [띄우기](#8-띄우기)
9. [모델 목록과 운영자 계정](#9-모델-목록과-운영자-계정)
10. [확인](#10-확인)
11. [그 뒤로](#11-그-뒤로)

## 1. AWS 와 도메인

**[웹] Lightsail 인스턴스**

1. 서울(`ap-northeast-2`), Linux, Ubuntu LTS, 8GB 번들로 만든다. 이름은 `ai-trpg-staging`.
2. **고정 IP** 를 만들어 붙인다.
3. **방화벽(Networking → IPv4 Firewall)**: SSH(22)는 "Restrict to IP address" 로 집의 공인 IP 만 둔다. HTTP(80), HTTPS(443)를 더한다. 그 밖은 지운다. IPv6 방화벽도 같게 둔다.
4. **자동 스냅샷**을 켠다.

**[웹] S3 와 IAM (바깥 백업)**

1. S3 에 버킷을 만든다: 서울, "모든 퍼블릭 액세스 차단" 켬, **버킷 버전 관리 켬**. 이름이 `<버킷>` 이다.
2. 버킷의 수명 주기 규칙: 접두사 `trpg-`, 현재 버전은 만든 지 35일 뒤 만료, 이전 버전은 30일 뒤 영구 삭제.
3. IAM 사용자 `ai-trpg-backup` 을 만든다(콘솔 로그인 없음). 인라인 정책에 `docker/backup-offsite/iam-policy.json` 을 붙이고 `BUCKET_NAME` 을 `<버킷>` 으로 바꾼다.
4. 그 사용자의 접근 키를 만든다(용도: 그 밖). 두 값을 비밀번호 관리자에 둔다. 6번에서 `.env` 에 적는다.

**[웹] S3 와 IAM (그림)**. 백업과 다른 버킷, 다른 사용자다. 백업의 키는 지우지 못하고 그림의 키는 지운다(배포 설계의 "그림 저장소").

1. S3 에 버킷을 만든다: 서울, "모든 퍼블릭 액세스 차단" 켬, 버전 관리는 끔(지운 그림이 남지 않게). 이름이 `<그림 버킷>` 이다. 모든 그림은 nginx 를 거쳐 나가므로 공개할 일이 없다.
2. IAM 사용자 `ai-trpg-images` 를 만든다(콘솔 로그인 없음). 인라인 정책에 `docker/object-store/iam-policy.json` 을 붙이고 `BUCKET_NAME` 을 `<그림 버킷>` 으로 바꾼다.
3. 그 사용자의 접근 키를 만든다(용도: 그 밖). 두 값을 비밀번호 관리자에 둔다. 6번에서 `.env` 에 적는다.

**[웹] 도메인**: `<도메인>` 의 A 레코드를 VM 의 고정 IP 로 둔다. 프록시(Cloudflare 의 주황 구름 등)는 켜지 않는다.

## 2. VM 의 기본

**[집 PC]** Lightsail 의 기본 키(계정 → SSH 키에서 받는다)로 붙는다.

```powershell
ssh -i $HOME\.ssh\LightsailDefaultKey-ap-northeast-2.pem ubuntu@<VM 의 고정 IP>
```

**[VM]** SSH 는 키로만 받는지, root 로 들어올 수 없는지 본다. 둘 다 `no` 여야 한다(Lightsail 의 Ubuntu 는 기본이 그렇다).

```bash
sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin) '
```

`yes` 가 보이면 `/etc/ssh/sshd_config.d/10-hardening.conf` 에 `PasswordAuthentication no` 와 `PermitRootLogin no` 를 적고 `sudo systemctl reload ssh`.

**[VM]** 패키지를 올리고 보안 업데이트를 저절로 받게 한다. 스왑 2GB 를 만든다.

```bash
sudo apt update && sudo apt -y upgrade
sudo apt install -y unattended-upgrades age git
sudo dpkg-reconfigure -plow unattended-upgrades        # "Yes"
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                                               # Swap 이 2.0Gi 면 된다
```

## 3. Docker

**[VM]** 공식 저장소에서 설치한다(Ubuntu 의 `docker.io` 가 아니다). [Docker 의 설치 안내](https://docs.docker.com/engine/install/ubuntu/)와 같다.

```bash
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

**[VM]** Docker 의 로그에도 상한을 둔다(README "외부에 열기 전"). `ubuntu` 를 `docker` 그룹에 넣는다. 그룹에 든 사용자는 root 와 같은 권한이다. 이 VM 의 사용자는 운영자 하나뿐이다.

```bash
echo '{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }' | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
sudo usermod -aG docker ubuntu
exit                                                  # 다시 붙어야 그룹이 먹는다
```

## 4. Tailscale 과 집 PC 의 Ollama

VM 은 집 PC 의 Ollama(11434)에만 닿고, 집의 다른 기기에는 닿지 않게 한다.

**[웹] Tailscale 의 접근 규칙(Access controls)**: 기본 규칙을 아래로 바꾼다. `<집 PC 의 Tailscale 주소>` 는 집 PC 에 Tailscale 을 설치한 뒤 관리 화면에 보이는 `100.` 으로 시작하는 주소다.

```json
{
  "tagOwners": { "tag:staging": ["autogroup:admin"] },
  "hosts": { "home-pc": "<집 PC 의 Tailscale 주소>" },
  "grants": [
    { "src": ["autogroup:member"], "dst": ["*"], "ip": ["*"] },
    { "src": ["tag:staging"], "dst": ["home-pc"], "ip": ["tcp:11434"] }
  ]
}
```

태그를 붙인 기기(VM)는 `autogroup:member` 가 아니라서 첫 줄을 받지 않는다. VM 이 닿는 곳은 둘째 줄의 하나뿐이다.

**[VM]** 설치하고 태그를 붙여 들어간다. 화면에 나오는 주소를 브라우저로 열어 승인한다.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --advertise-tags=tag:staging
```

**[집 PC]** Tailscale 을 설치하고 같은 계정으로 들어간다. Ollama 가 사설망 주소에만 듣게 하고, 그 주소로 오는 11434 만 방화벽에서 연다(관리자 PowerShell). 그다음 Ollama 를 껐다 켠다.

```powershell
setx OLLAMA_HOST "<집 PC 의 Tailscale 주소>:11434"
New-NetFirewallRule -DisplayName "Ollama over Tailscale" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Action Allow
```

**[VM]** 닿는지 본다. 모델 목록(JSON)이 나오면 된다.

```bash
curl -s http://<집 PC 의 Tailscale 주소>:11434/api/tags | head -c 300; echo
```

## 5. 저장소와 열쇠

**[VM]** 저장소를 받는다. 공개 저장소라 인증이 필요 없다.

```bash
sudo mkdir -p /srv/ai-trpg && sudo chown ubuntu:ubuntu /srv/ai-trpg
git clone https://github.com/epqlffltm/ai-trpg.git /srv/ai-trpg
cd /srv/ai-trpg
```

**[집 PC] 바깥 백업의 주 열쇠.** VM 에 두지 않는다. 비밀번호 관리자와 오프라인 사본(USB 등) 두 곳에 둔다. 공개키(`age1...`)를 적어 둔다.

```powershell
winget install FiloSottile.age
age-keygen -o "$HOME\ai-trpg-master.key"
```

**[VM] 확인 열쇠와 JWT 의 서명 키.** 둘 다 git 에 올라가지 않는 폴더다. 확인 열쇠도 비밀번호 관리자에 한 벌 둔다.
JWT 키는 컨테이너의 사용자(10001)가 읽게 주인을 바꾼다(README "모든 서버를 컨테이너로").

```bash
cd /srv/ai-trpg
mkdir -m 700 backup-keys && age-keygen -o backup-keys/check.key && chmod 600 backup-keys/check.key
mkdir -p auth-server/keys
(umask 077 && openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out auth-server/keys/jwt-private.pem)
sudo chown 10001 auth-server/keys/jwt-private.pem
```

## 6. .env

**[VM]** 여섯(루트와 서버 다섯)을 `tools/staging_env.py` 로 만든다. 이 도구는 두 단계다.

1. 로컬과 같은 `tools/fill_env.py` 를 불러 `.env.example` 에서 여섯을 만들고 비밀을 모두 난수로 채운다. 서버끼리 같아야 하는 비밀의 짝과 DB 비밀번호도 그 도구가 맞추고, 주석으로 막힌 짝의 줄(`# BILLING_SECRET=` 등)도 켠다(짝의 표는 그 도구의 `SECRETS` 하나다).
2. staging 의 값(도메인, `COMPOSE_FILE`, 서술 모델, `PAYMENT_PROVIDER=fake` 등)을 적고, 게임 서버만 아는 비밀 둘(`SIGNAL_SECRET`, `AI_LOG_HMAC_KEY`)도 켠다. 로컬에서는 막혀 있는 것들이다. `SIGNAL_SECRET` 을 켜면 서버를 다시 띄워도 신호의 서명이 같고, `AI_LOG_HMAC_KEY` 를 켜면 호출 기록에 입력의 지문이 남는다.

파일은 주인만 읽는다(600). 여섯 가운데 하나라도 이미 있으면 덮어쓰지 않고 멈춘다. 이미 있는 `.env` 의 빈 비밀만 다시 채울 때는 `python3 tools/fill_env.py` 를 쓴다.
VM 에는 uv 가 없어 Ubuntu 에 든 `python3` 로 돌린다(표준 라이브러리만 쓴다).

```bash
cd /srv/ai-trpg
python3 tools/staging_env.py --domain <도메인> --acme-email <메일> \
  --llm-base-url http://<집 PC 의 Tailscale 주소>:11434/v1 --s3-bucket <버킷> --image-bucket <그림 버킷> \
  --age-recipients "<주 열쇠의 공개키> $(age-keygen -y backup-keys/check.key)"
```

`fill_env.py` 가 "밖에서 받는 키"를 여럿 알리지만, staging 에서 채울 것은 끝에 찍히는 "사람이 채울 것" 다섯뿐이다(나머지는 쓰지 않는 창구와 메일). 비어 있으면 compose 가 뜨기를 거부하거나(S3 의 키), 그 창구의 모델을 부르지 않는다(Z.ai 의 키).
그림 저장소의 비밀 키(`IMAGE_STORE_SECRET_ACCESS_KEY`)는 로컬에서는 `fill_env.py` 가 난수로 채우지만 staging 에서는 IAM 사용자의 키라서 이 도구가 비워 둔다.

```bash
nano .env                       # BACKUP_AWS_ACCESS_KEY_ID, BACKUP_AWS_SECRET_ACCESS_KEY (1번의 백업 접근 키)
                                # IMAGE_STORE_ACCESS_KEY_ID, IMAGE_STORE_SECRET_ACCESS_KEY (1번의 그림 접근 키)
nano trpg-server/.env           # ZAI_API_KEY
```

경보를 휴대폰 등으로 받으려면 루트 `.env` 에 받는 곳(Discord, Slack, Telegram, 메일 가운데 적은 것만)을 적는다. 적는 이름과 만드는 법은 README 의 "경보"에 있다. 적지 않으면 Grafana 의 Alerting 화면에서만 본다.

여섯 파일과 두 열쇠를 비밀번호 관리자에 둔다. VM 을 잃으면 거기서 되살린다. 백업 파일과 같은 곳에 두지 않는다.

## 7. 허용 주소와 첫 인증서

**[VM]** 집의 공인 IP 를 허용 주소에 적는다. 줄이 없으면 아무도 서버에 닿지 못한다.

```bash
cd /srv/ai-trpg
cp docker/nginx/allowlist/allow.conf.example docker/nginx/allowlist/allow.conf
echo "allow <집의 공인 IP>;" >> docker/nginx/allowlist/allow.conf
```

**[VM]** 인증서를 처음 받는다. 프록시를 띄우기 전이라 certbot 이 직접 80 을 듣는다. 먼저 시험 서버로 해 보고(발급 한도에 세지 않는다), 통과하면 진짜를 받는다.

```bash
docker compose run --rm -p 80:80 certbot issue --dry-run
docker compose run --rm -p 80:80 certbot issue
```

`--dry-run` 이 실패하면 대개 셋 가운데 하나다: 도메인의 A 레코드가 아직 퍼지지 않았다(`dig +short <도메인>`), Lightsail 방화벽에 80 이 없다, 80 을 다른 것이 쓰고 있다.

## 8. 띄우기

**[VM]** 루트 `.env` 의 `COMPOSE_FILE` 과 `COMPOSE_PROFILES` 가 운영 설정과 프로필을 고르므로 명령에 `-f` 와 `--profile` 을 붙이지 않는다.
처음에는 이미지를 빌드하고 `ollama-pull` 이 `bge-m3`(1GB 남짓)를 받느라 시간이 걸린다.

```bash
cd /srv/ai-trpg
docker compose up -d --build
docker compose ps -a
```

`*-migrate` 다섯과 `ollama-pull` 이 `Exited (0)`, 서버 다섯과 `proxy`, 워커 넷, `certbot`, `ollama`, `prometheus`, `grafana` 가 `healthy` 면 된다.
`backup-offsite` 는 처음 올리고 풀어 보는 동안(15분 안) `starting` 이다. cron 둘과 Alloy, Loki 는 `Up` 이다.

## 9. 모델 목록과 운영자 계정

**[VM] 모델 목록.** 목록이 비어 있으면 시나리오를 저장하지 못한다. 넣는 명령의 값은 [게임 서버의 README](../../trpg-server/README.md) 의 `scripts.models` 에 있다.

```bash
docker compose exec trpg-server python -m scripts.models list
docker compose exec trpg-server python -m scripts.models add glm-4-7-flash --provider zai --api-model-id glm-4.7-flash \
  --name "GLM-4.7-Flash" --vendor zai --grade basic --reasoning-style thinking_type
```

결제 서버가 떠 있으면 결제 서버의 가격표에 있는 모델만 고를 수 있다. 무료 모델은 가격표에 올리지 않기로 했으므로(게임 서버 README) 지금 그대로는 staging 에서 고를 수 없다. 정할 것으로 남긴다(배포 설계의 열린 질문).

**[VM] 운영자 계정.** 관리 계정을 만들고, 관리자 화면에서 `operators` 그룹에 넣는다.

```bash
docker compose exec auth-server python manage.py createsuperuser
```

**[집 PC]** 관리자 화면과 Grafana 는 SSH 터널로만 연다. 띄워 둔 채 브라우저에서 `http://localhost:8000/admin/`, `http://localhost:3000` 을 연다. Grafana 의 비밀번호는 루트 `.env` 의 `GRAFANA_ADMIN_PASSWORD` 다.

```powershell
ssh -i $HOME\.ssh\LightsailDefaultKey-ap-northeast-2.pem -L 8000:127.0.0.1:8000 -L 3000:127.0.0.1:3000 ubuntu@<VM 의 고정 IP>
```

## 10. 확인

| 무엇을 | 어떻게 | 되면 |
| --- | --- | --- |
| HTTPS 와 가동 확인 | [집 PC] `curl.exe -s https://<도메인>/healthz` | `{"status":"ok"}` |
| HTTP 를 넘기기 | [집 PC] `curl.exe -sI http://<도메인>/api/v1/game/me` | `301` 과 `Location: https://<도메인>/...` |
| 집에서는 서버에 닿는다 | [집 PC] `curl.exe -s -o NUL -w "%{http_code}" https://<도메인>/api/v1/game/me` | `401`(토큰이 없어서. 서버가 답했다) |
| 집 밖에서는 막힌다 | 휴대폰의 데이터망(와이파이를 끄고)으로 `https://<도메인>/api/v1/game/me` | `403` 과 "허용된 주소에서만" |
| 컨테이너 | [VM] `docker compose ps -a` | 8번의 상태 |
| 인증서의 갱신 | [VM] `docker compose run --rm certbot renew --dry-run` | "Congratulations, all simulated renewals succeeded" |
| 바깥 백업 | [VM] `docker compose logs backup-offsite` | "올렸다", "풀어 봤다" 줄 |
| 주 열쇠로 풀리는가 | [웹] S3 콘솔에서 가장 최근 `trpg-*.dump.age` 를 받는다. [집 PC] `age -d -i "$HOME\ai-trpg-master.key" -o check.dump <받은 파일>` 이 오류 없이 끝나면 지운다 | 주마다 저절로 푸는 것은 확인 열쇠뿐이다. 주 열쇠는 이때 손으로 본다 |
| 메모리 | [VM] `docker stats --no-stream` | 합을 배포 설계의 열린 질문에 적는다 |
| 가동 확인의 경보 | 바깥의 감시(UptimeRobot 등)에 `https://<도메인>/healthz` 를 걸고, 잠깐 `docker compose stop proxy` 로 메일이 오는지 본다 | 다시 `docker compose start proxy` |

## 11. 그 뒤로

**새 커밋을 올린다(1단계: VM 에서 빌드).** 마이그레이션은 되돌리지 않는다. 되돌려야 하면 백업에서 푼다.

```bash
cd /srv/ai-trpg && git pull && docker compose up -d --build
```

**허용 주소를 바꾼다.** `docker/nginx/allowlist/allow.conf` 를 고치면 1분 안에 다시 읽는다. 바로 읽히려면 `docker compose exec proxy nginx -s reload`. 집의 주소가 바뀌었으면 Lightsail 방화벽의 22 도 고친다.

**로그를 본다.** Grafana(9번의 터널) 또는 `docker compose logs --tail 100 <서비스>`.
