#!/usr/bin/env bash
# .github/scripts/stack-smoke.sh
#
# compose 로 모든 서버를 컨테이너로 띄워 보고 확인한다. 관문 워크플로(.github/workflows/ci.yml 의 stack)가 부른다.
#
#   사용: stack-smoke.sh prepare | up | check | check-proxy | logs | down
#     prepare      설정 파일(.env 여섯)과 JWT 키를 이 실행에서만 쓰고 버리는 값으로 만든다
#     up           이미지를 만들고 띄운 뒤, 서버들과 프록시, Prometheus, Alertmanager, Grafana, 상태 확인이 있는 워커가 healthy 가 되고
#                  Loki 가 준비될 때까지 기다린다.
#                  서버의 healthcheck 는 /health/ready 라서, healthy 는 그 서버가 DB 에 닿는다는 뜻이다.
#                  워커의 healthcheck 는 심장박동 파일이라서, healthy 는 그 워커가 DB 에 닿으며 돈다는 뜻이다.
#                  DB 의 백업은 최근 백업 파일이 있으면 healthy 다
#     check        마이그레이션이 성공했는지, 서버마다 준비됐는지(/health/ready), 서버끼리 닿는지, root 가 아닌지,
#                  이미지에 .env 가 없는지 본다. 비밀이 그것을 쓰는 프로세스에만 가는지(secret_scope.py),
#                  바깥에 여는 포트가 정해 둔 것뿐이고 127.0.0.1 에 묶였는지(port_scope.py),
#                  모든 서비스의 로그에 상한이 있는지도 본다(logging_scope.py, 띄운 컨테이너의 설정).
#                  워커와 cron 이 다시 뜨기를 되풀이하지 않고 돌고 있는지, crontab 의 명령이 한 번씩 성공하는지도 본다.
#                  로그 모으기(observability 프로필, #25)도 본다: 서버의 줄이 Loki 에 label 과 줄의 값으로 들어오는가,
#                  JSON 이 아닌 줄도 들어오는가, 식별자가 label 이 아닌가, Grafana 가 Loki 에 닿는가,
#                  소켓 프록시가 쓰기를 막는가, 서버들이 소켓 프록시와 Loki 에 닿지 않는가.
#                  메트릭도 본다: OTLP 로 민 시험 지표가 Prometheus 에 정한 이름과 label 로 들어오는가,
#                  수집 쪽 자신의 메트릭이 들어오는가, Prometheus 가 아무것도 긁지 않는가, Grafana 가 Prometheus 에 닿는가.
#                  대시보드도 본다: 규칙을 지키는가(dashboard_scope.py), Grafana 가 파일에서 읽었는가, 쿼리가 오류 없이 도는가.
#                  DB 와 Redis 의 메트릭이 들어오는가, 메트릭을 읽는 계정(monitor)이 표를 읽거나 쓰지 못하는가,
#                  Alloy 가 서버들의 망에 없는가.
#                  경보도 본다: 규칙의 시험(promtool)이 통과하는가, Prometheus 가 규칙을 읽고 Alertmanager 를 찾았는가,
#                  건강한 스택에서 울리는 경보가 없는가, 받는 곳 넷을 모두 적은 설정이 맞는가, 반쯤 적으면 뜨지 않는가,
#                  비밀이 설정 파일에 없는가. 받는 곳의 흉내(alert_sink.py)를 띄워 시험 경보가 Discord, Slack, Telegram 의
#                  모양으로 넘어가는지 본다(메일은 보내 보지 않는다)
#     check-proxy  프록시를 거쳐 본다: 서버마다 닿는가, 막을 주소를 막는가, 요청 식별자, 요청 수 제한,
#                  모든 응답(서버의 응답, 404, 429)의 보안 머리말, HTTP 의 응답에 HSTS 가 없는가.
#                  HTTP 로만 보므로 컨테이너 없이도 돈다. 주소는 PROXY, ADMIN 환경 변수로 바꾼다
#     check-staging  staging 의 설정(docker-compose.staging.yml, #451)을 본다. up 뒤에 부른다.
#                  두 파일을 겹친 설정에서 비밀의 범위, 바깥에 여는 포트(프록시의 80, 443 뿐), 로그 상한을 보고,
#                  staging 에만 있는 이미지의 태그가 있는지, 인증서의 남은 날짜 검사(docker/certbot)가 맞는지 본다.
#                  staging 의 프록시를 하나 더 띄워(자체 서명 인증서) HTTPS 로 본다: HTTP 를 넘기는가, 인증서의 확인 파일을
#                  내주는가, 허용 주소 밖을 막는가, 허용 주소를 고치면 다시 읽는가, HSTS 와 보안 머리말.
#                  바깥 백업(backup-offsite)도 본다: S3 흉내(moto)를 띄워 백업을 암호화해 올리고, 확인 열쇠와 주 열쇠로
#                  풀어 빈 DB 에 풀리는가, 받는 쪽이 아닌 열쇠로는 풀리지 않는가, 실패하면 곧바로 unhealthy 인가
#     logs         모든 컨테이너의 로그를 찍는다. 실패했을 때 부른다
#     down         컨테이너와 볼륨을 지운다(check 가 띄운 받는 곳의 흉내, check-staging 이 띄운 프록시, S3 흉내, 허용 주소의 파일과 열쇠도)
#
# 서버의 기능은 보지 않는다. 그것은 서버마다의 CI 가 한다. 여기서는 "이미지가 만들어지고, 마이그레이션이 돌고,
# 서버가 뜨고, 서로 닿는가"만 본다.
#
# PC 에서 부르지 않는다. prepare 는 CI 가 아니면 멈춘다. 있는 .env 는 덮어쓰지 않는다.

set -euo pipefail

SERVERS=(auth game board billing notification)
# 서버마다 컨테이너 안에서 듣는 포트
declare -A PORTS=([auth]=8000 [game]=8001 [board]=8002 [billing]=8003 [notification]=8004)
# 계속 도는 워커와 주기 명령의 컨테이너
WORKERS=(auth-mail auth-welcome-credits auth-cron billing-sweeper billing-cron db-backup)
# 그 가운데 상태 확인이 있는 워커. 심장박동(docker-compose.yml 의 x-worker-heartbeat)을 보거나, DB 의 백업은 최근 백업 파일을 본다
HEARTBEAT_WORKERS=(auth-mail auth-welcome-credits billing-sweeper db-backup)
# 서명 개인키를 받지 않는 인증의 프로세스(#274). 키 폴더는 auth-server 에만 붙는다
KEYLESS=(auth-migrate auth-mail auth-welcome-credits auth-cron)
# 주기 명령의 컨테이너와 그 crontab
CRONTABS=(auth-cron:docker/cron/auth.crontab billing-cron:docker/cron/billing.crontab)
# 프록시의 주소와, 관리자 화면 때문에 따로 연 인증 서버의 주소
PROXY="${PROXY:-http://127.0.0.1:8080}"
ADMIN="${ADMIN:-http://127.0.0.1:8000}"
# 서버가 healthy 가 되기를 기다리는 시간(초)
WAIT_SECONDS=180
# 남긴 줄이 Loki 에서 찾아지기를 기다리는 시간(초). Alloy 는 15초마다 컨테이너를 찾고, 줄을 묶어 보낸다
LOG_WAIT_SECONDS=60
# Grafana 의 주소. 바깥(이 PC)에서 연 포트다
GRAFANA="${GRAFANA:-http://127.0.0.1:3000}"
# 서버마다의 대시보드(JSON)가 든 폴더. Grafana 가 파일로 읽는다(docker/grafana/provisioning/dashboards)
DASHBOARDS=docker/grafana/dashboards
# Loki 의 label 로 쓰는 것(docs/observability.md 의 "Loki 의 label"). 이것 말고는 label 이 없어야 한다
LOKI_LABELS=(container environment level mode service)
# 메트릭을 OTLP 로 미는 서버(docs/observability.md 의 "2. 메트릭"). 서버에 메트릭을 붙이면 여기에 더한다.
# 그 서버의 요청 수, DB 의 상태, 연결 풀이 Prometheus 에 있는지 본다
METRIC_SERVERS=(billing)
# 서버의 망 밖(소켓 프록시와 Loki 의 망)에서 주소를 부를 때 잠깐 띄우는 이미지. compose 의 redis 와 같아 이미 받아 두었다.
# 그 안의 busybox wget 을 쓴다
PROBE_IMAGE=redis:7-alpine
# 경보를 받는 곳(Discord, Slack, Telegram)의 흉내. check 가 observability 망에 띄운다(.github/scripts/alert_sink.py).
# prepare 가 루트 .env 의 ALERT_* 를 이 주소로 적는다. 파이썬 이미지는 바깥 백업의 S3 흉내와 같은 것이다
ALERT_SINK=alert-sink
ALERT_SINK_IMAGE=python:3.13-slim-trixie
# 받는 곳이 받았는지 볼 경로(정규식). Alertmanager 가 Telegram 의 주소 뒤에 /bot<토큰>/sendMessage 를 붙인다
ALERT_PATHS=(/discord /slack '/telegram/bot[^/]+/sendMessage')
# 컨테이너의 사용자. Dockerfile 에서 정한 번호다. 노드 이미지는 제 사용자(node, 1000)를 쓴다
APP_UID=10001
# staging 의 설정을 볼 때 루트 .env 대신 주는 값(진짜 도메인과 주소가 아니다). 두 파일을 겹친다
STAGING_DOMAIN=staging.test
STAGING_FILES=(-f docker-compose.yml -f docker-compose.staging.yml)
# check-staging 이 띄우는 staging 의 프록시. 로컬의 프록시(8080)와 겹치지 않는 포트로 이 PC 에만 연다
STAGING_PROXY=staging-proxy
STAGING_HTTP=http://127.0.0.1:18080
STAGING_HTTPS="https://$STAGING_DOMAIN:18443"
# 그 프록시에 CI 가 잠깐 두는 허용 주소. 이름이 *.conf 라 git 에 올라가지 않는다(.gitignore)
STAGING_ALLOWLIST=docker/nginx/allowlist/ci-stack-smoke.conf
# 바깥 백업(backup-offsite)을 볼 때 띄우는 S3 흉내(moto). 서버의 이미지와 같은 파이썬 이미지에 설치해 띄운다
STAGING_S3=staging-s3
STAGING_S3_IMAGE=python:3.13-slim-trixie
MOTO_VERSION=5.2.4
STAGING_BUCKET=ci-backups
# 바깥 백업의 확인 열쇠를 두는 폴더(docker-compose.staging.yml 이 붙인다). git 에 올라가지 않는다(.gitignore)
STAGING_KEYS=backup-keys
# 바깥 백업의 받는 쪽 열쇠(age 의 공개키 둘). 설정을 읽기만 할 때는 아무 값이나 되고, 바깥 백업을 볼 때 실제 열쇠로 바꾼다
staging_recipients="age1ci age1ci"

