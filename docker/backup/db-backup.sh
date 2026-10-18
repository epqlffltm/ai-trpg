#!/bin/sh
# docker/backup/db-backup.sh
#
# DB 하나를 통째로 한 파일로 뜨고(pg_dump), 뜬 파일을 빈 DB 에 풀어 원본과 같은지 본다(#274).
# docker-compose.yml 의 db-backup 이 DB 와 같은 이미지(pgvector) 안에서 돌린다. 이미지의 sh 와 pg_dump 만 쓴다.
#
#   사용: db-backup.sh loop | once | check [백업 파일]
#     loop   지금 한 번 뜨고, BACKUP_INTERVAL_SECONDS 마다 다시 뜬다. 컨테이너가 이것으로 돈다
#     once   지금 한 번 뜬다. docker compose run --rm db-backup once
#     check  백업 파일(없으면 가장 최근 것)을 같은 DB 서버의 빈 DB 에 풀고, 표마다 줄 수가 원본과 같은지 본다.
#            다 보면 그 DB 를 지운다. CI(stack)가 PR 마다 부른다
#
# 접속은 libpq 의 환경 변수(PGHOST, PGUSER, PGPASSWORD, PGDATABASE)로 한다. 관리 계정이다.
# 백업에는 이메일, 비밀번호 해시, 결제 원장이 들어 있다. 파일은 주인만 읽게(600) 만든다. 로그에는 파일 이름과 크기만 남긴다.
#
# 네 서버의 스키마가 같은 순간의 상태로 한 파일에 든다. 서버끼리 짝이 맞아야 하는 줄(게임의 홀드 기록과 결제의 홀드)이 있어서다.
# 테스트용 스키마(*_test)는 뜨지 않는다. 계정(role)도 뜨지 않는다. 복원할 DB 서버에는 초기화 스크립트(docker/postgres/init)가 계정을 만든다.

set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
# 남기는 백업의 수. 더 오래된 것은 지운다
BACKUP_KEEP="${BACKUP_KEEP:-14}"
# 다시 뜨는 간격(초). 하루다
BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
# 뜨지 못했을 때 다시 뜨기까지의 간격(초). 1분이다. 하루를 기다리면 그날의 백업이 통째로 빠진다.
# 스택을 처음 띄울 때 마이그레이션의 ALTER TABLE 과 pg_dump 의 잠금이 겹쳐 Postgres 가 pg_dump 를 끊는 일이 있다(deadlock detected).
# 마이그레이션은 몇 초면 끝나므로 1분 뒤에는 뜬다
BACKUP_RETRY_SECONDS="${BACKUP_RETRY_SECONDS:-60}"
# pg_dump 가 처음에 표의 잠금을 잡을 때 한 표를 기다리는 가장 긴 시간(밀리초). 못 잡으면 pg_dump 가 먼저 물러나고 BACKUP_RETRY_SECONDS 뒤에 다시 뜬다.
# PostgreSQL 이 교착을 찾는 시간(deadlock_timeout, 기본 1초)보다 짧아야 한다. 그래야 교착이 나기 전에 pg_dump 가 물러나고,
# 교착이 나서 마이그레이션 쪽이 끊기는 일(서버가 뜨지 않는다)이 없다. 잠금을 다 잡은 뒤의 덤프에는 쓰이지 않는다
BACKUP_LOCK_WAIT_MS="${BACKUP_LOCK_WAIT_MS:-500}"
# 백업 파일의 이름. 뜬 시각(UTC)이 붙는다. 이름 순서가 시간 순서다
PREFIX="trpg-"
SUFFIX=".dump"
# 복원을 확인하는 DB 의 이름. 확인이 끝나면 지운다
CHECK_DB="${PGDATABASE:-trpg}_restore_check"

log() {
  echo "db-backup: $*"
}

# 지금 시각으로 백업 파일의 이름을 만든다
backup_name() {
  echo "${PREFIX}$(date -u +%Y%m%dT%H%M%SZ)${SUFFIX}"
}

# DB 를 한 파일로 뜬다. 다 쓴 뒤에 이름을 바꾼다. 뜨다 멈춘 파일이 백업으로 보이지 않게 한다.
# 실패는 단계마다 직접 돌려준다. loop 가 "backup || ..." 으로 부르면 set -e 가 함수 안에서 꺼지기 때문이다
# pg_dump 의 오류는 바로 찍지 않고 받아 두었다가 접속 주소를 지우고 찍는다(report_dump_error)
dump_once() {
  final="$BACKUP_DIR/$(backup_name)"
  partial="$final.partial"
  errors="$(mktemp)"
  umask 077
  if ! pg_dump --format=custom --exclude-schema='*_test' --lock-wait-timeout="$BACKUP_LOCK_WAIT_MS" \
      --file="$partial" 2>"$errors"; then
    rm -f "$partial"
    report_dump_error "$errors"
    rm -f "$errors"
    return 1
  fi
  rm -f "$errors"
  chmod 600 "$partial" && mv "$partial" "$final" || return 1
  log "떴다 $(basename "$final") ($(wc -c < "$final") bytes)"
}

