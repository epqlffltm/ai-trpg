#!/usr/bin/env bash
# .github/scripts/changed-servers.sh
#
# PR 에서 바뀐 파일을 보고 검사할 서버를 고른다. 관문 워크플로(.github/workflows/ci.yml)가 부른다.
#
#   사용: changed-servers.sh <기준 커밋> <PR 의 커밋>
#   출력: GITHUB_OUTPUT 의 모양으로 서버마다 한 줄. auth=true, trpg=false, board=false, billing=true, notification=false, asset=false,
#         chat=false.
#         공용 코드(shared/)의 검사는 shared=true, 화면(web/)의 검사는 web=true 다
#
# 고르는 규칙:
#   - 서버의 폴더(auth-server/ 등)나 그 서버의 워크플로(.github/workflows/auth-server.yml)가 바뀌면 그 서버
#     그 서버의 API 목록(docs/api/<서버>.openapi.json)도 그 서버다. 손으로 고친 목록을 api-docs 가 잡는다
#   - API 목록을 뽑는 도구(tools/export_openapi.py)가 바뀌면 목록을 내는 서버(지금은 게임, 알림, 결제, asset, 인증, 게시판, chat)
#   - docker/ 아래(DB 초기화 스크립트, 프록시의 설정, crontab)나 compose 파일(docker-compose.yml, docker-compose.staging.yml)이
#     바뀌면 모두. 서버들의 DB 계정, 컨테이너로 띄우고 잇는 법, 주기 명령, staging 의 설정이 거기 있다.
#     .env 를 만드는 도구(tools/fill_env.py, tools/staging_env.py)도 모두다. CI(stack)가 그 도구들의 테스트를 돌리고
#     staging_env.py 로 만든 설정을 읽어 본다
#   - 관문 자신(.github/workflows/ci.yml, .github/scripts/)이 바뀌면 모두. 관문이 맞는지 모두로 확인한다
#   - 파이썬 서버들이 함께 쓰는 ruff 규칙(루트의 ruff.toml)이 바뀌면 인증, 게임, 알림, asset, chat 과 공용 코드
#   - 공용 코드(shared/<패키지>/)가 바뀌면 공용 코드의 검사(shared)와, 그 패키지를 쓰는 서버들.
#     쓰는 서버는 서버마다 pyproject.toml 의 경로 의존(path = "../shared/<패키지>")을 읽어 고른다. 따로 표를 두지 않는다.
#     새 서버가 공용 코드를 쓰기 시작하면 저절로 잡힌다(docs/architecture/shared-code.md 의 "버전과 CI")
#   - 화면의 폴더(web/)나 그 워크플로(.github/workflows/web.yml)가 바뀌면 화면(web). 화면은 서버의 API 목록에서 타입을 만들므로
#     API 목록(docs/api/*.openapi.json)이 바뀌어도 화면이다. 모두를 고르는 경로(docker/ 등)도 화면을 고른다(프록시의 이미지가 화면을 담는다)
#   - 그 밖(문서, 루트 README 등)은 아무것도 고르지 않는다
#   - 바뀐 파일을 알 수 없으면(커밋을 찾지 못함) 모두. 모르면 검사하는 쪽으로 기운다
#
# 남이 만든 액션(dorny/paths-filter 등)을 쓰지 않았다. 저장소를 읽는 외부 코드를 하나 줄이고, 규칙을 여기서 다 본다.

set -euo pipefail

# 검사하는 서버들. 출력의 이름과 폴더의 이름
SERVERS=(auth trpg board billing notification asset chat)
# 출력하는 것 모두. 서버들과 공용 코드의 검사(shared, .github/workflows/shared.yml), 화면의 검사(web, .github/workflows/web.yml)
OUTPUTS=("${SERVERS[@]}" shared web)
# 서버의 폴더들이 있는 곳. 테스트가 가짜 pyproject.toml 을 둔 곳으로 바꾼다
SERVER_ROOT="${SERVER_ROOT:-.}"

# 한 서버를 고르는 경로들인가. 서버 이름과 경로를 받는다.
belongs_to() {
  local server="$1" path="$2"
  [[ "$path" == "${server}-server/"* || "$path" == ".github/workflows/${server}-server.yml" ||
    "$path" == "docs/api/${server}.openapi.json" ]]
}

