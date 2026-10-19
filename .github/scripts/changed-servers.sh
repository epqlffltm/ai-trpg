#!/usr/bin/env bash
# .github/scripts/changed-servers.sh
#
# PR 에서 바뀐 파일을 보고 검사할 서버를 고른다. 관문 워크플로(.github/workflows/ci.yml)가 부른다.
#
#   사용: changed-servers.sh <기준 커밋> <PR 의 커밋>
#   출력: GITHUB_OUTPUT 의 모양으로 서버마다 한 줄. auth=true, game=false, board=false, billing=true, notification=false
#
# 고르는 규칙:
#   - 서버의 폴더(auth-server/ 등)나 그 서버의 워크플로(.github/workflows/auth-server.yml)가 바뀌면 그 서버
#   - docker/ 아래(DB 초기화 스크립트, 프록시의 설정, crontab)나 compose 파일(docker-compose.yml, docker-compose.staging.yml)이
#     바뀌면 모두. 서버들의 DB 계정, 컨테이너로 띄우고 잇는 법, 주기 명령, staging 의 설정이 거기 있다.
#     .env 를 만드는 도구(tools/fill_env.py, tools/staging_env.py)도 모두다. CI(stack)가 그 도구들의 테스트를 돌리고
#     staging_env.py 로 만든 설정을 읽어 본다
#   - 관문 자신(.github/workflows/ci.yml, .github/scripts/)이 바뀌면 모두. 관문이 맞는지 모두로 확인한다
#   - 파이썬 서버들이 함께 쓰는 ruff 규칙(루트의 ruff.toml)이 바뀌면 인증, 게임, 알림
#   - 그 밖(문서, 루트 README 등)은 아무것도 고르지 않는다
#   - 바뀐 파일을 알 수 없으면(커밋을 찾지 못함) 모두. 모르면 검사하는 쪽으로 기운다
#
# 남이 만든 액션(dorny/paths-filter 등)을 쓰지 않았다. 저장소를 읽는 외부 코드를 하나 줄이고, 규칙을 여기서 다 본다.

set -euo pipefail

# 검사하는 서버들. 출력의 이름과 폴더의 이름
SERVERS=(auth game board billing notification)

# 한 서버를 고르는 경로들인가. 서버 이름과 경로를 받는다.
belongs_to() {
  local server="$1" path="$2"
  [[ "$path" == "${server}-server/"* || "$path" == ".github/workflows/${server}-server.yml" ]]
}

# 파이썬 서버들(인증, 게임, 알림)이 함께 쓰는 설정인가. 바뀌면 그 서버들의 린트와 모양 검사를 다시 돌려야 한다.
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
  local path server
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if affects_all "$path"; then
      for server in "${SERVERS[@]}"; do picked[$server]=1; done
      continue
    fi
    if python_shared "$path"; then
      picked[auth]=1
      picked[game]=1
      picked[notification]=1
    fi
    for server in "${SERVERS[@]}"; do
      if belongs_to "$server" "$path"; then picked[$server]=1; fi
    done
  done
  for server in "${SERVERS[@]}"; do
    if [[ -n "${picked[$server]:-}" ]]; then echo "${server}=true"; else echo "${server}=false"; fi
  done
}

# 모두 고른 출력.
select_all() {
  local server
  for server in "${SERVERS[@]}"; do echo "${server}=true"; done
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