# 서버들(app)과 로그와 메트릭 모으기(observability)를 함께 띄운다
compose() {
  docker compose --profile app --profile observability "$@"
}

# staging 의 설정(두 파일을 겹친 것). VM 의 루트 .env 에 적을 값을 이 실행에서만 준다
staging_compose() {
  DOMAIN="$STAGING_DOMAIN" ACME_EMAIL=ci@example.com GAME_LLM_BASE_URL=http://100.64.0.1:11434/v1 \
    BACKUP_S3_BUCKET="$STAGING_BUCKET" BACKUP_S3_ENDPOINT="http://$STAGING_S3:5000" \
    BACKUP_AWS_ACCESS_KEY_ID=ci BACKUP_AWS_SECRET_ACCESS_KEY=ci BACKUP_AGE_RECIPIENTS="$staging_recipients" \
    docker compose "${STAGING_FILES[@]}" --profile app --profile observability "$@"
}

# 이 실행에서만 쓰는 비밀. 48자라 서버들이 요구하는 길이(32자 이상)를 넘는다
throwaway() {
  openssl rand -hex 24
}

# 표준 입력을 새 파일로 쓴다. 파일이 이미 있으면 쓰지 않고 실패한다.
write_new() {
  local path="$1"
  if [[ -e "$path" ]]; then
    echo "$path 가 이미 있다. 덮어쓰지 않는다" >&2
    return 1
  fi
  cat > "$path"
}

# 여섯 개의 .env 를 만든다. 주소는 compose 가 덮어쓰므로 비밀만 적는다.
# 서버끼리 함께 아는 비밀은 두 파일에 같은 값을 넣는다(결제 서버와 게임 서버, 결제 서버와 인증 서버,
# 알림 서버와 게임·결제·게시판 서버)
write_env_files() {
  local game_secret auth_secret notify_secret billing_notify_secret board_notify_secret
  game_secret="$(throwaway)"
  auth_secret="$(throwaway)"
  notify_secret="$(throwaway)"
  billing_notify_secret="$(throwaway)"
  board_notify_secret="$(throwaway)"
  write_new .env <<EOF
POSTGRES_PASSWORD=$(throwaway)
AUTH_DB_PASSWORD=$(throwaway)
GAME_DB_PASSWORD=$(throwaway)
BILLING_DB_PASSWORD=$(throwaway)
BOARD_DB_PASSWORD=$(throwaway)
NOTIFICATION_DB_PASSWORD=$(throwaway)
GRAFANA_ADMIN_PASSWORD=$(throwaway)
MONITOR_DB_PASSWORD=$(throwaway)
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318
ALERT_DISCORD_WEBHOOK_URL=http://$ALERT_SINK:8080/discord
ALERT_SLACK_WEBHOOK_URL=http://$ALERT_SINK:8080/slack
ALERT_TELEGRAM_BOT_TOKEN=$(throwaway)
ALERT_TELEGRAM_CHAT_ID=-1001
ALERT_TELEGRAM_API_URL=http://$ALERT_SINK:8080/telegram
EOF
  write_new auth-server/.env <<EOF
SECRET_KEY=$(throwaway)
BILLING_SECRET=$auth_secret
EOF
  write_new game-server/.env <<EOF
BILLING_SECRET=$game_secret
NOTIFICATION_SECRET=$notify_secret
EOF
  write_new board-server/.env <<EOF
NOTIFICATION_SECRET=$board_notify_secret
EOF
  write_new billing-server/.env <<EOF
PG_WEBHOOK_SECRET=$(throwaway)
GAME_SERVER_SECRET=$game_secret
AUTH_SERVER_SECRET=$auth_secret
NOTIFICATION_SECRET=$billing_notify_secret
EOF
  write_new notification-server/.env <<EOF
GAME_SERVER_SECRET=$notify_secret
BILLING_SERVER_SECRET=$billing_notify_secret
BOARD_SERVER_SECRET=$board_notify_secret
EOF
}

# JWT 개인키를 만든다. 주인만 읽게 두고 주인을 컨테이너의 사용자로 바꾼다.
# 리눅스에서 키 폴더를 컨테이너에 붙일 때 해야 하는 일과 같다(README 의 "모든 서버를 컨테이너로")
write_jwt_key() {
  local key=auth-server/keys/jwt-private.pem
  mkdir -p auth-server/keys
  if [[ -e "$key" ]]; then
    echo "$key 가 이미 있다. 덮어쓰지 않는다" >&2
    return 1
  fi
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key" 2>/dev/null
  chmod 600 "$key"
  sudo chown "$APP_UID" "$key"
}

prepare() {
  if [[ "${CI:-}" != "true" ]]; then
    echo "CI 에서만 부른다. PC 의 .env 와 키를 건드리지 않는다" >&2
    return 1
  fi
  write_env_files
  write_jwt_key
}

# 한 서비스의 컨테이너 번호. 끝난 컨테이너(마이그레이션)도 찾는다
container_of() {
  compose ps -a -q "$1"
}

# 컨테이너의 상태 확인 결과. healthy, starting, unhealthy 가운데 하나다
health_of() {
  docker inspect -f '{{.State.Health.Status}}' "$(container_of "$1")"
}

# 컨테이너의 상태 확인이 healthy 인가
is_healthy() {
  [[ "$(health_of "$1")" == "healthy" ]]
}

# 컨테이너가 아직 돌고 있는가
running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$(container_of "$1")")" == "true" ]]
}

# 서버들과 프록시, Prometheus, Alertmanager, Grafana, 심장박동을 알리는 워커가 모두 healthy 가 될 때까지 기다린다. 하나라도 죽거나 시간이 지나면 실패한다.
wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS)) service pending
  while ((SECONDS < deadline)); do
    pending=0
    for service in "${SERVERS[@]/%/-server}" proxy prometheus alertmanager grafana "${HEARTBEAT_WORKERS[@]}"; do
      if ! running "$service"; then
        echo "$service 가 죽었다" >&2
        return 1
      fi
      [[ "$(health_of "$service")" == "healthy" ]] || pending=$((pending + 1))
    done
    if ((pending == 0)); then
      echo "서버들과 프록시, Prometheus, Alertmanager, Grafana, 상태 확인이 있는 워커가 healthy 다"
      return 0
    fi
    sleep 3
  done
  echo "${WAIT_SECONDS}초 안에 healthy 가 되지 않았다" >&2
  return 1
}

# Loki 가 요청을 받을 때까지 기다린다. Loki 의 이미지에는 상태를 물을 도구가 없어 healthcheck 가 없다.
# 뜬 뒤 15초쯤은 503 이다(받을 준비를 한다)
wait_loki_ready() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  while ((SECONDS < deadline)); do
    if [[ "$(fetch_on observability http://loki:3100/ready 2>/dev/null)" == "ready" ]]; then
      echo "Loki 가 준비됐다"
      return 0
    fi
    sleep 3
  done
  echo "${WAIT_SECONDS}초 안에 Loki 가 준비되지 않았다" >&2
  return 1
}

up() {
  compose up -d --build
  wait_healthy
  wait_loki_ready
}

# 결과를 한 줄 찍고, 실패면 세어 둔다
failures=0
report() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok   $name"
  else
    echo "FAIL $name"
    failures=$((failures + 1))
  fi
}

migrated() {
  [[ "$(docker inspect -f '{{.State.ExitCode}}' "$(container_of "$1-migrate")")" == "0" ]]
}

# 바깥(이 PC)에서 연 포트로 닿는가
reachable_from_host() {
  curl -fsS -o /dev/null --max-time 5 "$1"
}

# 주소의 답이 이 상태 코드인가. 셋째 인자부터는 curl 에 그대로 넘긴다
status_is() {
  local expected="$1" url="$2"; shift 2
  [[ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$@" "$url")" == "$expected" ]]
}

# 프록시를 거친 응답에 X-Request-ID 가 하나만 있고, 클라이언트가 보낸 값이 아닌가
one_request_id_from_proxy() {
  local headers
  headers="$(curl -s -D - -o /dev/null --max-time 5 -H 'X-Request-ID: client-chosen-0001' "$PROXY/api/v1/auth/jwks")"
  [[ "$(grep -ci '^x-request-id:' <<<"$headers")" == "1" ]] && ! grep -qi 'client-chosen-0001' <<<"$headers"
}

# 머리말 목록에 그 머리말이 한 번만 있고 값이 이것인가. 이름의 대소문자는 가리지 않는다
one_header() {
  local headers="$1" name="$2" value="$3"
  [[ "$(grep -ci "^$name:" <<<"$headers")" == "1" ]] && grep -qixF "$name: $value" <<<"$headers"
}

