#!/usr/bin/env bash
# .github/scripts/changed-servers.test.sh
#
# 검사할 서버를 고르는 규칙(changed-servers.sh)을 검사한다. 관문 워크플로가 고르기 전에 먼저 돌린다.
# 규칙이 틀려 검사를 건너뛰면, 깨진 서버가 초록으로 머지된다.

set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=changed-servers.sh
source "$(dirname "$0")/changed-servers.sh"

failures=0

# 바뀐 파일들(인자)로 고른 결과가 기대(마지막 인자)와 같은지 본다. 기대는 "auth game" 처럼 고를 서버들이다.
expect() {
  local name="$1" expected="$2"; shift 2
  local actual
  actual="$(printf '%s\n' "$@" | select_servers | awk -F= '$2=="true"{printf "%s ", $1}' | sed 's/ $//')"
  if [[ "$actual" == "$expected" ]]; then
    echo "ok   $name"
  else
    echo "FAIL $name: 기대 [$expected], 실제 [$actual]"
    failures=$((failures + 1))
  fi
}

expect "한 서버만 바뀌면 그 서버" "board" "board-server/src/main.ts"
expect "두 서버가 바뀌면 둘" "auth board" "auth-server/accounts/tokens.py" "board-server/README.md"
expect "서버의 워크플로가 바뀌면 그 서버" "game" ".github/workflows/game-server.yml"
expect "DB 초기화 스크립트는 모두" "auth game board billing notification" "docker/postgres/init/06-x.sql"
expect "compose 파일은 모두" "auth game board billing notification" "docker-compose.yml"
expect "staging 의 compose 파일도 모두" "auth game board billing notification" "docker-compose.staging.yml"
expect "staging 의 .env 를 만드는 도구도 모두" "auth game board billing notification" "tools/staging_env.py"
expect "패치를 적용하는 도구는 고르지 않는다" "" "tools/apply_ai_update.py"
expect "프록시의 설정은 모두" "auth game board billing notification" "docker/nginx/templates/default.conf.template"
expect "crontab 은 모두" "auth game board billing notification" "docker/cron/auth.crontab"
expect "서버의 Dockerfile 은 그 서버" "billing" "billing-server/Dockerfile"
expect "알림 서버가 바뀌면 알림 서버" "notification" "notification-server/app/main.py"
expect "알림 서버의 워크플로가 바뀌면 알림 서버" "notification" ".github/workflows/notification-server.yml"
expect "관문 워크플로는 모두" "auth game board billing notification" ".github/workflows/ci.yml"
expect "관문의 스크립트는 모두" "auth game board billing notification" ".github/scripts/changed-servers.sh"
expect "함께 쓰는 ruff 규칙은 파이썬 서버 셋" "auth game notification" "ruff.toml"
expect "서버 안의 ruff.toml 같은 이름은 그 서버만" "billing" "billing-server/ruff.toml"
expect "문서만 바뀌면 아무것도" "" "README.md" "docs/observability.md"
expect "아무것도 안 바뀌면 아무것도" ""
expect "이름이 비슷한 다른 폴더는 고르지 않는다" "" "board-server-old/x" "authserver/x" "notification-server-old/x"
expect "폴더 이름만 같은 다른 경로는 고르지 않는다" "" "docs/board-server/x.md"

all="$(select_all | tr '\n' ' ')"
if [[ "$all" == "auth=true game=true board=true billing=true notification=true " ]]; then
  echo "ok   모를 때는 모두"
else
  echo "FAIL 모를 때는 모두: [$all]"
  failures=$((failures + 1))
fi

unknown="$(main 0000000000000000000000000000000000000000 HEAD 2>/dev/null | tr '\n' ' ')"
if [[ "$unknown" == "auth=true game=true board=true billing=true notification=true " ]]; then
  echo "ok   기준 커밋을 찾지 못하면 모두"
else
  echo "FAIL 기준 커밋을 찾지 못하면 모두: [$unknown]"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "$failures 개 실패"
  exit 1
fi
echo "모두 통과"
