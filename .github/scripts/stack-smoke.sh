#!/usr/bin/env bash
# .github/scripts/stack-smoke.sh
#
# compose 로 모든 서버를 컨테이너로 띄워 보고 확인한다. 관문 워크플로(.github/workflows/ci.yml 의 stack)가 부른다.
#
#   사용: stack-smoke.sh prepare | up | check | check-proxy | logs | down
#     prepare      설정 파일(.env 여섯)과 JWT 키를 이 실행에서만 쓰고 버리는 값으로 만든다
#     up           이미지를 만들고 띄운 뒤, 서버들과 프록시, Prometheus, Grafana, 상태 확인이 있는 워커가 healthy 가 되고
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
#                  수집 쪽 자신의 메트릭이 들어오는가, Prometheus 가 아무것도 긁지 않는가, Grafana 가 Prometheus 에 닿는가
#     check-proxy  프록시를 거쳐 본다: 서버마다 닿는가, 막을 주소를 막는가, 요청 식별자, 요청 수 제한,
#                  모든 응답(서버의 응답, 404, 429)의 보안 머리말.
#                  HTTP 로만 보므로 컨테이너 없이도 돈다. 주소는 PROXY, ADMIN 환경 변수로 바꾼다
#     logs         모든 컨테이너의 로그를 찍는다. 실패했을 때 부른다
#     down         컨테이너와 볼륨을 지운다
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
# Loki 의 label 로 쓰는 것(docs/observability.md 의 "Loki 의 label"). 이것 말고는 label 이 없어야 한다
LOKI_LABELS=(container environment level mode service)
# 메트릭을 OTLP 로 미는 서버(docs/observability.md 의 "2. 메트릭"). 서버에 메트릭을 붙이면 여기에 더한다.
# 그 서버의 요청 수, DB 의 상태, 연결 풀이 Prometheus 에 있는지 본다
METRIC_SERVERS=(billing)
# 서버의 망 밖(소켓 프록시와 Loki 의 망)에서 주소를 부를 때 잠깐 띄우는 이미지. compose 의 redis 와 같아 이미 받아 두었다.
# 그 안의 busybox wget 을 쓴다
PROBE_IMAGE=redis:7-alpine
# 컨테이너의 사용자. Dockerfile 에서 정한 번호다. 노드 이미지는 제 사용자(node, 1000)를 쓴다
APP_UID=10001

# 서버들(app)과 로그와 메트릭 모으기(observability)를 함께 띄운다
compose() {
  docker compose --profile app --profile observability "$@"
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
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318
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

# 서버들과 프록시, Prometheus, Grafana, 심장박동을 알리는 워커가 모두 healthy 가 될 때까지 기다린다. 하나라도 죽거나 시간이 지나면 실패한다.
wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS)) service pending
  while ((SECONDS < deadline)); do
    pending=0
    for service in "${SERVERS[@]/%/-server}" proxy prometheus grafana "${HEARTBEAT_WORKERS[@]}"; do
      if ! running "$service"; then
        echo "$service 가 죽었다" >&2
        return 1
      fi
      [[ "$(health_of "$service")" == "healthy" ]] || pending=$((pending + 1))
    done
    if ((pending == 0)); then
      echo "서버들과 프록시, Prometheus, Grafana, 상태 확인이 있는 워커가 healthy 다"
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

# 설정을 보는 검사(secret_scope.py, port_scope.py, logging_scope.py)의 규칙이 맞는가. 규칙이 틀리면 새는 것을 놓치고 초록이 된다
scope_rules_hold() {
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -p 'test_*_scope.py'
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
  for job in alloy loki prometheus grafana; do
    report "Alloy 가 $job 의 메트릭을 긁어 보낸다" eventually prometheus_finds "up{job=\"$job\"} == 1"
  done
  report "게임 서버가 Prometheus 에 닿지 않는다" unreachable_from game-server http://prometheus:9090/-/ready
  report "결제 서버가 Prometheus 에 닿지 않는다(telemetry 망에서는 Alloy 에만 닿는다)" \
    unreachable_from billing-server http://prometheus:9090/-/ready
  check_server_metrics
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

# 결제 서버에 서명 없는 알림을 하나 보낸다. 401 이 답이다(wget 이 실패로 끝난다). 센 것만 본다
send_unsigned_webhook() {
  fetch_on default http://billing-server:8003/api/v1/billing/webhooks/payment \
    --post-data '{}' --header 'Content-Type: application/json' >/dev/null 2>&1 || true
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
#   check_config <이름> <스크립트>
check_config() {
  local name="$1" script="$2" problems
  if problems="$(compose config --no-interpolate --no-env-resolution --format json | python3 "$script" 2>&1)"; then
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
  report "설정 검사(비밀, 열린 포트, 로그 상한)의 규칙이 맞다" scope_rules_hold
  check_config "비밀은 그것을 쓰는 프로세스에만 간다(docker-compose.yml 과 secret_scope.py 의 표)" .github/scripts/secret_scope.py
  check_config "바깥에 여는 포트는 정해 둔 것뿐이고 모두 127.0.0.1 에 묶였다(port_scope.py)" .github/scripts/port_scope.py
  check_config "모든 서비스의 로그에 크기와 파일 수의 상한이 있다(logging_scope.py)" .github/scripts/logging_scope.py
  report "띄운 컨테이너마다 로그에 상한이 붙었다" logs_limited
  for service in "${KEYLESS[@]}"; do
    report "$service 에 서명 개인키가 붙지 않았다" no_signing_key_mounted "$service"
  done
  report "백업을 빈 DB 에 풀면 원본과 같다" backup_restores
  report "백업 파일을 주인만 읽는다" backup_private
  check_workers
  check_logs
  check_metrics
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
  report "서버끼리만 부르는 주소의 404 에도 보안 머리말이 붙는다" security_headers "$PROXY/api/v1/billing/service/holds" -X POST
  report "인증의 민감한 요청을 IP 마다 막는다" limited_after 12 "$PROXY/api/v1/auth/login" 6 \
    -X POST -H 'Content-Type: application/json' -d '{}'
  # 위에서 제한을 채웠으므로 한 번 더 부르면 429 다
  report "요청 수 제한의 429 에도 보안 머리말이 붙는다" security_headers "$PROXY/api/v1/auth/login" \
    -X POST -H 'Content-Type: application/json' -d '{}'
  report "게시판 검색을 IP 마다 막는다" limited_after 10 "$PROXY/api/v1/board/posts?q=smoke" 1
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
  compose down -v
}

main() {
  case "${1:-}" in
    prepare | up | check | logs | down) "$1" ;;
    check-proxy) check_proxy ;;
    *)
      echo "사용: $0 prepare | up | check | check-proxy | logs | down" >&2
      return 2 ;;
  esac
}

main "$@"