# 프록시를 거친 응답에 보안 머리말 셋이 하나씩, 정한 값으로 붙었는가(#361). 둘째 인자부터는 curl 에 넘긴다.
# 서버가 같은 머리말을 보내도(인증 서버의 nosniff 등) 하나만 있어야 한다
security_headers() {
  local url="$1" headers; shift
  headers="$(curl -s -D - -o /dev/null --max-time 5 "$@" "$url" | tr -d '\r')"
  one_header "$headers" X-Content-Type-Options nosniff &&
    one_header "$headers" Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" &&
    one_header "$headers" Referrer-Policy no-referrer
}

# 같은 주소를 count 번 부른 뒤 한 번 더 부르면 429 와 Retry-After(초)가 오는가. 넷째 인자부터는 curl 에 넘긴다
limited_after() {
  local count="$1" url="$2" retry_after="$3" headers i; shift 3
  for ((i = 0; i < count; i++)); do
    curl -s -o /dev/null --max-time 5 "$@" "$url"
  done
  headers="$(curl -s -D - -o /dev/null --max-time 5 "$@" "$url")"
  grep -q '^HTTP/[0-9.]* 429' <<<"$headers" && grep -qi "^retry-after: ${retry_after}" <<<"$headers"
}

# 한 컨테이너 안에서 다른 컨테이너의 주소로 닿는가. 이미지마다 들어 있는 도구가 달라서 셋으로 나눈다
reachable_from() {
  local service="$1" url="$2"
  case "$service" in
    auth-server | game-server | notification-server)
      compose exec -T "$service" python -c "import urllib.request; urllib.request.urlopen('$url', timeout=5)" ;;
    board-server)
      compose exec -T "$service" node -e "fetch('$url').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))" ;;
    billing-server | billing-sweeper)
      compose exec -T "$service" wget -q -O /dev/null "$url" ;;
  esac
}

# 게임 서버가 제 설정(NOTIFICATION_URL, NOTIFICATION_SECRET)으로 서명한 알림을 알림 서버가 받는가(201).
# 닿기만 하고 서명이 어긋나면(두 .env 의 비밀이 다르다) 알림이 발송함에 쌓이기만 한다. 그것을 여기서 잡는다.
# 받는 사람은 이 실행에서만 쓰는 무작위 값이다. 알림 서버는 서버마다 넣을 수 있는 kind 를 정해 두었으므로
# 게임 서버의 kind 중 값이 필요 없는 것(publishing.unbanned)으로 보낸다(notification-server/app/notifications/catalog.py)
game_notification_accepted() {
  compose exec -T game-server python - <<'PY'
import asyncio
import uuid

import httpx

from app.core.config import get_settings
from app.notifications.client import Delivery
from app.notifications.models import OutgoingNotification
from app.notifications.setup import build_notifications


async def main() -> None:
    async with httpx.AsyncClient() as client:
        notifications = build_notifications(get_settings(), client)
        notification = OutgoingNotification(
            source_key=f'stack-smoke:{uuid.uuid4()}', user_id=uuid.uuid4(), kind='publishing.unbanned', payload={}
        )
        sent = await notifications.send(notification)
    raise SystemExit(0 if sent.delivery == Delivery.DELIVERED else 1)


asyncio.run(main())
PY
}

# 게시판 서버가 제 설정(NOTIFICATION_URL, NOTIFICATION_SECRET)으로 서명한 알림을 알림 서버가 받는가(201).
# 게임 서버의 것과 같다. 서버가 쓰는 코드(dist/notifications)를 그대로 불러 보낸다.
# 게시판의 kind(post.commented)에 화면이 쓰는 칸을 채워 보낸다
board_notification_accepted() {
  compose exec -T board-server node --input-type=module -e "
import { randomUUID } from 'node:crypto';
import { HttpNotificationSender } from './dist/notifications/notification-client.js';
const sender = new HttpNotificationSender(process.env.NOTIFICATION_URL, process.env.NOTIFICATION_SECRET);
const payload = { board_slug: 'free', post_id: '1', post_title: 'stack-smoke', comment_id: '1' };
const sent = await sender.send({ sourceKey: 'stack-smoke:' + randomUUID(), userId: randomUUID(), kind: 'post.commented', payload });
process.exit(sent.delivery === 'delivered' ? 0 : 1);
"
}

# 서버가 제 컨테이너 안에서 준비됐다고(/health/ready 가 200) 답하는가. 503 이면 실패다
ready_inside() {
  local server="$1"
  reachable_from "${server}-server" "http://127.0.0.1:${PORTS[$server]}/health/ready"
}

# 돌고 있고, 한 번도 다시 뜨지 않았는가. 바로 죽는 워커는 restart 때문에 돌고 있는 것처럼 보인다
stays_up() {
  running "$1" && [[ "$(docker inspect -f '{{.RestartCount}}' "$(container_of "$1")")" == "0" ]]
}

# 컨테이너에 붙인 crontab 의 문법이 맞는가
crontab_valid() {
  compose exec -T "$1" supercronic -test /etc/supercronic/crontab
}

# crontab 의 명령들. 주석과 빈 줄을 빼고, 앞의 시각 다섯 칸을 뗀다
crontab_commands() {
  grep -vE '^[[:space:]]*(#|$)' "$1" | awk '{ $1 = $2 = $3 = $4 = $5 = ""; sub(/^ +/, ""); print }'
}

# 명령 하나를 그 컨테이너에서 지금 한 번 돌려 성공하는가. cron 이 부를 때와 같이 /bin/sh 로 돈다
runs_once() {
  compose exec -T "$1" sh -c "$2"
}

