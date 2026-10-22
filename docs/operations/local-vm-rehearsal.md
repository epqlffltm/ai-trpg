# 로컬 VM 리허설

[staging VM 준비](staging-vm.md)의 순서서를 클라우드에 VM 을 빌리기 전에 집 PC 의 VM 에서 한 번 따라 해 본다. 순서서 그대로 따라 하고, 로컬이라 바꿔야 하는 곳만 여기에 적는다.

- 2026-10-22 에 정했다. 순서는 **로컬 VM 리허설 → 화면(#290) → 클라우드 VM(#491)** 이다([배포 설계](../architecture/deployment.md)의 머리).
- 2026-10-22 에 한 번 했다(`main` `8dddef0`). 순서서의 틀린 곳은 그 자리에서 고쳤고, 숫자와 찾은 것은 아래 [결과](#결과-2026-10-22)에 있다.
- 하루 안에 끝낸다. 순서서의 틀린 곳을 고치고, 아무도 쓰지 않을 때의 메모리(바닥값)를 재는 것이 목적이다.
- 명령마다 어디서 치는지 붙인다: **[집 PC]** Windows 의 PowerShell, **[VM]** VM 에 SSH 로 붙은 bash.

## 보는 것과 보지 않는 것

| 본다 | 보지 않는다(클라우드 VM 에서 본다) |
| --- | --- |
| 순서서의 명령이 그대로 도는가, 빠진 단계가 없는가 | 실제 도메인과 Let's Encrypt 의 인증서. 여기서는 자체 서명 인증서를 쓴다 |
| 8GB, 2코어에서 모두 뜨는가. 가만히 있을 때의 메모리(바닥값) | 바깥 백업(S3)과 그림 버킷(S3). 키가 없어 끈다 |
| 띄우는 순서, healthcheck, VM 을 다시 켰을 때 모두 다시 뜨는가 | 사용자가 있을 때의 연결 수, 메모리, 디스크가 하루에 느는 양 |
| 데이터 디스크 둘의 마운트, 경보가 울리는가, 로컬 백업 | Tailscale, Lightsail 의 방화벽과 스냅샷 |

부하가 걸린 숫자는 여기서 재도 바닥값일 뿐이다. 그 숫자로 몫(#592)이나 보관 기간(#539)을 고치지 않는다.

## 1. VM 을 만든다

[staging VM 준비](staging-vm.md)의 1번(AWS 와 도메인)을 이것으로 바꾼다.

**VMware Workstation Pro** 를 쓴다(개인 사용은 무료, Broadcom 의 계정으로 받는다). Windows Pro 라면 Hyper-V 도 된다. WSL2 는 쓰지 않는다. 메모리 한도가 WSL 전체에 하나뿐이고, 디스크를 따로 붙이기 어렵고, Docker Desktop 과 엉킨다. Docker Desktop 이 켜 둔 Hyper-V 위에서도 VMware 는 돈다(조금 느리다).

| 칸 | 값 | 까닭 |
| --- | --- | --- |
| OS | Ubuntu Server 24.04 LTS | 클라우드 VM 과 같다. Lightsail 에는 아직 22 와 24 뿐이다. 26.04 는 `sudo` 와 기본 명령이 바뀌어 차이를 가리기 어렵다 |
| CPU, 메모리 | 2코어, 8GB | Lightsail 의 8GB 번들과 같다. 메모리를 재는 것이 목적이라 늘리지 않는다 |
| 기본 디스크 | 40GB, 미리 잡지 않는다 | OS 와 Docker 의 이미지. 처음 빌드가 26GB 를 쓴다([결과](#결과-2026-10-22)) |
| 디스크 둘을 더 | 16GB, 32GB | DB 와 관측(순서서의 "데이터 디스크 둘"). VM 을 만든 뒤 설정에서 더한다 |
| 네트워크 | NAT | 집 PC 에서 VM 의 주소로 닿고, VM 은 인터넷과 집 PC 에 닿는다 |

VM 을 만들 때 "I will install the operating system later" 를 고른다. Easy Install 이 사용자를 마음대로 만들지 않게 한다.

Ubuntu 를 설치할 때:

- **Storage**: 40GB 디스크를 고른다(16G, 32G 가 아니다). "Set up this disk as an LVM group" 을 끈다. 켜 두면 `/` 가 디스크의 절반(19G)만 쓴다. 이미 켜고 설치했으면 설치 뒤에 늘린다: `sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv`
- **Profile**: 사용자 이름은 무엇이든 된다. 순서서의 명령은 `$USER` 를 쓴다.
- **SSH**: OpenSSH server 를 고른다. GitHub 에 공개키가 있으면 "Import SSH key → from GitHub" 로 가져온다. 그러면 비밀번호로 SSH 에 붙는 것이 꺼진다.
- **Featured snaps**: 고르지 않는다. Docker 는 순서서대로 공식 저장소에서 깐다.
- 디스크 둘은 설치할 때 건드리지 않는다. 순서서 3번에서 포맷한다.
- 로그인한 뒤 `do-release-upgrade` 를 권해도 하지 않는다.

**[VM]** 주소를 본다. 이것이 `<VM 주소>` 다. 앞의 세 칸(`192.168.x`)이 VMware 의 NAT 망이다.

```bash
ip -4 -brief addr show
```

**[집 PC]** VMware 의 NAT 망에서 집 PC 의 주소를 본다. "VMware Network Adapter VMnet8" 의 IPv4 주소가 `<집 PC 의 VMnet8 주소>` 다(보통 `192.168.x.1`).

```powershell
ipconfig | Select-String -Context 0,4 "VMnet8"
```

**[집 PC]** 도메인 대신 hosts 파일에 이름을 하나 적는다(관리자 PowerShell). 이름은 `staging.ai-trpg.test` 로 한다. `.test` 는 실제로 쓰이지 않는 이름이다.

```powershell
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "`r`n<VM 주소> staging.ai-trpg.test"
```

**[집 PC] SSH 키.** Lightsail 은 키를 주지만 로컬 VM 은 내 키를 넣어야 한다. 설치할 때 GitHub 에서 가져왔으면 넘어간다. Windows 에는 `ssh-copy-id` 가 없어 이렇게 넣는다. 키가 없으면 먼저 `ssh-keygen -t ed25519`(물음은 모두 Enter).

```powershell
type $HOME\.ssh\id_ed25519.pub | ssh <사용자>@<VM 주소> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
ssh <사용자>@<VM 주소>                                # 비밀번호를 묻지 않으면 된다
```

비밀번호로 붙는 것을 끄기(순서서 2번) 전에 키로 붙는지 꼭 본다. 꺼진 뒤에 키가 없으면 VMware 의 콘솔로만 들어간다.

## 2. 순서서의 2, 3번은 그대로

VM 의 기본(SSH, 업데이트, 스왑), Docker, 데이터 디스크 둘을 [순서서](staging-vm.md)대로 한다. 다른 곳은 셋이다.

- 붙을 때: `ssh <사용자>@<VM 주소>`
- 스왑: 설치 프로그램이 `/swap.img`(4GB)를 이미 만들어 둔다. Lightsail 과 같게 순서서의 2GB 만 남긴다. 순서서의 스왑 줄 앞에 지운다.

  ```bash
  swapon --show                                         # /swap.img 가 보이면
  sudo swapoff /swap.img && sudo rm /swap.img && sudo sed -i '\|^/swap.img|d' /etc/fstab
  ```

- 데이터 디스크의 장치 이름이 `nvme1n1` 이 아니라 `sdb`, `sdc` 다. 순서서대로 `lsblk` 의 크기(16G, 32G)로 가린다.

## 3. 순서서의 4번(Tailscale)을 이것으로 바꾼다

Tailscale 을 쓰지 않는다. VM 이 집 PC 의 Ollama 에 NAT 망으로 닿는다.

**[집 PC]** Ollama 가 VMnet8 의 주소에서 듣게 하고, VMware 의 NAT 망에서 오는 11434 만 연다(관리자 PowerShell). 리허설이 끝나면 둘 다 되돌린다(아래 "끝나면"). 그동안 집 PC 에서 `localhost:11434` 로 부르는 것(로컬 스택의 서버 등)은 닿지 않는다.

```powershell
setx OLLAMA_HOST "<집 PC 의 VMnet8 주소>:11434"
New-NetFirewallRule -DisplayName "Ollama for local VM" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress <VMnet8 의 망, 예: 192.168.x.0/24> -Action Allow
```

**[집 PC]** Ollama 를 껐다 켠다. 트레이의 Quit 만으로는 서버(`ollama`)가 남아 새 주소를 읽지 않을 때가 있다. 남은 것까지 끄고 시작 메뉴에서 다시 켠다. 새 주소에서 듣는지 본다.

```powershell
Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force
netstat -ano | Select-String ":11434 "                # 시작 메뉴로 켠 뒤 <집 PC 의 VMnet8 주소>:11434 LISTENING 이면 된다
```

**[VM]** 닿는지 본다. 모델 목록(JSON)이 나오면 된다.

```bash
curl -s http://<집 PC 의 VMnet8 주소>:11434/api/tags | grep -o '"name":"[^"]*"'
```

Grafana 는 SSH 터널로 연다(아래 7번).

## 4. 순서서의 5번은 그대로

저장소를 받고, 데이터 디스크의 폴더를 만들고(`prepare-disks.sh`), JWT 의 서명 키를 만든다. age 의 열쇠는 둘 다 VM 에서 만든다. 바깥 백업을 끄므로 주 열쇠를 집 PC 에 둘 일이 없다.

```bash
cd /srv/ai-trpg
mkdir -m 700 backup-keys
age-keygen -o backup-keys/check.key && age-keygen -o backup-keys/master.key && chmod 600 backup-keys/*.key
```

## 5. 순서서의 6번(.env)에서 바꾸는 값

도메인, 모델의 주소, 버킷을 리허설의 것으로 준다. 버킷은 쓰지 않지만 도구가 받는다.

```bash
cd /srv/ai-trpg
python3 tools/staging_env.py --domain staging.ai-trpg.test --acme-email rehearsal@example.com \
  --llm-base-url http://<집 PC 의 VMnet8 주소>:11434/v1 --s3-bucket rehearsal-backup --image-bucket rehearsal-images \
  --age-recipients "$(age-keygen -y backup-keys/master.key) $(age-keygen -y backup-keys/check.key)"
```

"사람이 채울 것" 다섯 가운데 S3 의 키 넷은 아무 글자나 적는다. 비어 있으면 compose 가 뜨기를 거부한다. 쓰지 않는다(바깥 백업은 끄고, 그림 올리기는 아직 없다).

```bash
sed -i -E 's/^(BACKUP_AWS_ACCESS_KEY_ID|BACKUP_AWS_SECRET_ACCESS_KEY|IMAGE_STORE_ACCESS_KEY_ID|IMAGE_STORE_SECRET_ACCESS_KEY)=$/\1=rehearsal-not-used/' .env
grep -E '^(BACKUP_AWS|IMAGE_STORE_(ACCESS|SECRET))' .env    # 넷 다 rehearsal-not-used
```

`ZAI_API_KEY` 는 비워 둬도 된다. 서술은 집 PC 의 Ollama 로 한다.

## 6. 순서서의 7번(허용 주소와 첫 인증서)을 이것으로 바꾼다

**[VM] 허용 주소.** 집 PC 는 VMware 의 NAT 망에서 온다. 그 망을 적는다.

```bash
cd /srv/ai-trpg
cp docker/nginx/allowlist/allow.conf.example docker/nginx/allowlist/allow.conf
echo "allow <VMnet8 의 망, 예: 192.168.x.0/24>;" >> docker/nginx/allowlist/allow.conf
```

**[VM] 자체 서명 인증서.** Let's Encrypt 는 바깥에서 닿는 도메인이 있어야 한다. 대신 자체 서명 인증서를 만들어 프록시가 읽는 볼륨(`tls`)에 certbot 의 컨테이너로 넣는다. 주인과 권한은 `docker/certbot/deploy-hook.sh` 와 같게 한다. 90일짜리라 certbot 의 healthcheck(14일보다 적게 남으면 unhealthy)를 통과한다.

```bash
mkdir -p /tmp/selfsigned
openssl req -x509 -newkey rsa:2048 -nodes -days 90 -subj "/CN=staging.ai-trpg.test" \
  -addext "subjectAltName=DNS:staging.ai-trpg.test" \
  -keyout /tmp/selfsigned/privkey.pem -out /tmp/selfsigned/fullchain.pem
docker compose run --rm --no-deps -v /tmp/selfsigned:/src:ro --entrypoint sh certbot -c \
  'cp /src/privkey.pem /src/fullchain.pem /tls/ && chown 101:101 /tls/*.pem && chmod 600 /tls/privkey.pem && chmod 644 /tls/fullchain.pem && ls -la /tls'
rm -rf /tmp/selfsigned
```

## 7. 띄운다

순서서의 8번과 같고, 바깥 백업만 끈다. 처음 빌드는 2코어에서 오래 걸린다. SSH 가 끊겨도 이어지게 `tmux new -s up` 안에서 하고, 다시 붙으면 `tmux attach -t up` 이다(`tmux set -g mouse on` 이면 휠로 올려 본다).

```bash
cd /srv/ai-trpg
time docker compose up -d --build --scale backup-offsite=0
docker compose ps -a --format 'table {{.Service}}\t{{.Status}}'
```

`*-migrate` 일곱과 `ollama-pull` 이 `Exited (0)`, 서버 일곱과 `proxy`, 워커들, `certbot`, `ollama`, `prometheus`, `grafana` 가 `healthy` 면 된다. `certbot` 의 갱신은 받은 인증서가 없어 아무것도 하지 않는다.
마이그레이션 하나가 실패하면 `up` 이 거기서 멈추고, 아직 켜지 않은 서버는 상관이 없어도 `Created` 로 남는다. `docker compose logs <그 마이그레이션>` 으로 까닭을 보고 고친 뒤 `up` 을 다시 한다(빌드는 캐시로 건너뛴다).

**[집 PC]** Grafana 와 관리자 화면은 SSH 터널로 연다. 집 PC 의 로컬 스택이 3000 과 8000 을 쓰므로 집 PC 쪽은 13000, 18000 으로 연다. 같은 포트로 열면 `bind … Permission denied` 가 나고, 브라우저는 로컬 스택의 Grafana 를 연다(버전까지 같아 헷갈린다).

```powershell
ssh -L 13000:127.0.0.1:3000 -L 18000:127.0.0.1:8000 <사용자>@<VM 주소>
```

이 창을 띄워 둔 채 `http://localhost:13000`(Grafana, `admin` 과 루트 `.env` 의 `GRAFANA_ADMIN_PASSWORD`), `http://localhost:18000/admin/`(인증 서버의 관리자 화면)을 연다. 브라우저가 `localhost` 에 저장한 로컬 스택의 비밀번호를 채우므로 시크릿 창으로 연다.

순서서의 9번(모델 목록과 운영자 계정)은 그대로 한다. 서술 모델은 집 PC 의 Ollama 에 있는 것을 넣는다. 파일은 저장소 밖(`~/local-models.toml`)에 둔다. `local` 창구는 `token_limit_field` 를 적고 `reasoning_style` 은 적지 않는다(`ai_core/catalog_contract.py`).

```toml
format = 1

[[models]]
slug = "gemma4-26b-a4b"
provider = "local"
api_model_id = "gemma4:26b-a4b-it-qat"
display_name = "Gemma 4 26B A4B (집 PC)"
vendor = "google"
grade = "basic"
token_limit_field = "max_tokens"

[[models.costs]]
effective_from = 2026-10-22
checked_on = 2026-10-22
input_per_mtok = 0
output_per_mtok = 0
```

## 8. 확인

순서서의 10번에서 클라우드에 기대는 줄(집 밖의 403, 인증서의 갱신, 바깥 백업, 주 열쇠로 풀기, Tailscale, 바깥의 감시)을 빼고, 리허설에서만 할 수 있는 것을 더한다.
경보는 Prometheus 가 규칙을 갖고 Alertmanager 가 보낸다. Grafana 의 "Alert rules" 는 Grafana 의 규칙만 보여 비어 있다. 울리는 것은 Alerting → Active notifications 에서 데이터 소스를 `alertmanager` 로 골라 보거나, 아래처럼 VM 에서 본다.

```bash
# [VM] 지금 울리는 경보와 상태. Watchdog(늘 firing)만 있으면 조용하다
docker compose exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/alerts | grep -oE '"alertname":"[^"]+"|"state":"[a-z]+"' | paste - - | sort | uniq -c
```

| 무엇을 | 어떻게 | 되면 |
| --- | --- | --- |
| HTTPS 와 가동 확인 | [집 PC] `curl.exe -sk https://staging.ai-trpg.test/healthz` | `{"status":"ok"}`(자체 서명이라 `-k`) |
| HTTP 를 넘기기 | [집 PC] `curl.exe -sI http://staging.ai-trpg.test/api/v1/game/me` | `301` 과 `Location: https://staging.ai-trpg.test/...` |
| 서버에 닿는다 | [집 PC] `curl.exe -sk -o NUL -w "%{http_code}" https://staging.ai-trpg.test/api/v1/game/me` | `401` |
| 허용 주소 밖은 막힌다 | [VM] `allow.conf` 의 줄을 다른 망으로 바꾸고 `docker compose exec proxy nginx -s reload`, 위를 다시 | `403`, `/healthz` 는 그대로 `ok`. 줄을 되돌리고 다시 읽힌다 |
| 컨테이너 | [VM] `docker compose ps -a` | 7번의 상태 |
| 메모리(바닥값) | [VM] 다 뜨고 10분 뒤, Grafana 의 화면을 열기 전에 `free -h` 와 `docker stats --no-stream --format "{{.MemUsage}}\t{{.Name}}" \| sort -h -r \| head` | 합과 큰 것 다섯을 적는다. 스왑을 쓰는지 본다. Grafana 는 화면을 열면 커진다 |
| DB 의 연결(바닥값) | [VM] `docker compose exec db psql -U trpg -d trpg -c "select usename, count(*) from pg_stat_activity where usename is not null group by 1 order by 2 desc"` | 계정마다의 수를 적는다. 몫(#592)의 합 80 과 견준다 |
| 디스크 | [VM] `df -h / /mnt/db /mnt/observability` 와 `docker system df` | 16G, 32G 디스크가 보인다. 이미지와 빌드 캐시의 크기를 적는다 |
| 다시 켜기 | [VM] `sudo reboot`, 다시 붙어 `uptime -s` 와 `docker ps -q \| xargs docker inspect --format '{{.State.StartedAt}} {{.RestartCount}} {{.Name}}' \| sort` | 디스크가 먼저 마운트되고 모두 다시 `healthy` 다. 걸린 시간은 켠 시각과 마지막 `StartedAt` 의 차로 잰다(다시 붙은 때가 아니다) |
| 경보 | [VM] `docker compose stop db`, 2분 30초 뒤 위의 명령 | `PostgresDown` 과 서버마다의 `…DatabaseUnreachable` 일곱이 `firing`. `docker compose start db` 로 되돌리고 2분 뒤 그친다 |
| 로컬 백업 | [VM] `ls -la backups/` | `trpg-*.dump` 가 있다(`db-backup`) |
| 한 판 | 화면이 없으므로 순서서 9번의 운영자 계정으로 API 를 불러 본다(선택) | 서술이 집 PC 의 Ollama 로 나온다 |

## 9. 적는다

- 순서서에서 틀렸거나 빠진 것은 그 자리에서 [staging-vm.md](staging-vm.md)를 고치는 PR 로 올린다.
- 메모리와 연결의 바닥값, 다시 켜는 데 걸린 시간은 아래 "결과"와 이슈의 댓글에 남기고, [배포 설계의 열린 질문](../architecture/deployment.md#열린-질문)의 "실제 메모리 사용량"에 "로컬 VM 의 바닥값"으로 적는다. 클라우드 VM 의 값이 나오면 바꾼다.

## 결과 (2026-10-22)

`main` `8dddef0`, VMware Workstation 위의 Ubuntu 24.04.4(설치 뒤 24.04.5, 커널 6.8.0-147), 2코어, 8GB, 집 PC 의 Ollama 0.40.6.

| 무엇 | 값 |
| --- | --- |
| 뜨는가 | 모두 뜬다. 처음에는 `chat-migrate` 가 실패했다(아래 "찾은 것" 1) |
| 처음 빌드의 시간 | 적지 못했다. 다음에 `time` 의 `real` 을 적는다 |
| 메모리(바닥값, Grafana 를 열기 전) | 2.3Gi / 7.7Gi 를 쓰고 5.4Gi 가 남는다. 스왑 2MiB |
| 큰 것 | Grafana 451MiB(화면을 연 뒤 762MiB), Alloy 362MiB, Tempo 260MiB, Loki 179MiB, Prometheus 154MiB. 서버는 하나에 90~120MiB, Ollama(bge-m3) 173MiB |
| DB 의 연결(바닥값) | 합 17: game 5, auth 2, trpg 2, billing 2, notification·board·asset·chat·monitor 1. 몫의 합 80 의 5분의 1 |
| 기본 디스크 | 38G 가운데 26G. 이미지 16.2GB, 빌드 캐시 5.2GB(2.9GB 는 지울 수 있다), 볼륨 1.2GB |
| 데이터 디스크 | DB 68M, 관측 605M(띄운 지 한 시간 반) |
| 다시 켜기 | 켜고 11초 안에 모든 컨테이너가 시작했다. 다시 시작한 컨테이너는 없다. `db-backup` 만 DB 의 이름을 못 찾아 한 번 실패하고 60초 뒤에 떴다 |
| 경보 | 규칙 49. DB 를 멈추자 `PostgresDown` 과 `…DatabaseUnreachable` 일곱이 울리고, 되살리자 2분 안에 그쳤다 |
| 허용 주소 | 망을 바꾸자 `403`, `/healthz` 는 `ok` |
| 로컬 백업 | 처음 뜰 때와 다시 켠 뒤 `trpg-*.dump` 가 하나씩 |

**찾은 것**

1. `chat-migrate` 가 뜨지 못했다. `chat-server/.env` 에 `.env.example` 의 `ASSET_URL` 이 남는데, compose 가 마이그레이션에서 `ASSET_SECRET` 만 비워 "주소는 있고 비밀이 없다"로 설정의 검사에 걸렸다. compose 가 `ASSET_URL` 도 비우게 고쳤다. CI 의 stack 은 `.env` 를 따로 만들어 `ASSET_URL` 이 없어서 몰랐다. 그 `.env` 에도 `.env.example` 과 같은 `ASSET_URL` 을 넣었다.
2. 서버의 5xx 경보(`…ServerErrors`)가 DB 가 멈추자 일곱 모두 pending 이 됐다. 준비 상태 확인(`/health/ready`)의 503 이 5xx 로 세어지고, healthcheck(10초마다, 초당 0.1)만으로 "요청이 아주 적을 때"의 문턱(초당 0.05)을 넘는다. DB 가 10분 넘게 멈추면 같은 원인으로 경보가 일곱 더 울린다. 경보 규칙의 이슈로 따로 고친다.
3. `BoardNotificationRoundsFailing` 은 지난 15분의 실패를 보아 DB 를 되살린 뒤에도 15분 동안 울린다. 규칙대로다.
4. 순서서에서 고친 것: SSH 의 설정을 보는 `sshd -T` 가 24.04 에서 `/run/sshd` 를 요구한다, `findmnt` 에 경로 둘을 주면 아무것도 찍지 않는다, 사용자 이름을 `ubuntu` 로 박아 두었다, 관리자 화면의 터널이 집 PC 의 로컬 스택과 포트가 겹친다([staging VM 준비](staging-vm.md)).

## 끝나면

- VM 은 꺼 둔다. 순서서를 고친 뒤 다시 따라 해 볼 때 쓴다. 클라우드 VM 이 뜨면 지운다. 클라우드 VM 은 처음부터 다시 만든다(이 VM 의 `.env` 와 열쇠를 옮기지 않는다).
- **[집 PC]** Ollama 와 방화벽을 되돌린다(관리자 PowerShell). 그다음 시작 메뉴에서 Ollama 를 켜고 `netstat -ano | Select-String ":11434 "` 가 `127.0.0.1:11434` 인지 본다.

  ```powershell
  [Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "User")
  Remove-NetFirewallRule -DisplayName "Ollama for local VM"
  Get-Process ollama* -ErrorAction SilentlyContinue | Stop-Process -Force
  ```

- hosts 파일의 줄은 VM 을 다시 켤 때 쓴다. 지우려면 메모장을 관리자로 열어 지운다.
