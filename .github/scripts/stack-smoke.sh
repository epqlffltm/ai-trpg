#!/usr/bin/env bash
# .github/scripts/stack-smoke.sh
#
# compose 로 서버 넷을 컨테이너로 띄워 보고 확인한다. 관문 워크플로(.github/workflows/ci.yml 의 stack)가 부른다.
#
#   사용: stack-smoke.sh prepare | up | check | check-proxy | logs | down
#     prepare      설정 파일(.env 다섯)과 JWT 키를 이 실행에서만 쓰고 버리는 값으로 만든다
#     up           이미지를 만들고 띄운 뒤, 서버 넷과 프록시, 상태 확인이 있는 워커가 healthy 가 될 때까지 기다린다.
#                  서버의 healthcheck 는 /health/ready 라서, healthy 는 그 서버가 DB 에 닿는다는 뜻이다.
#                  워커의 healthcheck 는 심장박동 파일이라서, healthy 는 그 워커가 DB 에 닿으며 돈다는 뜻이다.
#                  DB 의 백업은 최근 백업 파일이 있으면 healthy 다
#     check        마이그레이션이 성공했는지, 서버마다 준비됐는지(/health/ready), 서버끼리 닿는지, root 가 아닌지,
#                  이미지에 .env 가 없는지 본다. 비밀이 그것을 쓰는 프로세스에만 가는지도 본다(secret_scope.py).
#                  워커와 cron 이 다시 뜨기를 되풀이하지 않고 돌고 있는지, crontab 의 명령이 한 번씩 성공하는지도 본다
#     check-proxy  프록시를 거쳐 본다: 서버마다 닿는가, 막을 주소를 막는가, 요청 식별자, 요청 수 제한.
#                  HTTP 로만 보므로 컨테이너 없이도 돈다. 주소는 PROXY, ADMIN 환경 변수로 바꾼다
#     logs         모든 컨테이너의 로그를 찍는다. 실패했을 때 부른다
#     down         컨테이너와 볼륨을 지운다
#
# 서버의 기능은 보지 않는다. 그것은 서버마다의 CI 가 한다. 여기서는 "이미지가 만들어지고, 마이그레이션이 돌고,
# 서버가 뜨고, 서로 닿는가"만 본다.
#
# PC 에서 부르지 않는다. prepare 는 CI 가 아니면 멈춘다. 있는 .env 는 덮어쓰지 않는다.

set -euo pipefail

SERVERS=(auth game board billing)
# 서버마다 컨테이너 안에서 듣는 포트
declare -A PORTS=([auth]=8000 [game]=8001 [board]=8002 [billing]=8003)
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
# 컨테이너의 사용자. Dockerfile 에서 정한 번호다. 노드 이미지는 제 사용자(node, 1000)를 쓴다
APP_UID=10001

compose() {
  docker compose --profile app "$@"
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

# 다섯 개의 .env 를 만든다. 주소는 compose 가 덮어쓰므로 비밀만 적는다.
# 서버끼리 함께 아는 비밀은 두 파일에 같은 값을 넣는다(결제 서버와 게임 서버, 결제 서버와 인증 서버)
write_env_files() {
  local game_secret auth_secret
  game_secret="$(throwaway)"
  auth_secret="$(throwaway)"
  write_new .env <<EOF
POSTGRES_PASSWORD=$(throwaway)
AUTH_DB_PASSWORD=$(throwaway)
GAME_DB_PASSWORD=$(throwaway)
BILLING_DB_PASSWORD=$(throwaway)
BOARD_DB_PASSWORD=$(throwaway)
EOF
  write_new auth-server/.env <<EOF
SECRET_KEY=$(throwaway)
BILLING_SECRET=$auth_secret
EOF
  write_new game-server/.env <<EOF
BILLING_SECRET=$game_secret
EOF
  write_new board-server/.env < /dev/null
  write_new billing-server/.env <<EOF
PG_WEBHOOK_SECRET=$(throwaway)
GAME_SERVER_SECRET=$game_secret
AUTH_SERVER_SECRET=$auth_secret
EOF
}

# JWT 개인키를 만든다. 주인만 읽게 두고 주인을 컨테이너의 사용자로 바꾼다.
# 리눅스에서 키 폴더를 컨테이너에 붙일 때 해야 하는 일과 같다(README 의 "서버 넷을 컨테이너로")
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

# 서버 넷과 프록시, 심장박동을 알리는 워커가 모두 healthy 가 될 때까지 기다린다. 하나라도 죽거나 시간이 지나면 실패한다.
wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS)) service pending
  while ((SECONDS < deadline)); do
    pending=0
    for service in "${SERVERS[@]/%/-server}" proxy "${HEARTBEAT_WORKERS[@]}"; do
      if ! running "$service"; then
        echo "$service 가 죽었다" >&2
        return 1
      fi
      [[ "$(health_of "$service")" == "healthy" ]] || pending=$((pending + 1))
    done
    if ((pending == 0)); then
      echo "서버 넷과 프록시, 상태 확인이 있는 워커가 healthy 다"
      return 0
    fi
    sleep 3
  done
  echo "${WAIT_SECONDS}초 안에 healthy 가 되지 않았다" >&2
  return 1
}