# 인증 서버의 DB 계정에 테스트용 DB 를 만들 권한(CREATEDB)이 없는가. compose 의 기본은 주지 않는 것이다(#20)
auth_cannot_create_databases() {
  local sql="SELECT rolcreatedb FROM pg_roles WHERE rolname = 'auth'"
  # 관리 계정과 DB 의 이름은 db 컨테이너 안의 환경 변수로 읽는다. 그래서 작은따옴표로 넘겨 그 안에서 펼친다
  # shellcheck disable=SC2016
  [[ "$(compose exec -T -e SQL="$sql" db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$SQL"')" == "f" ]]
}

not_root() {
  [[ "$(compose exec -T "$1" id -u)" != "0" ]]
}

no_env_file_in_image() {
  compose exec -T "$1" test ! -e /app/.env
}

# 설정을 보는 검사(secret_scope.py, port_scope.py, logging_scope.py, dashboard_scope.py)의 규칙이 맞는가.
# 규칙이 틀리면 새는 것을 놓치고 초록이 된다. .env 를 만들고 비밀을 채우는 도구(tools/fill_env.py)의 테스트도 함께 돌린다
scope_rules_hold() {
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -p 'test_*_scope.py' &&
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_fill_env.py'
}

# 지금의 DB 를 뜨고, 그 백업을 같은 DB 서버의 빈 DB 에 풀어 표마다 줄 수가 같은지 본다(docker/backup/db-backup.sh).
# 처음 뜬 백업은 마이그레이션이 끝나기 전의 것일 수 있다. 그래서 마이그레이션이 끝난 지금 다시 뜬다
backup_restores() {
  compose exec -T db-backup sh /usr/local/bin/db-backup.sh once &&
    compose exec -T db-backup sh /usr/local/bin/db-backup.sh check
}

# 백업 파일을 주인만 읽는가. 이메일, 비밀번호 해시, 결제 원장이 들어 있다
backup_private() {
  [[ -z "$(compose exec -T db-backup find /backups -maxdepth 1 -name 'trpg-*.dump' ! -perm 600)" ]]
}

# --- 로그 모으기(observability 프로필) ---

# compose 의 망의 이름. compose 는 망의 이름 앞에 프로젝트의 이름을 붙인다(<프로젝트>_observability)
network_of() {
  local project
  project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$(container_of loki)")"
  echo "${project}_$1"
}

# 그 망에 잠깐 붙인 컨테이너에서 주소를 GET 하고 본문을 찍는다. 셋째 인자부터는 wget 에 넘긴다.
# 소켓 프록시와 Loki 는 서버의 망에 없어서 서버의 컨테이너에서는 부를 수 없다
fetch_on() {
  local network="$1" url="$2"; shift 2
  docker run --rm --network "$(network_of "$network")" "$PROBE_IMAGE" wget -q -O - "$@" "$url"
}

# LogQL 을 주소에 넣을 수 있게 바꾼다
urlencode() {
  python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

# 지난 한 시간의 줄에서 이 LogQL 에 맞는 것이 하나라도 있는가
loki_finds() {
  fetch_on observability "http://loki:3100/loki/api/v1/query_range?limit=1&query=$(urlencode "$1")" |
    python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin)["data"]["result"] else 1)'
}

# 될 때까지 몇 번 해 본다. 줄은 남긴 뒤 몇 초 지나야 Loki 에서 찾아진다
eventually() {
  local deadline=$((SECONDS + LOG_WAIT_SECONDS))
  until "$@"; do
    ((SECONDS < deadline)) || return 1
    sleep 3
  done
}

# Loki 의 label 이 정해 둔 것(LOKI_LABELS)뿐이고, service 와 container 가 있는가.
# 식별자(request_id, trace_id, job_id)가 label 이 되면 줄마다 저장 단위가 생긴다.
# 실패하면 Loki 에 있는 label 을 찍는다
loki_labels_are_listed() {
  fetch_on observability http://loki:3100/loki/api/v1/labels | python3 -c '
import json, sys
labels = set(json.load(sys.stdin)["data"])
if not {"service", "container"} <= labels <= set(sys.argv[1:]):
    print("Loki 의 label:", ", ".join(sorted(labels)))
    sys.exit(1)
' "${LOKI_LABELS[@]}"
}

# label 의 검사를 돌려 결과를 찍는다. 실패하면 무엇이 있었는지 함께 찍는다(check_config 와 같은 모양)
check_loki_labels() {
  local name="Loki 의 label 은 정해 둔 것뿐이다(식별자는 label 이 아니다)" problems
  if problems="$(loki_labels_are_listed 2>&1)"; then
    echo "ok   $name"
  else
    echo "FAIL $name"
    sed 's/^/     /' <<<"$problems"
    failures=$((failures + 1))
  fi
}

# 이 추적 식별자를 실어 인증 서버를 한 번 부른다. 인증 서버는 받은 traceparent 를 이어 써서 그 줄에 trace_id 로 싣는다
call_auth_with_trace() {
  curl -fsS -o /dev/null --max-time 5 -H "traceparent: 00-$1-$(openssl rand -hex 8)-01" "$ADMIN/api/v1/auth/jwks"
}

# Grafana 의 관리자 비밀번호. prepare 가 루트 .env 에 적었다
grafana_password() {
  sed -n 's/^GRAFANA_ADMIN_PASSWORD=//p' .env
}

# Grafana 가 그 데이터 소스(uid loki, prometheus)로 저장소에 닿는가
grafana_reaches() {
  status_is 200 "$GRAFANA/api/datasources/uid/$1/health" -u "admin:$(grafana_password)"
}

# 소켓 프록시가 이 주소를 넘기는가(200)
socket_proxy_allows() {
  fetch_on docker-api "http://docker-socket-proxy:2375$1" >/dev/null
}

# 소켓 프록시가 이 요청을 403 으로 막는가. 둘째 인자부터는 wget 에 넘긴다.
# 닿지 않아서 실패한 것과 가르려고 403 인지까지 본다. wget 은 그 상태를 오류 출력에 찍고 실패로 끝난다
socket_proxy_refuses() {
  local path="$1" errors; shift
  errors="$(fetch_on docker-api "http://docker-socket-proxy:2375$path" "$@" 2>&1 >/dev/null)" || true
  [[ "$errors" == *" 403 "* ]]
}

# 한 컨테이너 안에서 다른 컨테이너의 주소로 닿지 않는가
unreachable_from() {
  ! reachable_from "$@"
}

# 로그 모으기를 본다. 앞의 확인들이 서버에 남긴 줄이 Loki 에 들어와 있다
check_logs() {
  local trace
  trace="$(openssl rand -hex 16)"
  report "alloy 가 root 가 아니다" not_root alloy
  report "grafana 가 root 가 아니다" not_root grafana
  report "Alloy 와 Loki, 소켓 프록시가 다시 뜨지 않고 돈다" stays_up_all alloy loki docker-socket-proxy
  report "Grafana 가 Loki 에 닿는다(데이터 소스 loki)" grafana_reaches loki
  report "추적 식별자를 실어 인증 서버를 부른다" call_auth_with_trace "$trace"
  report "서버의 줄을 service, container, level 의 label 로 찾는다" \
    eventually loki_finds '{service="auth-server", container="auth-server", level="info"}'
  report "서버의 줄을 줄의 값 trace_id 로 거른다" \
    eventually loki_finds "{service=\"auth-server\"} | trace_id=\"$trace\""
  report "JSON 이 아닌 줄(DB)도 들어온다" eventually loki_finds '{container="db"} | log_format="other"'
  check_loki_labels
  report "소켓 프록시가 컨테이너 목록을 넘긴다" socket_proxy_allows /containers/json
  report "소켓 프록시가 컨테이너 만들기(POST)를 막는다" socket_proxy_refuses /containers/create \
    --post-data '{}' --header 'Content-Type: application/json'
  report "소켓 프록시가 이미지 목록을 막는다" socket_proxy_refuses /images/json
  report "게임 서버가 소켓 프록시에 닿지 않는다" unreachable_from game-server http://docker-socket-proxy:2375/version
  report "게임 서버가 Loki 에 닿지 않는다" unreachable_from game-server http://loki:3100/ready
  report "결제 서버가 Loki 에 닿지 않는다" unreachable_from billing-server http://loki:3100/ready
}

# --- 메트릭(observability 프로필) ---

# PromQL 의 지금 값에 맞는 시계열이 하나라도 있는가
prometheus_finds() {
  fetch_on observability "http://prometheus:9090/api/v1/query?query=$(urlencode "$1")" |
    python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin)["data"]["result"] else 1)'
}

# Prometheus 가 긁는 대상이 하나도 없는가. 받기만 해야 저장소를 Mimir 로 바꿀 때 Alloy 의 주소만 바뀐다
prometheus_scrapes_nothing() {
  fetch_on observability http://prometheus:9090/api/v1/targets |
    python3 -c 'import json, sys; sys.exit(0 if not json.load(sys.stdin)["data"]["activeTargets"] else 1)'
}

# 서버가 미는 것과 같은 길로 시험 지표 하나를 민다. telemetry 망에서 Alloy 의 OTLP(HTTP, JSON)로 보낸다.
# 쌓이는 수(counter) stack_smoke_probe 하나다. 단위가 없어 Prometheus 에서는 stack_smoke_probe_total 이 된다
push_probe_metric() {
  local instance="$1" now body
  now="$(date +%s%N)"
  body="$(printf '{"resourceMetrics":[{"resource":{"attributes":[%s,%s]},"scopeMetrics":[{"scope":{"name":"stack-smoke"},"metrics":[{"name":"stack_smoke_probe","sum":{"aggregationTemporality":2,"isMonotonic":true,"dataPoints":[{"asInt":"1","startTimeUnixNano":"%s","timeUnixNano":"%s"}]}}]}]}]}' \
    '{"key":"service.name","value":{"stringValue":"stack-smoke"}}' \
    "{\"key\":\"service.instance.id\",\"value\":{\"stringValue\":\"$instance\"}}" "$now" "$now")"
  fetch_on telemetry http://alloy:4318/v1/metrics --post-data "$body" --header 'Content-Type: application/json' >/dev/null
}

# DB 의 메트릭을 읽는 계정(monitor)의 비밀번호. prepare 가 루트 .env 에 적었다
monitor_password() {
  sed -n 's/^MONITOR_DB_PASSWORD=//p' .env
}

# monitor 계정으로 SQL 하나를 돌린다. 비밀번호로 붙도록 소켓이 아니라 127.0.0.1 로 붙는다.
# DB 의 이름은 db 컨테이너 안의 환경 변수로 읽는다. 그래서 작은따옴표로 넘겨 그 안에서 펼친다
monitor_query() {
  # shellcheck disable=SC2016
  compose exec -T -e PGPASSWORD="$(monitor_password)" -e SQL="$1" db \
    sh -c 'psql -h 127.0.0.1 -U monitor -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -Atc "$SQL"'
}

# monitor 계정이 붙어서 통계를 읽는가
monitor_reads_statistics() {
  [[ "$(monitor_query 'SELECT count(*) > 0 FROM pg_stat_database')" == "t" ]]
}

# monitor 계정이 서버의 표를 읽지 못하는가. 붙지 못해서 실패한 것과 가르려고 먼저 통계를 읽는다
monitor_cannot_read_tables() {
  monitor_reads_statistics && ! monitor_query 'SELECT 1 FROM billing.wallets LIMIT 1'
}

# monitor 계정이 쓰지 못하는가(default_transaction_read_only)
monitor_cannot_write() {
  monitor_reads_statistics && ! monitor_query 'CREATE TABLE public.monitor_probe (id integer)'
}

# Alloy 가 서버들의 망(<프로젝트>_default)에 없는가. 있으면 모든 서버의 API 를 부를 수 있다
alloy_off_server_network() {
  local networks
  networks="$(docker inspect -f '{{range $name, $network := .NetworkSettings.Networks}}{{$name}} {{end}}' "$(container_of alloy)")"
  [[ -n "$networks" && " $networks" != *"_default "* ]]
}

# 메트릭을 본다
check_metrics() {
  local instance job
  instance="$(openssl rand -hex 8)"
  report "prometheus 가 root 가 아니다" not_root prometheus
  report "Prometheus 가 다시 뜨지 않고 돈다" stays_up prometheus
  report "Grafana 가 Prometheus 에 닿는다(데이터 소스 prometheus)" grafana_reaches prometheus
  report "Prometheus 는 아무것도 긁지 않는다(받기만 한다)" prometheus_scrapes_nothing
  report "시험 지표를 OTLP 로 Alloy 에 민다(telemetry 망)" push_probe_metric "$instance"
  report "민 지표가 정한 이름(_total)과 label service, instance 로 Prometheus 에 들어온다" \
    eventually prometheus_finds "stack_smoke_probe_total{service=\"stack-smoke\", instance=\"$instance\"} == 1"
  for job in alloy loki prometheus alertmanager grafana; do
    report "Alloy 가 $job 의 메트릭을 긁어 보낸다" eventually prometheus_finds "up{job=\"$job\"} == 1"
  done
  report "Alloy 가 DB 의 메트릭을 monitor 계정으로 읽는다(pg_up == 1)" \
    eventually prometheus_finds 'pg_up{job="postgres", instance="db"} == 1'
  report "Alloy 가 Redis 의 메트릭을 읽는다(redis_up == 1)" \
    eventually prometheus_finds 'redis_up{job="redis", instance="redis"} == 1'
  report "monitor 계정은 서버의 표를 읽지 못한다" monitor_cannot_read_tables
  report "monitor 계정은 쓰지 못한다(읽기 전용)" monitor_cannot_write
  report "Alloy 가 서버들의 망(default)에 없다. DB 와 Redis 에는 datastore-metrics 로만 닿는다" alloy_off_server_network
  report "게임 서버가 Prometheus 에 닿지 않는다" unreachable_from game-server http://prometheus:9090/-/ready
  report "결제 서버가 Prometheus 에 닿지 않는다(telemetry 망에서는 Alloy 에만 닿는다)" \
    unreachable_from billing-server http://prometheus:9090/-/ready
  check_server_metrics
  check_dashboards
}