# 공용 코드의 경로인가. 공용 코드의 폴더나 그 워크플로다.
shared_path() {
  [[ "$1" == shared/* || "$1" == ".github/workflows/shared.yml" ]]
}

# 화면의 경로인가. 화면의 폴더, 그 워크플로, 화면이 타입을 만드는 서버의 API 목록이다.
web_path() {
  [[ "$1" == web/* || "$1" == ".github/workflows/web.yml" || "$1" == docs/api/*.openapi.json ]]
}

# 공용 코드의 경로에서 패키지의 이름을 꺼낸다(shared/server-core/src/x.py -> server-core). 패키지 밖이면 비어 있다.
shared_package() {
  local rest="${1#shared/}"
  if [[ "$1" == shared/*/* ]]; then echo "${rest%%/*}"; fi
}

# 그 공용 패키지를 쓰는 서버들. 서버의 pyproject.toml 에 그 패키지의 경로 의존이 있으면 쓰는 서버다.
shared_users() {
  local package="$1" server
  for server in "${SERVERS[@]}"; do
    if grep -qF "path = \"../shared/${package}\"" "${SERVER_ROOT}/${server}-server/pyproject.toml" 2>/dev/null; then
      echo "$server"
    fi
  done
}

# API 목록을 뽑는 도구인가. 바뀌면 목록을 내는 서버들의 api-docs 를 다시 돌린다(tools/export_openapi.py 의 SOURCES)
openapi_tool() {
  [[ "$1" == tools/export_openapi.py || "$1" == tools/test_export_openapi.py ]]
}

# 파이썬 서버들(인증, 게임, 알림, asset, chat)이 함께 쓰는 설정인가. 바뀌면 그 서버들의 린트와 모양 검사를 다시 돌려야 한다.
python_shared() {
  [[ "$1" == "ruff.toml" ]]
}

# 모두 고르는 경로인가.
affects_all() {
  local path="$1"
  [[ "$path" == docker/* || "$path" == "docker-compose.yml" || "$path" == "docker-compose.staging.yml" ||
    "$path" == tools/fill_env.py || "$path" == tools/test_fill_env.py ||
    "$path" == tools/staging_env.py || "$path" == tools/test_staging_env.py ||
    "$path" == ".github/workflows/ci.yml" || "$path" == .github/scripts/* ]]
}

# 바뀐 파일들(표준 입력, 한 줄에 하나)을 읽어 서버마다 true/false 를 찍는다.
select_servers() {
  local -A picked=()
  local path server package
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if affects_all "$path"; then
      for server in "${OUTPUTS[@]}"; do picked[$server]=1; done
      continue
    fi
    if openapi_tool "$path"; then
      picked[trpg]=1
      picked[notification]=1
      picked[billing]=1
      picked[asset]=1
      picked[auth]=1
      picked[board]=1
      picked[chat]=1
    fi
    if python_shared "$path"; then
      picked[auth]=1
      picked[trpg]=1
      picked[notification]=1
      picked[asset]=1
      picked[chat]=1
      picked[shared]=1
    fi
    if web_path "$path"; then
      picked[web]=1
    fi
    if shared_path "$path"; then
      picked[shared]=1
      package="$(shared_package "$path")"
      if [[ -n "$package" ]]; then
        for server in $(shared_users "$package"); do picked[$server]=1; done
      fi
    fi
    for server in "${SERVERS[@]}"; do
      if belongs_to "$server" "$path"; then picked[$server]=1; fi
    done
  done
  for server in "${OUTPUTS[@]}"; do
    if [[ -n "${picked[$server]:-}" ]]; then echo "${server}=true"; else echo "${server}=false"; fi
  done
}

# 모두 고른 출력.
select_all() {
  local server
  for server in "${OUTPUTS[@]}"; do echo "${server}=true"; done
}

# 두 커밋 사이에 바뀐 파일. PR 이 갈라져 나온 곳(merge base)부터 센다(점 셋). 그사이 main 에 들어간 남의 변경은 세지 않는다.
changed_files() {
  git diff --name-only "$1...$2"
}

main() {
  local base="${1:-}" head="${2:-}" files
  if [[ -z "$base" || -z "$head" ]] || ! files="$(changed_files "$base" "$head" 2>/dev/null)"; then
    echo "바뀐 파일을 알 수 없어 모두 검사한다" >&2
    select_all
    return
  fi
  printf '%s\n' "$files" | select_servers
}

# 테스트가 이 파일을 불러 함수만 쓸 때는 main 을 부르지 않는다
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
