#!/bin/sh
# docker/nginx/staging/start.sh
#
# staging 의 프록시를 띄운다(#451). docker-compose.staging.yml 의 proxy 가 entrypoint 로 부른다(sh 로 부르므로 실행 권한이 필요 없다).
#
#   1. 인증서와 허용 주소를 지켜보는 고리를 뒤에서 돌린다. 둘 중 하나라도 바뀌면 nginx 를 다시 읽힌다(nginx -s reload)
#   2. 이미지의 원래 시작 스크립트(/docker-entrypoint.sh)에 넘긴다. 틀(*.template)을 채우고 nginx 를 띄운다
#
# 다시 읽히는 까닭:
#   - certbot 은 다른 컨테이너라 nginx 에 신호를 보낼 수 없다. Docker 소켓을 주면 그 컨테이너가 VM 의 root 와 같아진다.
#     그래서 nginx 가 제 쪽에서 인증서 파일이 바뀐 것을 보고 다시 읽는다
#   - 허용 주소의 파일을 고친 뒤 손으로 다시 읽히는 것을 잊지 않게 한다. 지금 바로 읽히려면:
#       docker compose exec proxy nginx -s reload
#
# 다시 읽을 때 설정이 틀렸으면(허용 주소의 줄을 잘못 적었으면) nginx 는 앞의 설정으로 계속 돌고 오류 로그에 남긴다.
# 고치면 파일이 다시 바뀌므로 다음 바퀴에 다시 읽는다.

set -eu

# 지켜보는 간격(초). CI 는 짧게 준다
WATCH_SECONDS="${WATCH_SECONDS:-60}"
# 이미지의 원래 시작 스크립트. 시험할 때만 바꾼다
NGINX_ENTRYPOINT="${NGINX_ENTRYPOINT:-/docker-entrypoint.sh}"
TLS_DIR="${TLS_DIR:-/etc/nginx/tls}"
ALLOWLIST_DIR="${ALLOWLIST_DIR:-/etc/nginx/allowlist}"

# 지켜보는 파일들의 지문(이름, 바뀐 시각, 크기). 없는 파일은 빠진다. 파일이 생기거나 지워져도 지문이 바뀐다
fingerprint() {
  for file in "$TLS_DIR"/fullchain.pem "$TLS_DIR"/privkey.pem "$ALLOWLIST_DIR"/*.conf; do
    [ -e "$file" ] && stat -c '%n %Y %s' "$file"
  done
  return 0
}

# 다시 읽었다는 줄. 공통 규격(docs/observability.md)의 JSON 이다. 밀리초는 셸에서 얻지 못해 000 이다
log_reloaded() {
  printf '{"timestamp":"%s.000Z","level":"info","service":"proxy","environment":"%s","version":"%s","message":"인증서나 허용 주소가 바뀌어 설정을 다시 읽었다","operation":"proxy.reload"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%S)" "${APP_ENVIRONMENT:-}" "${APP_VERSION:-}"
}

# 지문이 바뀔 때마다 nginx 를 다시 읽힌다. nginx 가 아직 뜨지 않았으면(pid 파일이 없으면) 다음 바퀴에 다시 본다
watch_and_reload() {
  last="$(fingerprint)"
  while sleep "$WATCH_SECONDS"; do
    now="$(fingerprint)"
    [ "$now" = "$last" ] && continue
    if nginx -s reload 2>/dev/null; then
      last="$now"
      log_reloaded
    fi
  done
}

watch_and_reload &
exec "$NGINX_ENTRYPOINT" "$@"
