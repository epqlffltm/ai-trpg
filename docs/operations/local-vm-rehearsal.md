# 로컬 VM 리허설

[staging VM 준비](staging-vm.md)의 순서서를 클라우드에 VM 을 빌리기 전에 집 PC 의 VM 에서 한 번 따라 해 본다. 순서서 그대로 따라 하고, 로컬이라 바꿔야 하는 곳만 여기에 적는다.

- 2026-10-22 에 정했다. 순서는 **로컬 VM 리허설 → 화면(#290) → 클라우드 VM(#491)** 이다([배포 설계](../architecture/deployment.md)의 머리).
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

**VMware Workstation Pro** 를 쓴다(개인 사용은 무료). Windows Pro 라면 Hyper-V 도 된다. WSL2 는 쓰지 않는다. 메모리 한도가 WSL 전체에 하나뿐이고, 디스크를 따로 붙이기 어렵고, Docker Desktop 과 엉킨다.

| 칸 | 값 | 까닭 |
| --- | --- | --- |
| OS | Ubuntu Server LTS(24.04) | 클라우드 VM 과 같다 |
| CPU, 메모리 | 2코어, 8GB | Lightsail 의 8GB 번들과 같다. 메모리를 재는 것이 목적이라 늘리지 않는다 |
| 기본 디스크 | 40GB | OS 와 Docker 의 이미지 |
| 디스크 둘을 더 | 16GB, 32GB | DB 와 관측(순서서의 "데이터 디스크 둘") |
| 네트워크 | NAT | 집 PC 에서 VM 의 주소로 닿고, VM 은 인터넷과 집 PC 에 닿는다 |

Ubuntu 를 설치할 때:

- 사용자 이름을 **`ubuntu`** 로 만든다. 순서서의 명령(`usermod -aG docker ubuntu`, `chown ubuntu:ubuntu`)이 그대로 돈다.
- **OpenSSH server** 를 고른다.
- 디스크 둘은 설치할 때 건드리지 않는다. 순서서 3번에서 포맷한다.

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

## 2. 순서서의 2, 3번은 그대로

VM 의 기본(SSH, 업데이트, 스왑), Docker, 데이터 디스크 둘을 [순서서](staging-vm.md)대로 한다. 다른 곳은 둘뿐이다.

- 붙을 때: `ssh ubuntu@<VM 주소>`
- 데이터 디스크의 장치 이름이 `nvme1n1` 이 아니라 `sdb`, `sdc` 일 수 있다. 순서서대로 `lsblk` 의 크기(16G, 32G)로 가린다.

## 3. 순서서의 4번(Tailscale)을 이것으로 바꾼다

Tailscale 을 쓰지 않는다. VM 이 집 PC 의 Ollama 에 NAT 망으로 닿는다.

**[집 PC]** Ollama 가 VMnet8 의 주소에서 듣게 하고, VMware 의 NAT 망에서 오는 11434 만 연다(관리자 PowerShell). 그다음 Ollama 를 껐다 켠다. 리허설이 끝나면 둘 다 되돌린다(아래 "끝나면").

```powershell
setx OLLAMA_HOST "<집 PC 의 VMnet8 주소>:11434"
New-NetFirewallRule -DisplayName "Ollama for local VM" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress <VMnet8 의 망, 예: 192.168.x.0/24> -Action Allow
```

**[VM]** 닿는지 본다. 모델 목록(JSON)이 나오면 된다.

```bash
curl -s http://<집 PC 의 VMnet8 주소>:11434/api/tags | head -c 300; echo
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
nano .env      # BACKUP_AWS_ACCESS_KEY_ID, BACKUP_AWS_SECRET_ACCESS_KEY, IMAGE_STORE_ACCESS_KEY_ID, IMAGE_STORE_SECRET_ACCESS_KEY 에 rehearsal-not-used
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
  'cp /src/privkey.pem /src/fullchain.pem /tls/ && chown 101:101 /tls/*.pem && chmod 600 /tls/privkey.pem && chmod 644 /tls/fullchain.pem'
rm -rf /tmp/selfsigned
```

## 7. 띄운다

순서서의 8번과 같고, 바깥 백업만 끈다.

```bash
cd /srv/ai-trpg
docker compose up -d --build --scale backup-offsite=0
docker compose ps -a
```

`*-migrate` 일곱과 `ollama-pull` 이 `Exited (0)`, 서버 일곱과 `proxy`, 워커들, `certbot`, `ollama`, `prometheus`, `grafana` 가 `healthy` 면 된다. `certbot` 의 갱신은 받은 인증서가 없어 아무것도 하지 않는다.

**[집 PC]** Grafana 와 관리자 화면은 SSH 터널로 연다. 띄워 둔 채 `http://localhost:3000`(Grafana), `http://localhost:8000/admin/`(인증 서버의 관리자 화면)을 연다.

```powershell
ssh -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 ubuntu@<VM 주소>
```

순서서의 9번(모델 목록과 운영자 계정)은 그대로 한다. 서술 모델은 집 PC 의 Ollama 에 있는 것을 넣는다.

## 8. 확인

순서서의 10번에서 클라우드에 기대는 줄(집 밖의 403, 인증서의 갱신, 바깥 백업, 주 열쇠로 풀기, Tailscale, 바깥의 감시)을 빼고, 리허설에서만 할 수 있는 것을 더한다.

| 무엇을 | 어떻게 | 되면 |
| --- | --- | --- |
| HTTPS 와 가동 확인 | [집 PC] `curl.exe -sk https://staging.ai-trpg.test/healthz` | `{"status":"ok"}`(자체 서명이라 `-k`) |
| 서버에 닿는다 | [집 PC] `curl.exe -sk -o NUL -w "%{http_code}" https://staging.ai-trpg.test/api/v1/game/me` | `401` |
| 허용 주소 밖은 막힌다 | [VM] `allow.conf` 의 줄을 다른 주소로 바꾸고 1분 기다린 뒤 위를 다시 | `403`. 줄을 되돌린다 |
| 컨테이너 | [VM] `docker compose ps -a` | 7번의 상태 |
| 메모리(바닥값) | [VM] 다 뜨고 10분 뒤 `free -h` 와 `docker stats --no-stream --format "{{.Name}} {{.MemUsage}}"` | 합과 큰 것 다섯을 적는다. 스왑을 쓰는지 본다 |
| DB 의 연결(바닥값) | [VM] `docker compose exec db psql -U trpg -d trpg -c "select usename, count(*) from pg_stat_activity group by 1 order by 2 desc"` | 계정마다의 수를 적는다. 몫(#592)의 합 80 과 견준다 |
| 데이터 디스크 | 순서서 10번의 `df -h` 두 줄 | 16G, 32G 디스크가 보인다 |
| 다시 켜기 | [VM] `sudo reboot`, 다시 붙어 `docker compose ps -a` | 디스크가 먼저 마운트되고 모두 다시 `healthy` 다. 걸린 시간을 적는다 |
| 경보 | [VM] `docker compose stop db`, 2분 뒤 Grafana 의 Alerting | `PostgresDown` 과 서버마다의 `…DatabaseUnreachable` 이 울린다. `docker compose start db` 로 되돌리고 그치는 것을 본다 |
| 로컬 백업 | [VM] `ls -la backups/` | `trpg-*.dump` 가 있다(`db-backup`) |
| 한 판 | 화면이 없으므로 순서서 9번의 운영자 계정으로 API 를 불러 본다(선택) | 서술이 집 PC 의 Ollama 로 나온다 |

## 9. 적는다

- 순서서에서 틀렸거나 빠진 것은 그 자리에서 [staging-vm.md](staging-vm.md)를 고치는 PR 로 올린다.
- 메모리와 연결의 바닥값, 다시 켜는 데 걸린 시간은 이슈에 댓글로 남기고, [배포 설계의 열린 질문](../architecture/deployment.md#열린-질문)의 "실제 메모리 사용량"에 "로컬 VM 의 바닥값"으로 적는다. 클라우드 VM 의 값이 나오면 바꾼다.

## 끝나면

- VM 은 지우거나 꺼 둔다. 클라우드 VM 은 처음부터 다시 만든다(이 VM 의 `.env` 와 열쇠를 옮기지 않는다).
- **[집 PC]** Ollama 와 방화벽을 되돌린다: `[Environment]::SetEnvironmentVariable("OLLAMA_HOST", $null, "User")` 그다음 Ollama 를 껐다 켜고, `Remove-NetFirewallRule -DisplayName "Ollama for local VM"`. hosts 파일의 줄도 지운다(메모장을 관리자로 열어).