up() {
  compose up -d --build
  wait_healthy
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
    auth-server | game-server)
      compose exec -T "$service" python -c "import urllib.request; urllib.request.urlopen('$url', timeout=5)" ;;
    board-server)
      compose exec -T "$service" node -e "fetch('$url').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))" ;;
    billing-server)
      compose exec -T "$service" wget -q -O /dev/null "$url" ;;
  esac
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

# 비밀의 범위 검사(secret_scope.py)의 규칙이 맞는가. 규칙이 틀리면 새는 비밀을 놓치고 초록이 된다
secret_scope_rules_hold() {
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s .github/scripts -p 'test_secret_scope.py'
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

# 컨테이너에 서명 개인키의 폴더가 붙지 않았는가. 끝난 컨테이너(마이그레이션)도 본다
no_signing_key_mounted() {
  ! docker inspect -f '{{range .Mounts}}{{println .Destination}}{{end}}' "$(container_of "$1")" | grep -qx /app/keys
}

# compose 의 설정에서 비밀이 그것을 쓰는 프로세스에만 가는지 본다. .env 는 읽지 않는다(--no-env-resolution).
# 실패하면 무엇이 새는지(프로세스와 비밀의 이름)를 함께 찍는다. 값은 찍지 않는다
check_secret_scope() {
  local name="비밀은 그것을 쓰는 프로세스에만 간다(docker-compose.yml 과 secret_scope.py 의 표)" problems
  if problems="$(compose config --no-interpolate --no-env-resolution --format json | python3 .github/scripts/secret_scope.py 2>&1)"; then
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
  report "인증 서버가 결제 서버에 닿는다" reachable_from auth-server http://billing-server:8003/health
  report "게임 서버가 결제 서버에 닿는다" reachable_from game-server http://billing-server:8003/health
  report "비밀의 범위 검사의 규칙이 맞다" secret_scope_rules_hold
  check_secret_scope
  for service in "${KEYLESS[@]}"; do
    report "$service 에 서명 개인키가 붙지 않았다" no_signing_key_mounted "$service"
  done
  report "백업을 빈 DB 에 풀면 원본과 같다" backup_restores
  report "백업 파일을 주인만 읽는다" backup_private
  check_workers
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
  report "프록시는 관리자 화면을 막는다" status_is 404 "$PROXY/admin/login/"
  report "프록시는 관리자 화면의 CSS 를 막는다" status_is 404 "$PROXY/static/admin/css/base.css"
  report "프록시는 점 두 개로 돌아가는 주소도 막는다" status_is 404 "$PROXY/api/v1/auth/%2e%2e/%2e%2e/admin/login/" --path-as-is
  # 결제 서버에 닿으면 서명이 없어 401 이다. 404 면 프록시가 막은 것이다
  report "프록시는 서버끼리만 부르는 결제 주소를 막는다" status_is 404 "$PROXY/api/v1/billing/service/holds" -X POST
  # 인증 서버에 닿으면 서명이 없어 401 이다(#352)
  report "프록시는 서버끼리만 부르는 인증 주소를 막는다" status_is 404 "$PROXY/api/v1/auth/service/guardian-notices" -X POST
  report "프록시는 서버의 상태 확인 주소를 막는다" status_is 404 "$PROXY/health"
  report "프록시는 그 밖의 주소를 막는다" status_is 404 "$PROXY/"
  report "프록시가 요청 식별자를 하나 정해 돌려준다" one_request_id_from_proxy
  report "인증의 민감한 요청을 IP 마다 막는다" limited_after 12 "$PROXY/api/v1/auth/login" 6 \
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
