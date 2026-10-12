#!/usr/bin/env bash
# .github/scripts/stack-smoke.sh
#
# compose 로 서버 넷을 컨테이너로 띄워 보고 확인한다. 관문 워크플로(.github/workflows/ci.yml 의 stack)가 부른다.
#
#   사용: stack-smoke.sh prepare | up | check | logs | down
#     prepare  설정 파일(.env 다섯)과 JWT 키를 이 실행에서만 쓰고 버리는 값으로 만든다
#     up       이미지를 만들고 띄운 뒤, 서버 넷이 healthy 가 될 때까지 기다린다
#     check    마이그레이션이 성공했는지, 바깥과 서버끼리 닿는지, root 가 아닌지, 이미지에 .env 가 없는지 본다
#     logs     모든 컨테이너의 로그를 찍는다. 실패했을 때 부른다
#     down     컨테이너와 볼륨을 지운다
#
# 서버의 기능은 보지 않는다. 그것은 서버마다의 CI 가 한다. 여기서는 "이미지가 만들어지고, 마이그레이션이 돌고,
# 서버가 뜨고, 서로 닿는가"만 본다.
#
# PC 에서 부르지 않는다. prepare 는 CI 가 아니면 멈춘다. 있는 .env 는 덮어쓰지 않는다.

set -euo pipefail

SERVERS=(auth game board billing)
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

# 컨테이너가 아직 돌고 있는가
running() {
  [[ "$(docker inspect -f '{{.State.Running}}' "$(container_of "$1")")" == "true" ]]
}

# 서버 넷이 모두 healthy 가 될 때까지 기다린다. 서버가 죽거나 시간이 지나면 실패한다.
wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS)) server pending
  while ((SECONDS < deadline)); do
    pending=0
    for server in "${SERVERS[@]}"; do
      if ! running "${server}-server"; then
        echo "${server}-server 가 죽었다" >&2
        return 1
      fi
      [[ "$(health_of "${server}-server")" == "healthy" ]] || pending=$((pending + 1))
    done
    if ((pending == 0)); then
      echo "서버 넷이 healthy 다"
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

not_root() {
  [[ "$(compose exec -T "$1" id -u)" != "0" ]]
}

no_env_file_in_image() {
  compose exec -T "$1" test ! -e /app/.env
}

check() {
  local server jwks=http://auth-server:8000/api/v1/auth/jwks
  for server in "${SERVERS[@]}"; do
    report "${server}-migrate 가 성공했다" migrated "$server"
    report "${server}-server 가 root 가 아니다" not_root "${server}-server"
    report "${server}-server 의 이미지에 .env 가 없다" no_env_file_in_image "${server}-server"
  done
  report "바깥에서 인증 서버에 닿는다" reachable_from_host http://127.0.0.1:8000/api/v1/auth/jwks
  report "바깥에서 게임 서버에 닿는다" reachable_from_host http://127.0.0.1:8001/health/ready
  report "바깥에서 게시판 서버에 닿는다" reachable_from_host http://127.0.0.1:8002/health/ready
  report "바깥에서 결제 서버에 닿는다" reachable_from_host http://127.0.0.1:8003/health/ready
  report "관리자 화면의 CSS 를 내준다" reachable_from_host http://127.0.0.1:8000/static/admin/css/base.css
  report "게임 서버가 인증 서버의 공개키를 받는다" reachable_from game-server "$jwks"
  report "게시판 서버가 인증 서버의 공개키를 받는다" reachable_from board-server "$jwks"
  report "결제 서버가 인증 서버의 공개키를 받는다" reachable_from billing-server "$jwks"
  report "인증 서버가 결제 서버에 닿는다" reachable_from auth-server http://billing-server:8003/health
  report "게임 서버가 결제 서버에 닿는다" reachable_from game-server http://billing-server:8003/health
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
    *)
      echo "사용: $0 prepare | up | check | logs | down" >&2
      return 2 ;;
  esac
}

main "$@"
