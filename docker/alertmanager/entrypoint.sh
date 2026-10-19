#!/bin/sh
# docker/alertmanager/entrypoint.sh
# Alertmanager 의 시작 명령(#25). docker-compose.yml 의 alertmanager 가 부른다(이미지의 busybox sh).
#
# 루트 .env 의 ALERT_* 로 설정 파일을 만들고 Alertmanager 를 띄운다. Alertmanager 의 설정 파일은 환경 변수를 펼치지 않는다.
# 받는 곳(Discord, Slack, Telegram, 메일)은 값을 적은 것만 켠다. 하나도 없으면 경보는 Grafana 에서만 본다.
# 바깥 감시(ALERT_HEARTBEAT_WEBHOOK_URL)를 적으면 늘 울리는 Watchdog 을 그 주소로만 1~2분마다 보낸다. 끊기면 바깥 감시가 알린다.
# Watchdog 은 적지 않아도 운영자의 받는 곳에 가지 않는다(버린다).
# 비밀(웹후크 주소, 봇 토큰, 메일 비밀번호)은 설정 파일에 적지 않고 주인만 읽는 파일에 따로 둔다(*_file).
# 설정 파일과 비밀은 컨테이너 안(/tmp)에만 있다. 컨테이너를 다시 만들면 루트 .env 로 다시 만든다.
#
#   sh entrypoint.sh [alertmanager 의 인자...]   설정을 만들고 Alertmanager 를 띄운다
#   sh entrypoint.sh check                        설정을 만들고 amtool 로 검사만 한다(stack-smoke.sh 가 부른다)
#
# 받는 곳을 하나만 반쯤 적으면(Telegram 의 토큰만, 메일의 계정만) 뜨지 않는다. 적은 사람이 알아채게 한다.

set -eu

CONFIG_DIR="${ALERTMANAGER_CONFIG_DIR:-/tmp/alertmanager}"
CONFIG="$CONFIG_DIR/alertmanager.yml"
# 켠 받는 곳의 이름들. 로그에 남긴다(값은 남기지 않는다)
enabled=""

fail() {
  echo "alertmanager: $*" >&2
  exit 1
}

# 값 하나를 YAML 의 작은따옴표 문자열로 바꾼다. 안의 작은따옴표는 둘로 적는다
quote() {
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/''/g")"
}

# 비밀 하나를 주인만 읽는 파일로 쓰고 그 경로를 찍는다
secret_file() {
  printf '%s' "$2" > "$CONFIG_DIR/$1"
  printf '%s' "$CONFIG_DIR/$1"
}

# 둘 다 적었거나 둘 다 비었는가
both_or_neither() {
  if [ -n "$2" ] && [ -z "$4" ]; then fail "$1 를 적었으면 $3 도 적는다"; fi
  if [ -z "$2" ] && [ -n "$4" ]; then fail "$3 를 적었으면 $1 도 적는다"; fi
}

# 주소가 http:// 나 https:// 로 시작하는가
require_url() {
  case "$2" in
    http://* | https://*) ;;
    *) fail "$1 는 https:// 로 시작하는 주소다" ;;
  esac
}

# 적은 값들이 맞는 모양인가. 값은 찍지 않는다
validate() {
  both_or_neither ALERT_TELEGRAM_BOT_TOKEN "${ALERT_TELEGRAM_BOT_TOKEN:-}" ALERT_TELEGRAM_CHAT_ID "${ALERT_TELEGRAM_CHAT_ID:-}"
  both_or_neither ALERT_SMTP_USER "${ALERT_SMTP_USER:-}" ALERT_SMTP_PASSWORD "${ALERT_SMTP_PASSWORD:-}"
  if [ -n "${ALERT_DISCORD_WEBHOOK_URL:-}" ]; then require_url ALERT_DISCORD_WEBHOOK_URL "$ALERT_DISCORD_WEBHOOK_URL"; fi
  if [ -n "${ALERT_SLACK_WEBHOOK_URL:-}" ]; then require_url ALERT_SLACK_WEBHOOK_URL "$ALERT_SLACK_WEBHOOK_URL"; fi
  if [ -n "${ALERT_HEARTBEAT_WEBHOOK_URL:-}" ]; then require_url ALERT_HEARTBEAT_WEBHOOK_URL "$ALERT_HEARTBEAT_WEBHOOK_URL"; fi
  if [ -n "${ALERT_TELEGRAM_CHAT_ID:-}" ] && ! printf '%s' "$ALERT_TELEGRAM_CHAT_ID" | grep -Eq '^-?[0-9]+$'; then
    fail "ALERT_TELEGRAM_CHAT_ID 는 숫자다(그룹은 -100 으로 시작한다)"
  fi
}

# --- 받는 곳마다의 설정. 값이 없으면 아무것도 찍지 않는다 ---

