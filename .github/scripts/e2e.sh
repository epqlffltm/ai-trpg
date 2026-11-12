#!/usr/bin/env bash
# .github/scripts/e2e.sh
#
# 종단간 테스트(web/e2e, P2-4)의 스택을 띄우고 채우고 브라우저로 돌린다. 관문 워크플로(.github/workflows/ci.yml 의 e2e)가 부른다.
# 연기 검사(stack-smoke.sh)와 따로 돈다. 그쪽은 설정이 실제와 같은지를, 이쪽은 화면에서 한 흐름이 끝까지 가는지를 본다.
#
#   사용: e2e.sh prepare | up | seed | test | logs | down
#     prepare  설정 파일(.env 아홉)과 JWT 키를 stack-smoke.sh 와 같은 방법으로 만들고, Mailpit 의 자체 서명 인증서를 만든다
#     up       docker-compose.yml 에 docker-compose.e2e.yml 을 겹쳐 서버들(프로필 app)을 띄우고 healthy 를 기다린다.
#              로그와 메트릭 모으기(observability)는 띄우지 않는다
#     seed     가짜 모델을 모델 목록에 넣고 켜고(게임·chat·story 서버), 그 가격을 결제 서버의 가격표에 넣고(Go 의 cmd/prices),
#              견본 계정 둘과 견본 시나리오를 만들고(tools/dev_seed.py, 테이블은 열지 않는다),
#              견본 계정이 공개 캐릭터와 세계관을 게시한다(tools/e2e/seed_works.py)
#     test     Playwright 로 web/e2e 를 돌린다. 브라우저는 워크플로가 먼저 받아 둔다
#     logs     모든 컨테이너의 로그. 실패했을 때 부른다
#     down     컨테이너와 볼륨, 만든 인증서를 지운다
#
# PC 에서 부르지 않는다. prepare 는 CI 가 아니면 멈춘다(stack-smoke.sh 의 prepare 와 같다).

set -euo pipefail

FILES=(-f docker-compose.yml -f docker-compose.e2e.yml)
# 기다릴 서비스. 서버들과 프록시, 메일과 크레딧을 맡기는 워커, 가짜 모델
WAIT_FOR=(auth-server trpg-server board-server billing-server notification-server asset-server chat-server story-server
  proxy auth-mail auth-welcome-credits stub-llm)
WAIT_SECONDS=240
PROXY=http://127.0.0.1:8080
MAILPIT=http://127.0.0.1:8025
CERTS=e2e-certs
# 서버마다 켤 가짜 모델의 이름표(tools/e2e/local-models.toml)
MODELS=("trpg-server e2e-narrator" "chat-server e2e-chat" "story-server e2e-story")
# 그 가격(결제 서버의 가격표). 서술은 1인 1라운드, chat·story 는 말 한 번의 크레딧
PRICES=("narration.e2e-narrator.i0.o0 10" "chat.e2e-chat.i0.o0 10" "story.e2e-story.i0.o0 10")
# 견본 계정의 비밀번호(tools/dev_seed.py 의 DEFAULT_PASSWORD 와 같다). 테스트가 E2E_SEED_PASSWORD 로 받는다
SEED_PASSWORD=seed-pass-2026

compose() {
  docker compose "${FILES[@]}" --profile app "$@"
}

# 루트 .env 의 한 값
root_env() {
  sed -n "s/^$1=//p" .env | tail -n 1
}

