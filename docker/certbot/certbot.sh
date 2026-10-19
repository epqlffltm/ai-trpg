#!/bin/sh
# docker/certbot/certbot.sh
#
# staging 의 인증서(Let's Encrypt)를 받고 갱신한다(#451). docker-compose.staging.yml 의 certbot 이 entrypoint 로 부른다.
#
#   사용: certbot.sh issue [certbot 의 옵션...] | renew | loop
#     issue  처음 한 번 받는다. nginx 가 아직 없을 때라 certbot 이 직접 80 을 듣는다(standalone).
#            VM 에서 프록시를 띄우기 전에 부른다. 뒤에 붙인 옵션은 certbot 에 그대로 넘긴다(먼저 --dry-run 으로 시험한다):
#              docker compose run --rm -p 80:80 certbot issue --dry-run
#              docker compose run --rm -p 80:80 certbot issue
#     renew  한 번 갱신한다. 남은 날짜가 30일보다 많으면 아무것도 하지 않는다.
#            nginx 가 확인 파일을 내준다(webroot, docker/nginx/staging/default.conf.template 의 /.well-known/acme-challenge/)
#     loop   12시간마다 renew 를 부른다. compose 가 띄워 두는 모양이다(기본)
#
# 받거나 갱신하면 deploy-hook.sh 가 인증서를 nginx 가 읽는 곳(/tls)으로 옮긴다. nginx 는 파일이 바뀐 것을 보고 다시 읽는다
# (docker/nginx/staging/start.sh). 이 컨테이너는 nginx 에 신호를 보내지 않는다. Docker 소켓을 받지 않는다.
#
# 처음에 standalone 으로 받아도, renew 가 --webroot 를 주므로 갱신 설정(/etc/letsencrypt/renewal/)이 webroot 로 바뀐다.

set -eu

# nginx 와 함께 쓰는 확인 파일의 폴더. compose 의 볼륨(acme)이다
WEBROOT=/var/www/certbot
# 받거나 갱신한 뒤에 부르는 것. certbot 이 RENEWED_LINEAGE(받은 인증서의 폴더)를 넘긴다
DEPLOY_HOOK="sh /opt/certbot/deploy-hook.sh"
# loop 의 간격(초). Let's Encrypt 는 하루에 두 번 묻기를 권한다
RENEW_SECONDS="${RENEW_SECONDS:-43200}"

usage() {
  echo "사용: $0 issue [certbot 의 옵션...] | renew | loop" >&2
}

# 처음 받기. 도메인 하나, 인증서의 이름도 도메인이다(/etc/letsencrypt/live/<도메인>/)
issue() {
  : "${DOMAIN:?루트 .env 에 DOMAIN 을 적는다}"
  : "${ACME_EMAIL:?루트 .env 에 ACME_EMAIL 을 적는다}"
  certbot certonly --standalone --non-interactive --agree-tos --no-eff-email \
    --email "$ACME_EMAIL" --cert-name "$DOMAIN" -d "$DOMAIN" \
    --deploy-hook "$DEPLOY_HOOK" "$@"
}

renew() {
  certbot renew --non-interactive --no-random-sleep-on-renew \
    --webroot -w "$WEBROOT" --deploy-hook "$DEPLOY_HOOK"
}

# 갱신이 실패해도 멈추지 않고 다음 바퀴에 다시 한다. 실패는 certbot 의 줄로 남고, 남은 날짜가 14일 아래로 내려가면
# 이 컨테이너가 unhealthy 가 된다(cert_check.py)
loop() {
  while :; do
    renew || echo "갱신에 실패했다. ${RENEW_SECONDS}초 뒤에 다시 한다" >&2
    sleep "$RENEW_SECONDS"
  done
}

main() {
  command="${1:-loop}"
  [ "$#" -gt 0 ] && shift
  case "$command" in
    issue) issue "$@" ;;
    renew) renew ;;
    loop) loop ;;
    *)
      usage
      return 2 ;;
  esac
}

main "$@"
