#!/usr/bin/env bash
# .github/scripts/changed-servers.test.sh
#
# 검사할 서버를 고르는 규칙(changed-servers.sh)을 검사한다. 관문 워크플로가 고르기 전에 먼저 돌린다.
# 규칙이 틀려 검사를 건너뛰면, 깨진 서버가 초록으로 머지된다.

set -euo pipefail

# shellcheck source-path=SCRIPTDIR source=changed-servers.sh
source "$(dirname "$0")/changed-servers.sh"

failures=0

# 바뀐 파일들(인자)로 고른 결과가 기대(마지막 인자)와 같은지 본다. 기대는 "auth trpg" 처럼 고를 서버들이다.
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
expect "서버의 워크플로가 바뀌면 그 서버" "trpg" ".github/workflows/trpg-server.yml"
expect "DB 초기화 스크립트는 모두" "auth trpg board billing notification asset chat story shared web" "docker/postgres/init/06-x.sql"
expect "compose 파일은 모두" "auth trpg board billing notification asset chat story shared web" "docker-compose.yml"
expect "staging 의 compose 파일도 모두" "auth trpg board billing notification asset chat story shared web" "docker-compose.staging.yml"
expect "staging 의 .env 를 만드는 도구도 모두" "auth trpg board billing notification asset chat story shared web" "tools/staging_env.py"
expect ".env 의 비밀을 채우는 도구도 모두" "auth trpg board billing notification asset chat story shared web" "tools/fill_env.py"
expect "패치를 적용하는 도구는 고르지 않는다" "" "tools/apply_ai_update.py"
expect "프록시의 설정은 모두" "auth trpg board billing notification asset chat story shared web" "docker/nginx/templates/default.conf.template"
expect "crontab 은 모두" "auth trpg board billing notification asset chat story shared web" "docker/cron/auth.crontab"
expect "서버의 Dockerfile 은 그 서버" "billing" "billing-server/Dockerfile"
expect "알림 서버가 바뀌면 알림 서버" "notification" "notification-server/app/main.py"
expect "알림 서버의 워크플로가 바뀌면 알림 서버" "notification" ".github/workflows/notification-server.yml"
expect "관문 워크플로는 모두" "auth trpg board billing notification asset chat story shared web" ".github/workflows/ci.yml"
expect "관문의 스크립트는 모두" "auth trpg board billing notification asset chat story shared web" ".github/scripts/changed-servers.sh"
expect "함께 쓰는 ruff 규칙은 파이썬 서버들과 공용 코드" "auth trpg notification asset chat story shared" "ruff.toml"
expect "서버 안의 ruff.toml 같은 이름은 그 서버만" "billing" "billing-server/ruff.toml"
expect "문서만 바뀌면 아무것도" "" "README.md" "docs/observability.md"
expect "아무것도 안 바뀌면 아무것도" ""
expect "이름이 비슷한 다른 폴더는 고르지 않는다" "" "board-server-old/x" "authserver/x" "notification-server-old/x" "asset-server-old/x" "chat-server-old/x" "story-server-old/x"
expect "폴더 이름만 같은 다른 경로는 고르지 않는다" "" "docs/board-server/x.md"
expect "서버의 API 목록은 그 서버과 화면" "trpg web" "docs/api/trpg.openapi.json"
expect "asset 서버가 바뀌면 asset 서버" "asset" "asset-server/app/main.py"
expect "asset 서버의 워크플로가 바뀌면 asset 서버" "asset" ".github/workflows/asset-server.yml"
expect "asset 서버의 API 목록은 asset 서버과 화면" "asset web" "docs/api/asset.openapi.json"
expect "API 목록의 안내는 아무것도" "" "docs/api/README.md"
expect "화면이 바뀌면 화면" "web" "web/apps/web/src/main.tsx"
expect "화면의 워크플로가 바뀌면 화면" "web" ".github/workflows/web.yml"
expect "동의 문서가 바뀌면 화면" "web" "docs/legal/terms.md"
expect "web 이라는 이름의 다른 폴더는 고르지 않는다" "" "docs/web/x.md" "web-old/x"
expect "chat 서버가 바뀌면 chat 서버" "chat" "chat-server/app/main.py"
expect "chat 서버의 워크플로가 바뀌면 chat 서버" "chat" ".github/workflows/chat-server.yml"
expect "chat 서버의 API 목록은 chat 서버과 화면" "chat web" "docs/api/chat.openapi.json"
expect "story 서버가 바뀌면 story 서버" "story" "story-server/app/main.py"
expect "story 서버의 워크플로가 바뀌면 story 서버" "story" ".github/workflows/story-server.yml"
expect "story 서버의 API 목록은 story 서버과 화면" "story web" "docs/api/story.openapi.json"
expect "API 목록을 뽑는 도구는 목록을 내는 서버" "auth trpg board billing notification asset chat story" "tools/export_openapi.py"
expect "인증 서버의 API 목록은 인증 서버과 화면" "auth web" "docs/api/auth.openapi.json"
expect "결제 서버의 손으로 쓴 목록은 결제 서버" "billing" "billing-server/api/openapi.yaml"
expect "결제 서버의 API 목록은 결제 서버과 화면" "billing web" "docs/api/billing.openapi.json"
expect "게시판 서버의 API 목록은 게시판 서버과 화면" "board web" "docs/api/board.openapi.json"