# Mailpit 이 STARTTLS 에 쓰는 자체 서명 인증서와, 인증의 프로세스가 믿을 묶음(시스템의 것 + 이 인증서)
write_mail_certs() {
  mkdir -p "$CERTS"
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=mailpit" -addext "subjectAltName=DNS:mailpit" \
    -keyout "$CERTS/mailpit.key" -out "$CERTS/mailpit.crt" 2>/dev/null
  cat /etc/ssl/certs/ca-certificates.crt "$CERTS/mailpit.crt" > "$CERTS/trust.pem"
  # 컨테이너의 사용자(10001, Mailpit 의 사용자)가 읽는다. 이 실행에서만 쓰는 열쇠다
  chmod 644 "$CERTS"/*
}

prepare() {
  bash .github/scripts/stack-smoke.sh prepare
  write_mail_certs
}

# 컨테이너의 상태 확인 결과(healthy, starting, unhealthy). 상태 확인이 없으면 돌고 있는가(running, exited). 아직 없으면 missing
health_of() {
  local id
  id="$(compose ps -a -q "$1")"
  [[ -n "$id" ]] || { echo missing; return 0; }
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id"
}

wait_healthy() {
  local deadline=$((SECONDS + WAIT_SECONDS)) service pending
  while ((SECONDS < deadline)); do
    pending=0
    for service in "${WAIT_FOR[@]}"; do
      case "$(health_of "$service")" in
        healthy) ;;
        exited | dead) echo "$service 가 멈췄다" >&2; return 1 ;;
        *) pending=$((pending + 1)) ;;
      esac
    done
    if ((pending == 0)); then
      echo "서버들과 프록시, 워커, 가짜 모델이 healthy 다"
      return 0
    fi
    sleep 3
  done
  echo "${WAIT_SECONDS}초 안에 healthy 가 되지 않았다" >&2
  compose ps -a >&2
  return 1
}

# 이미지마다 만들 서비스 하나씩(stack-smoke.sh 의 build_targets 와 같은 까닭). 한 이미지를 여러 서비스가 함께 쓴다
build_targets() {
  compose config --format json | python3 -c '
import json, sys
first = {}
for name, service in json.load(sys.stdin)["services"].items():
    if "build" in service:
        first.setdefault(service.get("image", name), name)
print(*first.values())'
}

# 이미지 저장소가 잠깐 답하지 않으면 쉬었다가 다시 한다(stack-smoke.sh 의 with_retries 와 같다)
with_retries() {
  local attempt=1
  until "$@"; do
    if ((attempt >= 3)); then
      echo "3 번 해도 되지 않았다: ${*:1:2}" >&2
      return 1
    fi
    sleep $((15 * attempt))
    attempt=$((attempt + 1))
  done
}

up() {
  local listed targets
  listed="$(build_targets)"
  read -ra targets <<<"$listed"
  with_retries compose pull --ignore-buildable --quiet
  with_retries compose build "${targets[@]}"
  compose up -d
  wait_healthy
}

# 서버마다 모델 목록에 가짜 모델을 들여오고 제 것을 켠다
seed_models() {
  local line server model
  for line in "${MODELS[@]}"; do
    read -r server model <<<"$line"
    compose exec -T "$server" python -m scripts.models sync --file /e2e/local-models.toml
    compose exec -T "$server" python -m scripts.models enable "$model"
  done
}

# 결제 서버의 가격표에 가짜 모델의 값을 넣는다. 이미지에 cmd/prices 가 없어 러너의 Go 로 돌린다.
# DB 는 compose 가 이 PC 에 연 포트로 닿는다
seed_prices() {
  local url line
  url="postgres://billing:$(root_env BILLING_DB_PASSWORD)@127.0.0.1:${POSTGRES_PORT:-5432}/trpg"
  for line in "${PRICES[@]}"; do
    read -r code credits <<<"$line"
    (cd billing-server && DATABASE_URL="$url" go run ./cmd/prices set "$code" "$credits" -tier standard -reason "e2e")
  done
}

# 견본 계정 둘과 견본 시나리오. 시나리오의 서술 모델은 고를 수 있는 모델이어야 한다.
# 게임 서버는 결제 서버의 가격 목록을 60초 동안 받아 둔다(server_core/billing/price_list.py). 가격을 넣기 전에 받아 둔 것이
# 있으면 그동안 가짜 모델을 고를 수 없다. 그래서 15초마다 다시 해 본다(dev_seed.py 는 몇 번 돌려도 같다)
seed_samples() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    if python3 tools/dev_seed.py --proxy "$PROXY" --password "$SEED_PASSWORD" --no-table; then
      return 0
    fi
    echo "견본을 채우지 못했다. 15초 뒤에 다시 한다($attempt/6)" >&2
    sleep 15
  done
  return 1
}

# chat·story 의 테스트가 쓸 공개 캐릭터와 세계관. 견본 계정이 있어야 한다(seed_samples 뒤)
seed_works() {
  python3 tools/e2e/seed_works.py --proxy "$PROXY" --password "$SEED_PASSWORD"
}

seed() {
  seed_prices
  seed_models
  seed_samples
  seed_works
}

test_web() {
  (cd web && E2E_BASE_URL="$PROXY" E2E_MAILPIT_URL="$MAILPIT" E2E_SEED_PASSWORD="$SEED_PASSWORD" \
    npx playwright test -c e2e)
}

logs() {
  compose ps -a
  compose logs --no-color
}

down() {
  compose down -v
  rm -rf "$CERTS"
}

main() {
  case "${1:-}" in
    prepare | up | seed | logs | down) "$1" ;;
    test) test_web ;;
    *)
      echo "사용: $0 prepare | up | seed | test | logs | down" >&2
      return 2 ;;
  esac
}

main "$@"