# pg_dump 의 오류를 로그에 남긴다. 잠금을 기다리다 물러난 것이면 그렇게 적는다.
# pg_dump 는 --lock-wait-timeout 을 잠금을 잡는 문장(LOCK TABLE)의 statement_timeout 으로 건다. 그래서 그 오류는 "statement timeout" 이다.
# 덤프의 나머지에는 statement_timeout 을 걸지 않으므로, 이 글이 보이면 잠금을 기다리다 물러난 것이다.
# 접속 주소(호스트, IP, 포트, 소켓)는 지운다. 비밀번호는 libpq 가 오류에 싣지 않는다(PGPASSWORD 는 환경 변수에만 있다)
report_dump_error() {
  if grep -qE 'statement timeout|lock timeout' "$1"; then
    log "다른 작업이 표를 잠그고 있어 ${BACKUP_LOCK_WAIT_MS}ms 안에 잠금을 잡지 못했다(마이그레이션 중일 수 있다)"
  fi
  hide_address < "$1" | while IFS= read -r line; do
    log "pg_dump: $line"
  done
}

# 접속 주소를 지운다. libpq 의 "connection to server at \"db\" (172.18.0.2), port 5432 failed" 와
# "connection to server on socket \"/var/run/postgresql/.s.PGSQL.5432\" failed" 를 "connection to server failed" 로 바꾼다
hide_address() {
  sed -E \
    -e 's/connection to server at "[^"]*" \([^)]*\), port [0-9]+/connection to server/g' \
    -e 's/connection to server at "[^"]*", port [0-9]+/connection to server/g' \
    -e 's/connection to server on socket "[^"]*"/connection to server/g' \
    -e 's/^pg_dump: //'
}

# 가장 최근의 백업부터 이름을 한 줄씩 낸다
backups_newest_first() {
  ls -1 "$BACKUP_DIR" | grep "^${PREFIX}.*${SUFFIX}\$" | sort -r
}

# BACKUP_KEEP 개만 남기고 오래된 백업을 지운다
prune() {
  backups_newest_first | tail -n +"$((BACKUP_KEEP + 1))" | while read -r old; do
    rm -f "$BACKUP_DIR/$old"
    log "지웠다 $old"
  done
}

# 뜨고 정리한다. 뜨지 못하면 정리하지 않는다. 멀쩡한 옛 백업을 지우지 않게 한다
backup() {
  dump_once || return 1
  prune
}

# 끝내라는 신호를 받으면 바로 끝낸다. sleep 을 기다리지 않는다
stop() {
  log "멈춘다"
  exit 0
}

# 지금 한 번 뜨고 간격마다 다시 뜬다. 실패해도 멈추지 않는다. 실패하면 BACKUP_RETRY_SECONDS 뒤에 다시 뜬다
loop() {
  trap stop TERM INT
  while true; do
    if backup; then
      wait_for="$BACKUP_INTERVAL_SECONDS"
    else
      log "뜨지 못했다. ${BACKUP_RETRY_SECONDS}초 뒤에 다시 뜬다"
      wait_for="$BACKUP_RETRY_SECONDS"
    fi
    sleep "$wait_for" &
    wait $!
  done
}

# 관리 계정으로 관리용 DB(postgres)에 SQL 을 보낸다. "없어서 건너뛴다" 같은 안내(NOTICE)는 찍지 않는다
admin_sql() {
  PGOPTIONS='-c client_min_messages=warning' psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --dbname=postgres --command="$1"
}

# 그 DB 의 표마다 "스키마.표|줄 수"를 이름 순서로 낸다. 테스트용 스키마는 뺀다
row_counts() {
  psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --dbname="$1" <<'SQL'
SELECT format('SELECT %L || ''|'' || count(*) FROM %I.%I', table_schema || '.' || table_name, table_schema, table_name)
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_schema NOT LIKE '%\_test'
ORDER BY table_schema, table_name
\gexec
SQL
}

# 백업 파일을 빈 DB 에 풀고, 표마다 줄 수가 원본과 같은지 본다. 원본은 그사이 바뀌지 않아야 한다(CI 에서 부른다)
check() {
  file="${1:-$BACKUP_DIR/$(backups_newest_first | head -n 1)}"
  [ -f "$file" ] || { log "풀어 볼 백업이 없다"; return 1; }
  admin_sql "DROP DATABASE IF EXISTS \"$CHECK_DB\"" || return 1
  admin_sql "CREATE DATABASE \"$CHECK_DB\"" || return 1
  if ! pg_restore --exit-on-error --dbname="$CHECK_DB" "$file"; then
    admin_sql "DROP DATABASE \"$CHECK_DB\""
    log "풀지 못했다 $(basename "$file")"
    return 1
  fi
  original="$(row_counts "${PGDATABASE:-trpg}")" || return 1
  restored="$(row_counts "$CHECK_DB")" || return 1
  admin_sql "DROP DATABASE \"$CHECK_DB\"" || return 1
  if [ "$original" != "$restored" ]; then
    log "풀어 본 DB 가 원본과 다르다"
    return 1
  fi
  log "풀어 봤다 $(basename "$file"): 표 $(printf '%s\n' "$restored" | grep -c .)개의 줄 수가 원본과 같다"
}

main() {
  mkdir -p "$BACKUP_DIR"
  case "${1:-}" in
    loop) loop ;;
    once) backup ;;
    check) shift; check "$@" ;;
    *)
      echo "사용: $0 loop | once | check [백업 파일]" >&2
      return 2 ;;
  esac
}

main "$@"