# 서버가 민 메트릭이 정한 이름과 label 로 들어오는지 본다. 서버의 프로세스는 label instance 의 앞부분으로 가른다
check_server_metrics() {
  local server service
  for server in "${METRIC_SERVERS[@]}"; do
    service="${server}-server"
    report "$service 의 요청 수가 들어온다(http_server_requests_total, instance=server-…)" \
      eventually prometheus_finds "http_server_requests_total{service=\"$service\", route=\"/health/ready\", instance=~\"server-.+\"}"
    report "$service 의 요청 시간이 초로 들어온다(http_server_request_duration_seconds)" \
      eventually prometheus_finds "http_server_request_duration_seconds_count{service=\"$service\"}"
    report "$service 가 DB 에 닿는다고 적었다(db_up == 1)" eventually prometheus_finds "db_up{service=\"$service\"} == 1"
    report "$service 의 연결 풀이 들어온다(db_pool_connections, db_pool_connections_max)" \
      eventually prometheus_finds "db_pool_connections{service=\"$service\", state=\"idle\"} and on(instance) db_pool_connections_max"
  done
  # 결제 서버의 작업. 정리 작업은 30초마다 돌고, 대사는 check_workers 가 한 번 돌렸다(끝날 때 한 번 민다)
  report "결제 서버의 정리 작업이 작업 메트릭을 민다(sweep.run, instance=sweeper-…)" \
    eventually prometheus_finds 'background_jobs_finished_total{service="billing-server", operation="sweep.run", result="success", instance=~"sweeper-.+"}'
  report "결제 서버의 대사가 끝날 때 작업 메트릭을 민다(reconcile.run)" \
    eventually prometheus_finds 'background_jobs_finished_total{service="billing-server", operation="reconcile.run"}'
  # 업무 메트릭. 주문과 결제 대행사는 CI 에 결제가 없어 값이 생기지 않는다. 알림은 서명 없는 것을 하나 보내 만든다
  send_unsigned_webhook
  report "결제 서버가 서명 없는 알림을 센다(payment_webhooks_total, result=bad_signature)" \
    eventually prometheus_finds 'payment_webhooks_total{service="billing-server", provider="fake", result="bad_signature"}'
}

# --- 대시보드(observability 프로필) ---

# 이름이 붙은 확인 하나를 부르고, 실패하면 그 명령이 찍은 것(무엇이 틀렸는지)을 함께 찍는다
#   report_problems <이름> <명령...>
report_problems() {
  local name="$1" problems; shift
  if problems="$("$@" 2>&1)"; then
    echo "ok   $name"
  else
    echo "FAIL $name"
    sed 's/^/     /' <<<"$problems"
    failures=$((failures + 1))
  fi
}

# Grafana 가 그 uid 의 대시보드를 파일에서 읽었는가
grafana_has_dashboard() {
  status_is 200 "$GRAFANA/api/dashboards/uid/$1" -u "admin:$(grafana_password)"
}

# 대시보드의 Prometheus 쿼리를 Grafana 의 데이터 소스 프록시로 하나씩 돌려 오류가 없는가.
# 값이 없는 것(CI 에 결제가 없어 생기지 않은 메트릭)은 오류가 아니다. 이름이나 PromQL 이 틀린 것을 잡는다
dashboard_queries_run() {
  DASHBOARD_QUERY_AUTH="admin:$(grafana_password)" python3 .github/scripts/dashboard_scope.py "$DASHBOARDS" \
    --query "$GRAFANA/api/datasources/proxy/uid/prometheus"
}