discord() {
  [ -n "${ALERT_DISCORD_WEBHOOK_URL:-}" ] || return 0
  enabled="$enabled discord"
  cat <<YAML
    discord_configs:
      - webhook_url_file: $(quote "$(secret_file discord-webhook-url "$ALERT_DISCORD_WEBHOOK_URL")")
        send_resolved: true
YAML
}

slack() {
  [ -n "${ALERT_SLACK_WEBHOOK_URL:-}" ] || return 0
  enabled="$enabled slack"
  cat <<YAML
    slack_configs:
      - api_url_file: $(quote "$(secret_file slack-webhook-url "$ALERT_SLACK_WEBHOOK_URL")")
        send_resolved: true
YAML
}

telegram() {
  [ -n "${ALERT_TELEGRAM_BOT_TOKEN:-}" ] || return 0
  enabled="$enabled telegram"
  cat <<YAML
    telegram_configs:
      - bot_token_file: $(quote "$(secret_file telegram-bot-token "$ALERT_TELEGRAM_BOT_TOKEN")")
        chat_id: $ALERT_TELEGRAM_CHAT_ID
        api_url: $(quote "${ALERT_TELEGRAM_API_URL:-https://api.telegram.org}")
        send_resolved: true
YAML
}

# 메일. 보내는 사람은 로그인하는 계정이다(Gmail 은 다른 주소를 계정 주소로 바꾼다). 받는 사람을 적지 않으면 그 계정이다
email() {
  [ -n "${ALERT_SMTP_USER:-}" ] || return 0
  enabled="$enabled email"
  cat <<YAML
    email_configs:
      - to: $(quote "${ALERT_EMAIL_TO:-$ALERT_SMTP_USER}")
        from: $(quote "$ALERT_SMTP_USER")
        smarthost: $(quote "${ALERT_SMTP_SMARTHOST:-smtp.gmail.com:587}")
        auth_username: $(quote "$ALERT_SMTP_USER")
        auth_password_file: $(quote "$(secret_file smtp-password "$ALERT_SMTP_PASSWORD")")
        require_tls: true
        send_resolved: true
YAML
}

# 바깥 감시. Watchdog 을 그 주소로 POST 한다(healthchecks.io 의 ping 주소 등). 풀림은 보내지 않는다(늘 울린다)
heartbeat() {
  [ -n "${ALERT_HEARTBEAT_WEBHOOK_URL:-}" ] || return 0
  enabled="$enabled heartbeat"
  cat <<YAML
    webhook_configs:
      - url_file: $(quote "$(secret_file heartbeat-webhook-url "$ALERT_HEARTBEAT_WEBHOOK_URL")")
        send_resolved: false
        max_alerts: 1
YAML
}

# 묶는 법과 되풀이. 같은 경보 이름과 서버(또는 인프라의 job)를 한 알림으로 묶는다.
# 첫 알림은 30초 모아 보내고, 묶음이 바뀌면 5분마다, 그대로면 4시간마다 다시 보낸다. 풀리면 풀렸다고 보낸다(send_resolved)
# Watchdog 만 따로 바깥 감시로 보낸다. 기다리지 않고 1분마다 다시 보낸다. 운영자의 받는 곳으로 내려가지 않는다(continue 가 없다)
route() {
  cat <<YAML
route:
  receiver: operator
  group_by: [alertname, service, job]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers: ['alertname = Watchdog']
      receiver: heartbeat
      group_wait: 0s
      group_interval: 1m
      repeat_interval: 1m

# DB 가 죽었으면 서버마다의 "DB 에 닿지 못한다"는 보내지 않는다. 원인 하나에 알림 하나다
inhibit_rules:
  - source_matchers: ['alertname = PostgresDown']
    target_matchers: ['alertname =~ ".+DatabaseUnreachable"']

receivers:
YAML
}

# 받는 쪽 하나의 머리. 그 아래에 받는 곳마다의 설정이 붙는다
receiver() {
  printf '  - name: %s\n' "$1"
}

# 설정 파일을 만든다. 주인만 읽는 폴더에 쓴다
render() {
  umask 077
  mkdir -p "$CONFIG_DIR"
  validate
  {
    route
    receiver operator
    discord
    slack
    telegram
    email
    receiver heartbeat
    heartbeat
  } > "$CONFIG"
  if [ -n "$enabled" ]; then
    echo "alertmanager: 받는 곳:$enabled" >&2
  else
    echo "alertmanager: 받는 곳이 없다. 루트 .env 에 ALERT_* 를 적는다. 그때까지 경보는 Grafana 에서만 본다" >&2
  fi
}

main() {
  render
  if [ "${1:-}" = "check" ]; then
    exec amtool check-config "$CONFIG"
  fi
  exec alertmanager --config.file="$CONFIG" "$@"
}

main "$@"
