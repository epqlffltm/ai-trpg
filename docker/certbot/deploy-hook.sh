#!/bin/sh
# docker/certbot/deploy-hook.sh
#
# certbot 이 인증서를 받거나 갱신한 뒤에 부른다(certbot.sh 의 --deploy-hook). 인증서와 키를 nginx 가 읽는 곳(/tls)에 옮긴다.
#
# 옮기는 까닭: certbot 은 /etc/letsencrypt/live 와 archive 를 root 만 읽게(0700) 만든다.
# 프록시(nginx-unprivileged)는 root 가 아니라(101) 그대로는 읽지 못한다. 그래서 두 파일만 그 사용자의 것으로 옮긴다.
# 프록시는 /tls 만 읽기 전용으로 붙인다. Let's Encrypt 의 계정 키와 지난 인증서는 프록시에 닿지 않는다.
#
# 임시 이름으로 쓴 뒤 이름을 바꾼다(mv). nginx 가 반쯤 쓴 파일을 읽지 않는다.
# 키를 먼저 바꾸므로 잠깐 새 키와 옛 인증서가 함께 있을 수 있다. 그 사이에 다시 읽으면 nginx 는 앞의 설정으로 계속 돌고,
# 인증서가 바뀐 다음 바퀴에 다시 읽는다(docker/nginx/staging/start.sh).

set -eu

: "${RENEWED_LINEAGE:?certbot 이 넘기는 RENEWED_LINEAGE 가 없다}"
TLS_DIR="${TLS_DIR:-/tls}"
# 프록시 이미지(nginx-unprivileged)의 사용자
NGINX_UID="${NGINX_UID:-101}"

# 파일 하나를 옮긴다: place <원본> <이름> <권한>
place() {
  temporary="$TLS_DIR/.$2.tmp"
  cp "$1" "$temporary"
  chown "$NGINX_UID:$NGINX_UID" "$temporary"
  chmod "$3" "$temporary"
  mv -f "$temporary" "$TLS_DIR/$2"
}

place "$RENEWED_LINEAGE/privkey.pem" privkey.pem 0600
place "$RENEWED_LINEAGE/fullchain.pem" fullchain.pem 0644
echo "인증서를 $TLS_DIR 에 옮겼다($RENEWED_LINEAGE)"