# 대시보드를 본다. 서버의 메트릭이 들어온 뒤에 부른다
check_dashboards() {
  local file uid
  report_problems "대시보드가 규칙을 지킨다(uid 는 파일 이름, 데이터 소스는 uid 로, 쿼리마다 그 서버의 service)" \
    python3 .github/scripts/dashboard_scope.py "$DASHBOARDS"
  for file in "$DASHBOARDS"/*.json; do
    uid="$(basename "$file" .json)"
    report "Grafana 가 대시보드 $uid 를 파일에서 읽었다" eventually grafana_has_dashboard "$uid"
  done
  report_problems "대시보드의 쿼리가 Grafana 를 거쳐 Prometheus 에서 오류 없이 돈다" dashboard_queries_run
}

# 결제 서버에 서명 없는 알림을 하나 보낸다. 401 이 답이다(wget 이 실패로 끝난다). 센 것만 본다
send_unsigned_webhook() {
  fetch_on default http://billing-server:8003/api/v1/billing/webhooks/payment \
    --post-data '{}' --header 'Content-Type: application/json' >/dev/null 2>&1 || true
}

# --- 경보(observability 프로필) ---

# 규칙의 시험(docker/prometheus/rules/tests)이 Prometheus 의 컨테이너 안의 promtool 로 통과하는가
alert_rules_pass() {
  compose exec -T prometheus sh -c 'promtool test rules /etc/prometheus/rules/tests/*.test.yml'
}

# 규칙 파일의 묶음(groups 의 name)이 모두 Prometheus 에 올라왔는가. 파일의 YAML 이 틀리면 Prometheus 는 옛 규칙을 쥔다
prometheus_loaded_rules() {
  local expected
  expected="$(sed -n 's/^  - name: //p' docker/prometheus/rules/*.yml)"
  fetch_on observability http://prometheus:9090/api/v1/rules | python3 -c '
import json, sys
loaded = {group["name"] for group in json.load(sys.stdin)["data"]["groups"]}
missing = set(sys.argv[1].split()) - loaded
print(*sorted(missing), file=sys.stderr)
sys.exit(1 if missing else 0)' "$expected"
}

# Prometheus 가 경보를 넘길 Alertmanager 를 찾았는가
prometheus_finds_alertmanager() {
  fetch_on observability http://prometheus:9090/api/v1/alertmanagers |
    python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin)["data"]["activeAlertmanagers"] else 1)'
}

# 건강한 스택에서 울리는 경보가 없는가. 울리는 것이 있으면 그 이름을 찍는다. 규칙의 선택자가 틀리면(이름표, label) 여기서 울린다
no_alert_firing() {
  fetch_on observability "http://prometheus:9090/api/v1/query?query=$(urlencode 'ALERTS{alertstate="firing"}')" | python3 -c '
import json, sys
firing = sorted({series["metric"]["alertname"] for series in json.load(sys.stdin)["data"]["result"]})
print(*firing, file=sys.stderr)
sys.exit(1 if firing else 0)'
}

# 띄운 Alertmanager 의 설정이 맞는가. 시작 명령이 루트 .env 의 값으로 만든 파일이다
alertmanager_config_valid() {
  compose exec -T alertmanager amtool check-config /tmp/alertmanager/alertmanager.yml
}

# 받는 곳 넷을 모두 적은 설정이 맞는가. CI 는 메일을 보내 보지 않으므로 메일의 설정은 이것으로 본다
alertmanager_accepts_all_receivers() {
  compose run --rm --no-deps -T -e ALERT_SMTP_USER=ci@example.com -e ALERT_SMTP_PASSWORD="$(throwaway)" \
    -e ALERT_EMAIL_TO=ops@example.com,oncall@example.com alertmanager check
}

# 받는 곳을 반쯤 적으면(메일의 계정만) 뜨지 않는가
alertmanager_refuses_half_receiver() {
  ! compose run --rm --no-deps -T -e ALERT_SMTP_USER=ci@example.com alertmanager check
}

# 비밀(봇 토큰)이 설정 파일에 없고, 비밀을 둔 파일을 주인만 읽는가
alertmanager_secrets_private() {
  local token
  token="$(sed -n 's/^ALERT_TELEGRAM_BOT_TOKEN=//p' .env)"
  [[ -n "$token" ]] &&
    ! compose exec -T alertmanager grep -qF "$token" /tmp/alertmanager/alertmanager.yml &&
    [[ -z "$(compose exec -T alertmanager find /tmp/alertmanager -type f ! -perm 600)" ]]
}

# 받는 곳의 흉내를 observability 망에 띄운다. 이미지의 root 가 아닌 사용자(nobody)로 돌린다
alert_sink_up() {
  docker run -d --rm --name "$ALERT_SINK" --network "$(network_of observability)" --user 65534:65534 \
    -v "$PWD/.github/scripts/alert_sink.py:/sink.py:ro" "$ALERT_SINK_IMAGE" python3 -I /sink.py 8080 >/dev/null
}

alert_sink_down() {
  docker rm -f "$ALERT_SINK" >/dev/null 2>&1 || true
}

# 흉내가 준비됐는가
alert_sink_ready() {
  fetch_on observability "http://$ALERT_SINK:8080/received" >/dev/null
}

# 시험 경보를 하나 넣는다. Prometheus 가 넘길 때와 같은 API(v2)다. label run 은 이 실행의 값이다
post_test_alert() {
  local body
  body="$(printf '[{"labels":{"alertname":"StackSmokeAlert","severity":"warning","run":"%s"},"annotations":{"summary":"stack-smoke 의 시험 경보"}}]' "$1")"
  fetch_on observability http://alertmanager:9093/api/v2/alerts --post-data "$body" --header 'Content-Type: application/json' >/dev/null
}

# 흉내가 이 경로(정규식)로 요청을 받았는가
sink_received() {
  fetch_on observability "http://$ALERT_SINK:8080/received" |
    python3 -c 'import json, re, sys; sys.exit(0 if any(re.fullmatch(sys.argv[1], path) for path in json.load(sys.stdin)) else 1)' "$1"
}

# Grafana 가 Alertmanager 에 닿는가(데이터 소스 alertmanager 의 프록시로 상태를 묻는다)
grafana_reaches_alertmanager() {
  status_is 200 "$GRAFANA/api/datasources/proxy/uid/alertmanager/api/v2/status" -u "admin:$(grafana_password)"
}

# 경보를 본다. 메트릭이 들어온 뒤에 부른다. 첫 알림은 30초를 모아 보낸다(group_wait)
check_alerts() {
  local run path
  run="$(openssl rand -hex 8)"
  report "alertmanager 가 root 가 아니다" not_root alertmanager
  report "Alertmanager 가 다시 뜨지 않고 돈다" stays_up alertmanager
  report_problems "경보 규칙의 시험이 통과한다(promtool test rules)" alert_rules_pass
  report_problems "Prometheus 가 규칙 파일의 묶음을 모두 읽었다" prometheus_loaded_rules
  report "Prometheus 가 Alertmanager 를 찾았다" prometheus_finds_alertmanager
  report_problems "건강한 스택에서 울리는 경보가 없다" no_alert_firing
  report "띄운 Alertmanager 의 설정이 맞다(amtool check-config)" alertmanager_config_valid
  report "받는 곳 넷(Discord, Slack, Telegram, 메일)을 모두 적은 설정이 맞다" alertmanager_accepts_all_receivers
  report "받는 곳을 반쯤 적으면 Alertmanager 가 뜨지 않는다" alertmanager_refuses_half_receiver
  report "비밀이 Alertmanager 의 설정 파일에 없고 주인만 읽는다" alertmanager_secrets_private
  report "Grafana 가 Alertmanager 에 닿는다(데이터 소스 alertmanager)" grafana_reaches_alertmanager
  report "결제 서버가 Alertmanager 에 닿지 않는다(경보를 꾸며 넣거나 끄지 못한다)" \
    unreachable_from billing-server http://alertmanager:9093/-/ready
  report "받는 곳의 흉내를 띄운다" alert_sink_up
  report "흉내가 준비됐다" eventually alert_sink_ready
  report "시험 경보를 Alertmanager 에 넣는다" post_test_alert "$run"
  for path in "${ALERT_PATHS[@]}"; do
    report "Alertmanager 가 시험 경보를 보냈다($path)" eventually sink_received "$path"
  done
}

# 모두 돌고 있고, 한 번도 다시 뜨지 않았는가
stays_up_all() {
  local service
  for service in "$@"; do
    stays_up "$service" || return 1
  done
}

# 컨테이너에 서명 개인키의 폴더가 붙지 않았는가. 끝난 컨테이너(마이그레이션)도 본다
no_signing_key_mounted() {
  ! docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$(container_of "$1")" | grep -qx /app/keys
}

# 띄운 컨테이너마다 로그에 크기의 상한(max-size)이 붙었는가(#358). 끝난 컨테이너(마이그레이션)도 본다.
# 설정 검사(logging_scope.py)는 compose 의 설정을 보고, 이것은 Docker 가 실제로 받은 값을 본다
logs_limited() {
  local ids id
  ids="$(compose ps -a -q)"
  [[ -n "$ids" ]] || return 1
  for id in $ids; do
    [[ -n "$(docker inspect -f '{{index .HostConfig.LogConfig.Config "max-size"}}' "$id")" ]] || return 1
  done
}

# compose 의 설정을 검사 스크립트에 넘겨 본다. .env 는 읽지 않는다(--no-interpolate, --no-env-resolution).
# 실패하면 무엇이 틀렸는지(서비스와 이름)를 함께 찍는다. 비밀의 값은 찍지 않는다
#   check_config <이름> <설정을 내는 함수(compose, staging_compose)> <스크립트> [스크립트의 인자...]
check_config() {
  local name="$1" config_of="$2" script="$3" problems; shift 3
  if problems="$("$config_of" config --no-interpolate --no-env-resolution --format json | python3 "$script" "$@" 2>&1)"; then
    echo "ok   $name"
  else
    echo "FAIL $name"
    sed 's/^/     /' <<<"$problems"
    failures=$((failures + 1))
  fi
}

check() {
  local server jwks=http://auth-server:8000/api/v1/auth/jwks
  for server in "${SERVERS[@]}"; do
    report "${server}-migrate 가 성공했다" migrated "$server"
    report "${server}-server 가 준비됐다(/health/ready 가 200, DB 에 닿는다)" ready_inside "$server"
    report "${server}-server 가 root 가 아니다" not_root "${server}-server"
    report "${server}-server 의 이미지에 .env 가 없다" no_env_file_in_image "${server}-server"
  done
  report "인증 서버의 /health 가 200 이다" status_is 200 "$ADMIN/health"
  report "인증 서버의 /health/ready 가 200 이다(DB 에 닿는다)" status_is 200 "$ADMIN/health/ready"
  report "인증 서버의 DB 계정에 CREATEDB 가 없다" auth_cannot_create_databases
  report "관리자 화면을 인증 서버의 포트에서 연다" status_is 200 "$ADMIN/admin/login/"
  report "관리자 화면의 CSS 를 내준다" reachable_from_host "$ADMIN/static/admin/css/base.css"
  report "게임 서버가 인증 서버의 공개키를 받는다" reachable_from game-server "$jwks"
  report "게시판 서버가 인증 서버의 공개키를 받는다" reachable_from board-server "$jwks"
  report "결제 서버가 인증 서버의 공개키를 받는다" reachable_from billing-server "$jwks"
  report "알림 서버가 인증 서버의 공개키를 받는다" reachable_from notification-server "$jwks"
  report "알림 서버가 인증 서버의 끊긴 세션 목록을 받는다" reachable_from notification-server \
    http://auth-server:8000/api/v1/auth/session-revocations
  report "인증 서버가 결제 서버에 닿는다" reachable_from auth-server http://billing-server:8003/health
  report "게임 서버가 결제 서버에 닿는다" reachable_from game-server http://billing-server:8003/health
  report "게임 서버가 알림 서버에 닿는다" reachable_from game-server http://notification-server:8004/health
  report "게임 서버가 서명한 알림을 알림 서버가 받는다" game_notification_accepted
  report "결제 서버의 정리 작업이 알림 서버에 닿는다" reachable_from billing-sweeper http://notification-server:8004/health
  report "게시판 서버가 알림 서버에 닿는다" reachable_from board-server http://notification-server:8004/health
  report "게시판 서버가 서명한 알림을 알림 서버가 받는다" board_notification_accepted
  report "설정 검사(비밀, 열린 포트, 로그 상한, 대시보드)와 .env 를 채우는 도구의 규칙이 맞다" scope_rules_hold
  check_config "비밀은 그것을 쓰는 프로세스에만 간다(docker-compose.yml 과 secret_scope.py 의 표)" compose .github/scripts/secret_scope.py
  check_config "바깥에 여는 포트는 정해 둔 것뿐이고 모두 127.0.0.1 에 묶였다(port_scope.py)" compose .github/scripts/port_scope.py
  check_config "모든 서비스의 로그에 크기와 파일 수의 상한이 있다(logging_scope.py)" compose .github/scripts/logging_scope.py
  report "띄운 컨테이너마다 로그에 상한이 붙었다" logs_limited
  for service in "${KEYLESS[@]}"; do
    report "$service 에 서명 개인키가 붙지 않았다" no_signing_key_mounted "$service"
  done
  report "백업을 빈 DB 에 풀면 원본과 같다" backup_restores
  report "백업 파일을 주인만 읽는다" backup_private
  check_workers
  check_logs
  check_metrics
  check_alerts
  finish
}

# 워커와 주기 명령을 본다
check_workers() {
  local worker entry service crontab command
  for worker in "${WORKERS[@]}"; do
    report "$worker 가 다시 뜨지 않고 돈다" stays_up "$worker"
  done
  for worker in "${HEARTBEAT_WORKERS[@]}"; do
    report "$worker 가 healthy 다(DB 에 닿으며 돈다)" is_healthy "$worker"
  done
  for entry in "${CRONTABS[@]}"; do
    service="${entry%%:*}"
    crontab="${entry#*:}"
    report "$service 의 crontab 문법이 맞다" crontab_valid "$service"
    while IFS= read -r command; do
      report "$service 에서 [$command] 이 한 번 성공한다" runs_once "$service" "$command"
    done < <(crontab_commands "$crontab")
  done
}

# 프록시를 거쳐 본다. 요청 수 제한을 채우므로 맨 마지막에 부른다
check_proxy() {
  report "프록시로 인증 서버에 닿는다" status_is 200 "$PROXY/api/v1/auth/jwks"
  # 토큰 없이 부른 /me 의 401 은 그 서버가 답한 것이다. 프록시가 막았으면 404 다
  report "프록시로 게임 서버에 닿는다" status_is 401 "$PROXY/api/v1/game/me"
  report "프록시로 게시판 서버에 닿는다" status_is 401 "$PROXY/api/v1/board/me"
  report "프록시로 결제 서버에 닿는다" status_is 401 "$PROXY/api/v1/billing/me"
  report "프록시로 알림 서버에 닿는다" status_is 401 "$PROXY/api/v1/notification/me/notifications"
  report "프록시는 관리자 화면을 막는다" status_is 404 "$PROXY/admin/login/"
  report "프록시는 관리자 화면의 CSS 를 막는다" status_is 404 "$PROXY/static/admin/css/base.css"
  report "프록시는 점 두 개로 돌아가는 주소도 막는다" status_is 404 "$PROXY/api/v1/auth/%2e%2e/%2e%2e/admin/login/" --path-as-is
  # 결제 서버에 닿으면 서명이 없어 401 이다. 404 면 프록시가 막은 것이다
  report "프록시는 서버끼리만 부르는 결제 주소를 막는다" status_is 404 "$PROXY/api/v1/billing/service/holds" -X POST
  # 인증 서버에 닿으면 서명이 없어 401 이다(#352)
  report "프록시는 서버끼리만 부르는 인증 주소를 막는다" status_is 404 "$PROXY/api/v1/auth/service/guardian-notices" -X POST
  # 알림 서버에 닿으면 서명이 없어 401 이다
  report "프록시는 서버끼리만 부르는 알림 주소를 막는다" status_is 404 "$PROXY/api/v1/notification/service/game/notifications" -X POST
  report "프록시는 서버의 상태 확인 주소를 막는다" status_is 404 "$PROXY/health"
  report "프록시는 그 밖의 주소를 막는다" status_is 404 "$PROXY/"
  report "프록시가 요청 식별자를 하나 정해 돌려준다" one_request_id_from_proxy
  report "서버의 응답에 보안 머리말이 하나씩 붙는다" security_headers "$PROXY/api/v1/auth/jwks"
  report "막은 주소의 404 에도 보안 머리말이 붙는다" security_headers "$PROXY/"
  report "HTTP 의 응답에는 HSTS 가 없다" no_header Strict-Transport-Security "$PROXY/api/v1/auth/jwks"
  report "서버끼리만 부르는 주소의 404 에도 보안 머리말이 붙는다" security_headers "$PROXY/api/v1/billing/service/holds" -X POST
  report "인증의 민감한 요청을 IP 마다 막는다" limited_after 12 "$PROXY/api/v1/auth/login" 6 \
    -X POST -H 'Content-Type: application/json' -d '{}'
  # 위에서 제한을 채웠으므로 한 번 더 부르면 429 다
  report "요청 수 제한의 429 에도 보안 머리말이 붙는다" security_headers "$PROXY/api/v1/auth/login" \
    -X POST -H 'Content-Type: application/json' -d '{}'
  report "게시판 검색을 IP 마다 막는다" limited_after 10 "$PROXY/api/v1/board/posts?q=smoke" 1
  finish
}

# --- staging 의 설정(#451) ---

# 그 머리말이 없는가. 둘째 인자부터는 curl 에 넘긴다
no_header() {
  local name="$1" url="$2" headers; shift 2
  headers="$(curl -s -D - -o /dev/null --max-time 5 "$@" "$url")"
  [[ -n "$headers" ]] && ! grep -qi "^$name:" <<<"$headers"
}

# staging 의 프록시에 HTTPS 로 부른다. 도메인을 이 PC 로 돌리고, 자체 서명 인증서라 확인을 끈다
staging_curl() {
  curl -s --max-time 5 -k --resolve "$STAGING_DOMAIN:18443:127.0.0.1" "$@"
}

# staging 의 프록시의 답이 이 상태 코드인가. 셋째 인자부터는 curl 에 넘긴다
staging_status_is() {
  local expected="$1" url="$2"; shift 2
  [[ "$(staging_curl -o /dev/null -w '%{http_code}' "$@" "$url")" == "$expected" ]]
}

# staging 의 프록시의 응답에 보안 머리말 넷(HSTS 포함)이 하나씩 붙었는가. 둘째 인자부터는 curl 에 넘긴다
staging_security_headers() {
  local url="$1" headers; shift
  headers="$(staging_curl -D - -o /dev/null "$@" "$url" | tr -d '\r')"
  one_header "$headers" X-Content-Type-Options nosniff &&
    one_header "$headers" Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" &&
    one_header "$headers" Referrer-Policy no-referrer &&
    one_header "$headers" Strict-Transport-Security "max-age=31536000"
}

# HTTP 로 부르면 정한 도메인의 HTTPS 로 넘기는가(받은 Host 가 아니라)
redirects_to_https() {
  [[ "$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 5 -H 'Host: evil.example' \
    "$STAGING_HTTP/api/v1/game/me?x=1")" == "301 https://$STAGING_DOMAIN/api/v1/game/me?x=1" ]]
}

# 인증서의 확인 파일(HTTP-01)을 HTTP 로 내주는가
serves_acme_challenge() {
  [[ "$(curl -s --max-time 5 "$STAGING_HTTP/.well-known/acme-challenge/stack-smoke")" == "stack-smoke-token" ]]
}

# 이 TLS 판으로 붙는가
tls_version_works() {
  staging_curl -o /dev/null "--tlsv$1" --tls-max "$1" "$STAGING_HTTPS/healthz"
}

# 그 주소가 기다리는 동안 이 상태 코드가 되는가(허용 주소를 고친 뒤 nginx 가 다시 읽기를 기다린다)
eventually_status_is() {
  local expected="$1" url="$2" deadline=$((SECONDS + 15))
  while ((SECONDS < deadline)); do
    staging_status_is "$expected" "$url" && return 0
    sleep 1
  done
  return 1
}

# staging 에만 있는 이미지(certbot, ollama)의 태그가 저장소에 있는가. 받지 않고 목록만 묻는다(ollama 는 크다).
# 로컬에도 있는 이미지는 up 이 이미 받았다. 이 저장소에서 만드는 이미지(ai-trpg/...)는 빼고 본다
staging_images_exist() {
  local image
  while IFS= read -r image; do
    docker manifest inspect "$image" >/dev/null || { echo "$image 이 없다" >&2; return 1; }
  done < <(comm -13 <(compose config --images | sort -u) <(staging_compose config --images | sort -u) | grep -v '^ai-trpg/')
}

# 인증서의 남은 날짜 검사(docker/certbot/cert_check.py)의 테스트를 certbot 이미지 안에서 돌린다(cryptography 가 있다)
cert_check_rules_hold() {
  staging_compose run --rm --no-deps -e PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 certbot \
    -m unittest discover -s /opt/certbot -p 'test_*.py'
}

# 자체 서명 인증서를 만들어 deploy-hook.sh 로 tls 볼륨에 옮긴다. certbot 이 갱신한 뒤와 같은 길이다.
# 인증서의 확인 파일 하나도 acme 볼륨에 둔다
staging_certificate() {
  local lineage
  lineage="$(mktemp -d)"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 30 \
    -subj "/CN=$STAGING_DOMAIN" -addext "subjectAltName=DNS:$STAGING_DOMAIN" \
    -keyout "$lineage/privkey.pem" -out "$lineage/fullchain.pem" 2>/dev/null
  chmod a+r "$lineage"/*.pem
  staging_compose run --rm --no-deps -v "$lineage:/lineage:ro" -e RENEWED_LINEAGE=/lineage \
    --entrypoint sh certbot /opt/certbot/deploy-hook.sh
  staging_compose run --rm --no-deps --entrypoint sh certbot -c \
    'mkdir -p /var/www/certbot/.well-known/acme-challenge && echo stack-smoke-token > /var/www/certbot/.well-known/acme-challenge/stack-smoke'
  rm -rf "$lineage"
}

# 옮긴 키를 프록시의 사용자(101)만 읽는가
private_key_private() {
  [[ "$(staging_compose run --rm --no-deps --entrypoint stat certbot -c '%u %a' /tls/privkey.pem | tr -d '\r')" == "101 600" ]]
}

# 인증서가 30일 남았으니 certbot 의 상태 확인이 통과하는가
cert_check_passes() {
  staging_compose run --rm --no-deps --entrypoint python3 certbot /opt/certbot/cert_check.py
}

# staging 의 프록시를 compose 의 정의 그대로 하나 더 띄운다(시작 스크립트, 틀, 볼륨). 포트만 이 PC 의 다른 곳에 연다.
# 허용 주소를 지켜보는 간격을 1초로 줄인다
staging_proxy_up() {
  staging_proxy_down
  staging_compose run -d --no-deps --name "$STAGING_PROXY" -e WATCH_SECONDS=1 \
    -p 127.0.0.1:18080:8080 -p 127.0.0.1:18443:8443 proxy >/dev/null
  local deadline=$((SECONDS + 30))
  while ((SECONDS < deadline)); do
    staging_status_is 200 "$STAGING_HTTPS/healthz" && return 0
    sleep 1
  done
  docker logs "$STAGING_PROXY" >&2 || true
  return 1
}

staging_proxy_down() {
  docker rm -f "$STAGING_PROXY" >/dev/null 2>&1 || true
  rm -f "$STAGING_ALLOWLIST"
}

# 허용 주소에 모든 주소를 적는다. CI 의 요청이 어느 주소로 오는지(Docker 의 게이트웨이) 몰라서다
allow_everyone() {
  echo 'allow all;' >"$STAGING_ALLOWLIST"
}

# --- 바깥 백업(backup-offsite) ---

# 바깥 백업의 컨테이너에서 명령 하나를 돌린다. 둘째 인자부터는 그 명령의 인자다
#   offsite <offsite.sh 의 명령> [docker compose run 의 옵션...]
offsite() {
  local command="$1"; shift
  staging_compose run --rm --no-deps -T "$@" backup-offsite "$command"
}

# S3 흉내에 aws CLI 를 부른다. 바깥 백업의 이미지에 든 것을 쓴다
offsite_aws() {
  staging_compose run --rm --no-deps -T --entrypoint aws backup-offsite --endpoint-url "http://$STAGING_S3:5000" "$@"
}

# age 의 열쇠를 하나 만들어 그 파일에 쓴다. 공개키를 찍는다
#   new_age_key <파일>
new_age_key() {
  staging_compose run --rm --no-deps -T --entrypoint age-keygen backup-offsite >"$1" 2>/dev/null
  grep -o 'age1[0-9a-z]*' "$1"
}

# S3 흉내(moto)를 서버의 망에 띄우고 버킷을 만든다. 설치하는 데 1~2분 걸린다
offsite_s3_up() {
  docker rm -f "$STAGING_S3" >/dev/null 2>&1 || true
  docker run -d --name "$STAGING_S3" --network "$(network_of default)" "$STAGING_S3_IMAGE" \
    sh -c "pip install --quiet --disable-pip-version-check 'moto[server]==$MOTO_VERSION' && exec moto_server -H 0.0.0.0 -p 5000" \
    >/dev/null
  local deadline=$((SECONDS + 240))
  while ((SECONDS < deadline)); do
    if offsite_aws s3 ls >/dev/null 2>&1; then
      offsite_aws s3 mb "s3://$STAGING_BUCKET" >/dev/null
      return
    fi
    sleep 5
  done
  docker logs "$STAGING_S3" >&2 || true
  return 1
}

# 확인 열쇠(VM 에 두는 것)와 주 열쇠(VM 밖에 두는 것)를 만들고, 받는 쪽 열쇠를 그 둘로 바꾼다.
# 셋째 열쇠(stranger)는 받는 쪽이 아니다. 그것으로는 풀리지 않아야 한다
offsite_keys() {
  local check master
  rm -rf "$STAGING_KEYS" && mkdir -m 700 "$STAGING_KEYS"
  offsite_key_dir="$(mktemp -d)"
  check="$(new_age_key "$STAGING_KEYS/check.key")" || return 1
  master="$(new_age_key "$offsite_key_dir/master.key")" || return 1
  stranger="$(new_age_key "$offsite_key_dir/stranger.key")" || return 1
  [[ -n "$check" && -n "$master" && -n "$stranger" ]] || return 1
  chmod a+r "$offsite_key_dir"/*.key
  staging_recipients="$master $check"
}

# 버킷에 올라간 것이 age 로 잠긴 파일인가(맨 앞이 age 의 머리말인가). 덤프가 그대로 올라가면 안 된다
uploaded_encrypted() {
  local key
  key="$(offsite_aws s3 ls "s3://$STAGING_BUCKET/" | awk '{print $4}' | tr -d '\r' | sort | tail -n 1)"
  [[ "$key" == trpg-*.dump.age ]] || return 1
  [[ "$(offsite_aws s3 cp "s3://$STAGING_BUCKET/$key" - | head -c 21)" == "age-encryption.org/v1" ]]
}

# 주 열쇠(VM 밖의 것)로 풀어 본다. 손으로 되살릴 때의 열쇠도 받는 쪽인가
master_key_restores() {
  offsite verify -v "$offsite_key_dir:/run/master-keys:ro" -e OFFSITE_CHECK_KEY=/run/master-keys/master.key
}

# 받는 쪽이 아닌 열쇠로는 풀리지 않는가. 받는 쪽 열쇠의 검사를 지나도록 그 열쇠를 받는 쪽인 척 적는다(파일은 그 열쇠로 잠기지 않았다)
stranger_key_fails() {
  local real="$staging_recipients" status=0
  staging_recipients="${real%% *} $stranger"
  if offsite verify -v "$offsite_key_dir:/run/master-keys:ro" -e OFFSITE_CHECK_KEY=/run/master-keys/stranger.key; then
    status=1
  fi
  staging_recipients="$real"
  return "$status"
}

# 풀어 본 뒤 확인용 DB 가 남지 않았는가
no_offsite_check_db() {
  local sql="SELECT count(*) FROM pg_database WHERE datname LIKE '%\_offsite\_check'"
  # shellcheck disable=SC2016
  [[ "$(compose exec -T -e SQL="$sql" db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$SQL"')" == "0" ]]
}

# 풀어 보기가 실패한 뒤 상태 확인이 곧바로 실패하는가(마지막으로 풀어 본 시각을 지운다)
unhealthy_after_failed_verify() {
  ! offsite health
}

offsite_down() {
  docker rm -f "$STAGING_S3" >/dev/null 2>&1 || true
  rm -rf "$STAGING_KEYS"
  [[ -z "${offsite_key_dir:-}" ]] || rm -rf "$offsite_key_dir"
}

# 바깥 백업: 암호화해 올리고, 확인 열쇠와 주 열쇠로 풀리고, 다른 열쇠로는 풀리지 않는가
check_offsite_backup() {
  report "바깥 백업의 이미지를 만든다(age, aws CLI)" staging_compose build backup-offsite
  report "바깥 백업의 열쇠(확인, 주)를 만든다" offsite_keys
  if ! offsite_s3_up; then
    echo "FAIL S3 흉내(moto)가 뜬다"
    failures=$((failures + 1))
    offsite_down
    return
  fi
  echo "ok   S3 흉내(moto)가 뜬다"
  report "로컬의 백업을 암호화해 버킷에 올린다" offsite upload
  report "버킷의 것은 age 로 잠겨 있다(덤프가 그대로 올라가지 않는다)" uploaded_encrypted
  report "다시 올려도 이미 올린 것은 건너뛴다" offsite upload
  report "버킷의 백업을 확인 열쇠로 풀어 원본과 맞추고 빈 DB 에 푼다" offsite verify
  report "올리고 풀어 본 뒤에는 healthy 다" offsite health
  report "주 열쇠(VM 밖에 두는 것)로도 풀린다" master_key_restores
  report "받는 쪽이 아닌 열쇠로는 풀리지 않는다" stranger_key_fails
  report "풀어 보기가 실패하면 곧바로 unhealthy 다" unhealthy_after_failed_verify
  report "풀어 본 뒤 확인용 DB 가 남지 않는다" no_offsite_check_db
  offsite_down
}

check_staging() {
  report "staging 의 설정을 값을 채워 읽을 수 있다" staging_compose config -q
  check_config "staging 에서도 비밀은 그것을 쓰는 프로세스에만 간다(secret_scope.py)" staging_compose .github/scripts/secret_scope.py
  check_config "staging 에서 바깥에 여는 포트는 프록시의 80, 443 뿐이다(port_scope.py --public)" staging_compose \
    .github/scripts/port_scope.py --public
  check_config "staging 에만 있는 서비스에도 로그의 상한이 있다(logging_scope.py)" staging_compose .github/scripts/logging_scope.py
  report "staging 에만 있는 이미지의 태그가 있다" staging_images_exist
  report "인증서의 남은 날짜 검사의 규칙이 맞다(docker/certbot)" cert_check_rules_hold
  report "받은 인증서를 프록시가 읽는 곳에 옮긴다(deploy-hook.sh)" staging_certificate
  report "옮긴 키를 프록시의 사용자만 읽는다" private_key_private
  report "남은 날이 넉넉한 인증서는 certbot 의 상태 확인을 통과한다" cert_check_passes
  if ! staging_proxy_up; then
    echo "FAIL staging 의 프록시가 HTTPS 로 뜬다"
    failures=$((failures + 1))
    staging_proxy_down
    finish
    return
  fi
  echo "ok   staging 의 프록시가 HTTPS 로 뜬다"
  report "HTTP 는 정한 도메인의 HTTPS 로 넘긴다(받은 Host 가 아니다)" redirects_to_https
  report "인증서의 확인 파일은 HTTP 로 내준다" serves_acme_challenge
  report "HTTP 의 넘기기에는 HSTS 가 없다" no_header Strict-Transport-Security "$STAGING_HTTP/"
  report "TLS 1.2 로 붙는다" tls_version_works 1.2
  report "TLS 1.3 으로 붙는다" tls_version_works 1.3
  report "가동 확인은 허용 주소 밖에서도 답한다" staging_status_is 200 "$STAGING_HTTPS/healthz"
  report "가동 확인에도 보안 머리말과 HSTS 가 붙는다" staging_security_headers "$STAGING_HTTPS/healthz"
  report "허용 주소 밖에서는 서버에 닿지 못한다(403)" staging_status_is 403 "$STAGING_HTTPS/api/v1/game/me"
  report "막은 403 에도 보안 머리말과 HSTS 가 붙는다" staging_security_headers "$STAGING_HTTPS/api/v1/game/me"
  allow_everyone
  report "허용 주소를 고치면 다시 읽어 서버에 닿는다" eventually_status_is 401 "$STAGING_HTTPS/api/v1/game/me"
  report "서버의 응답에도 보안 머리말과 HSTS 가 하나씩 붙는다" staging_security_headers "$STAGING_HTTPS/api/v1/game/me"
  report "허용 주소 안에서도 관리자 화면은 막는다" staging_status_is 404 "$STAGING_HTTPS/admin/login/"
  report "허용 주소 안에서도 서버끼리만 부르는 주소는 막는다" staging_status_is 404 "$STAGING_HTTPS/api/v1/billing/service/holds" -X POST
  staging_proxy_down
  check_offsite_backup
  finish
}

# 실패한 것이 있으면 실패로 끝낸다
finish() {
  if ((failures > 0)); then
    echo "$failures 개 실패"
    return 1
  fi
  echo "모두 통과"
}

logs() {
  compose ps -a
  compose logs --no-color
}

down() {
  alert_sink_down
  staging_proxy_down
  offsite_down
  compose down -v
}

main() {
  case "${1:-}" in
    prepare | up | check | logs | down) "$1" ;;
    check-proxy) check_proxy ;;
    check-staging) check_staging ;;
    *)
      echo "사용: $0 prepare | up | check | check-proxy | check-staging | logs | down" >&2
      return 2 ;;
  esac
}

main "$@"