# 공용 코드를 쓰는 서버는 서버의 pyproject.toml 의 경로 의존으로 고른다. 가짜 서버 폴더로 본다
fake_root="$(mktemp -d)"
trap 'rm -rf "$fake_root"' EXIT
mkdir -p "$fake_root/trpg-server" "$fake_root/notification-server" "$fake_root/asset-server" "$fake_root/board-server" \
  "$fake_root/chat-server" "$fake_root/story-server"
printf '[tool.uv.sources]\nserver-core = { path = "../shared/server-core", editable = true }\n' \
  > "$fake_root/notification-server/pyproject.toml"
printf '[tool.uv.sources]\nserver-core = { path = "../shared/server-core", editable = true }\nai-core = { path = "../shared/ai-core" }\n' \
  > "$fake_root/trpg-server/pyproject.toml"
printf '[project]\nname = "asset-server"\n' > "$fake_root/asset-server/pyproject.toml"
printf '[tool.uv.sources]\nserver-core = { path = "../shared/server-core", editable = true }\n' \
  > "$fake_root/chat-server/pyproject.toml"
printf '[tool.uv.sources]\nserver-core = { path = "../shared/server-core", editable = true }\n' \
  > "$fake_root/story-server/pyproject.toml"
SERVER_ROOT="$fake_root"
expect "공용 패키지가 바뀌면 공용 코드와 그것을 쓰는 서버" "trpg notification chat story shared" "shared/server-core/src/server_core/settings.py"
expect "다른 공용 패키지는 그것을 쓰는 서버만" "trpg shared" "shared/ai-core/pyproject.toml"
expect "아무도 쓰지 않는 공용 패키지는 공용 코드만" "shared" "shared/content-core/src/x.py"
expect "이름이 비슷한 패키지는 쓰는 것으로 보지 않는다" "shared" "shared/server/x.py"
expect "공용 코드의 안내는 공용 코드만" "shared" "shared/README.md"
expect "공용 코드의 워크플로는 공용 코드" "shared" ".github/workflows/shared.yml"
expect "shared 라는 이름의 다른 폴더는 고르지 않는다" "" "docs/shared/x.md" "shared-old/x"
SERVER_ROOT=.

all="$(select_all | tr '\n' ' ')"
if [[ "$all" == "auth=true trpg=true board=true billing=true notification=true asset=true chat=true story=true shared=true web=true " ]]; then
  echo "ok   모를 때는 모두"
else
  echo "FAIL 모를 때는 모두: [$all]"
  failures=$((failures + 1))
fi

unknown="$(main 0000000000000000000000000000000000000000 HEAD 2>/dev/null | tr '\n' ' ')"
if [[ "$unknown" == "auth=true trpg=true board=true billing=true notification=true asset=true chat=true story=true shared=true web=true " ]]; then
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
