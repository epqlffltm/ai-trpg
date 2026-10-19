#!/bin/sh
# docker/backup-offsite/offsite.sh
#
# DB 의 백업을 암호화해 VM 밖(S3)에 한 벌 더 두고, 일주일에 한 번 버킷의 것을 실제로 받아 풀어 본다(staging).
# docker-compose.staging.yml 의 backup-offsite 가 돌린다. 덤프는 db-backup 이 뜬다(docker/backup/db-backup.sh). 여기는 옮기고 확인만 한다.
#
#   사용: offsite.sh loop | upload | verify | health
#     loop    한 시간마다 upload 를 하고, 마지막으로 풀어 본 지 일주일이 지났으면 verify 를 한다. 컨테이너가 이것으로 돈다
#     upload  로컬의 백업 가운데 버킷에 아직 없는 것을 암호화해 올린다
#     verify  버킷의 가장 최근 백업을 받아 확인 열쇠로 풀고, 올릴 때의 원본과 같은지(SHA-256) 보고,
#             같은 DB 서버의 빈 DB 에 풀어 서버마다의 스키마가 다 들어 있는지 본다. 다 보면 그 DB 와 푼 파일을 지운다
#     health  컨테이너의 상태 확인. 26시간 안에 올렸고, 일주일 하루 안에 풀어 보기에 성공했으면 healthy 다
#
# 암호화(age): 백업마다 받는 쪽 열쇠 둘로 잠근다(BACKUP_AGE_RECIPIENTS, 공개키 둘).
#   - 주 열쇠: 비밀키는 VM 에 두지 않는다. 비밀번호 관리자와 오프라인 사본에만 둔다. 손으로 되살릴 때 쓴다
#   - 확인 열쇠: 비밀키를 VM 에 둔다(/run/backup-keys/check.key). 주마다 풀어 보는 데 쓴다
#   VM 을 빼앗기면 확인 열쇠로 버킷의 지난 백업도 풀린다. 그때는 지금의 DB 도 이미 넘어간 뒤다.
#   버킷의 열쇠(S3 접근 키)는 올리기, 받기, 목록만 할 수 있다. 지우지 못한다(docs/architecture/deployment.md 의 "백업").
#
# 로그에는 파일 이름과 크기만 남긴다. 백업에는 이메일, 비밀번호 해시, 결제 원장이 들어 있다.
# 푼 파일은 확인이 끝나면 바로 지운다. 로컬의 백업(BACKUP_DIR)은 읽기만 한다.

set -eu
# 만드는 파일(암호화한 것, 푼 것)은 주인만 읽는다
umask 077

BACKUP_DIR="${BACKUP_DIR:-/backups}"
# 마지막으로 올린 때와 풀어 본 때(파일의 시각). 상태 확인이 본다. compose 의 볼륨이다
STATE_DIR="${STATE_DIR:-/state}"
# 확인 열쇠(age 의 비밀키 파일)
CHECK_KEY="${OFFSITE_CHECK_KEY:-/run/backup-keys/check.key}"
# 암호화한 파일과 푼 파일을 잠깐 두는 곳. 다 쓰면 지운다
WORK_DIR="${OFFSITE_WORK_DIR:-/tmp/offsite}"
# loop 의 간격(초). 한 시간이다. 하루에 한 번 뜨는 백업을 늦어도 한 시간 안에 올린다
INTERVAL_SECONDS="${OFFSITE_INTERVAL_SECONDS:-3600}"
# 풀어 보는 간격(분). 일주일이다
VERIFY_EVERY_MINUTES="${OFFSITE_VERIFY_MINUTES:-10080}"
# 상태 확인의 기준(분). 올리기는 26시간(하루에 두 시간의 여유), 풀어 보기는 일주일 하루
HEALTH_UPLOAD_MINUTES=1560
HEALTH_VERIFY_MINUTES=11520
# 백업 파일의 이름(db-backup.sh 와 같다). 버킷에는 끝에 .age 를 붙여 둔다
PREFIX="trpg-"
SUFFIX=".dump"
CIPHER_SUFFIX=".age"
# 올린 파일의 원본 SHA-256 을 싣는 S3 메타데이터의 이름
DIGEST_KEY="plaintext-sha256"
# 복원을 확인하는 DB 의 이름. 확인이 끝나면 지운다. db-backup 의 확인 DB 와 이름이 다르다
CHECK_DB="${PGDATABASE:-trpg}_offsite_check"

log() {
  echo "backup-offsite: $*"
}

# aws CLI. 버킷의 주소를 따로 적었으면(CI 의 S3 흉내) 그리로 보낸다. AWS 에서는 비워 둔다
s3() {
  if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
    aws --endpoint-url "$BACKUP_S3_ENDPOINT" "$@"
  else
    aws "$@"
  fi
}

# 꼭 있어야 하는 설정. 없으면 무엇이 없는지 찍고 멈춘다
require_settings() {
  : "${BACKUP_S3_BUCKET:?루트 .env 에 BACKUP_S3_BUCKET 을 적는다}"
  : "${BACKUP_AGE_RECIPIENTS:?루트 .env 에 BACKUP_AGE_RECIPIENTS(age 의 공개키 둘)를 적는다}"
}

# 받는 쪽 열쇠가 age 의 공개키 둘(주 열쇠, 확인 열쇠)인가. 하나뿐이면 주 열쇠나 확인 열쇠 가운데 하나를 빠뜨린 것이다
recipients_are_two() {
  count=0
  for recipient in $BACKUP_AGE_RECIPIENTS; do
    case "$recipient" in
      age1*) count=$((count + 1)) ;;
      *)
        log "BACKUP_AGE_RECIPIENTS 에 age 의 공개키(age1...)가 아닌 것이 있다"
        return 1 ;;
    esac
  done
  if [ "$count" -ne 2 ]; then
    log "BACKUP_AGE_RECIPIENTS 의 공개키는 둘이다(주 열쇠, 확인 열쇠). 지금 ${count}개다"
    return 1
  fi
}

# 확인 열쇠의 공개키가 받는 쪽 열쇠에 들어 있는가. 없으면 버킷의 백업을 그 열쇠로 풀 수 없다
check_key_is_a_recipient() {
  if ! public="$(age-keygen -y "$CHECK_KEY" 2>/dev/null)"; then
    log "확인 열쇠를 읽지 못했다($CHECK_KEY)"
    return 1
  fi
  for recipient in $BACKUP_AGE_RECIPIENTS; do
    [ "$recipient" = "$public" ] && return 0
  done
  log "확인 열쇠의 공개키가 BACKUP_AGE_RECIPIENTS 에 없다"
  return 1
}

sha256_of() {
  sha256sum "$1" | cut -d ' ' -f 1
}

# 로컬의 백업 이름들. 오래된 것부터(이름 순서가 시간 순서다). 뜨는 중인 파일(.partial)은 빠진다
local_backups() {
  for file in "$BACKUP_DIR/$PREFIX"*"$SUFFIX"; do
    [ -f "$file" ] && basename "$file"
  done
  return 0
}

# 버킷에 그 이름이 있는가
remote_exists() {
  s3 s3api head-object --bucket "$BACKUP_S3_BUCKET" --key "$1" >/dev/null 2>&1
}

# 받는 쪽 열쇠 모두로 잠근다: encrypt <원본> <암호화한 파일>
encrypt() {
  source_file="$1"
  target_file="$2"
  set --
  for recipient in $BACKUP_AGE_RECIPIENTS; do
    set -- "$@" -r "$recipient"
  done
  age "$@" -o "$target_file" "$source_file"
}

# 백업 하나를 암호화해 올린다. 원본의 SHA-256 을 메타데이터로 싣는다(풀어 볼 때 맞춰 본다)
upload_one() {
  name="$1"
  key="$name$CIPHER_SUFFIX"
  encrypted="$WORK_DIR/$key"
  digest="$(sha256_of "$BACKUP_DIR/$name")" || return 1
  if ! encrypt "$BACKUP_DIR/$name" "$encrypted"; then
    rm -f "$encrypted"
    log "암호화하지 못했다 $name"
    return 1
  fi
  if ! s3 s3 cp "$encrypted" "s3://$BACKUP_S3_BUCKET/$key" --metadata "$DIGEST_KEY=$digest" --only-show-errors; then
    rm -f "$encrypted"
    log "올리지 못했다 $key"
    return 1
  fi
  log "올렸다 $key ($(wc -c < "$encrypted") bytes)"
  rm -f "$encrypted"
}

# 로컬의 백업 가운데 버킷에 아직 없는 것을 모두 올린다. 하나라도 실패하면 실패다(다음 바퀴에 다시 한다)
upload() {
  require_settings
  recipients_are_two || return 1
  mkdir -p "$WORK_DIR" "$STATE_DIR"
  names="$(local_backups)"
  if [ -z "$names" ]; then
    log "올릴 백업이 아직 없다"
    return 1
  fi
  failed=0
  for name in $names; do
    remote_exists "$name$CIPHER_SUFFIX" && continue
    upload_one "$name" || failed=1
  done
  [ "$failed" -eq 0 ] || return 1
  touch "$STATE_DIR/last-upload"
}

# 버킷의 가장 최근 백업의 이름. 이름 순서가 시간 순서다. 없으면 빈 글자다
newest_remote() {
  s3 s3api list-objects-v2 --bucket "$BACKUP_S3_BUCKET" --prefix "$PREFIX" --query 'Contents[].Key' --output text |
    tr '\t' '\n' | grep "^${PREFIX}.*${SUFFIX}${CIPHER_SUFFIX}\$" | sort | tail -n 1
}

# 올릴 때 실은 원본의 SHA-256
remote_digest() {
  s3 s3api head-object --bucket "$BACKUP_S3_BUCKET" --key "$1" --query "Metadata.\"$DIGEST_KEY\"" --output text
}

# 관리 계정으로 관리용 DB(postgres)에 SQL 을 보낸다(db-backup.sh 와 같다)
admin_sql() {
  PGOPTIONS='-c client_min_messages=warning' psql --no-psqlrc --quiet --set=ON_ERROR_STOP=1 --dbname=postgres --command="$1"
}

# 그 DB 에서 표가 하나라도 있는 스키마들. 이름 순서다. 시스템과 테스트용 스키마는 뺀다
schemas_with_tables() {
  psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --dbname="$1" --command="
    SELECT DISTINCT table_schema FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('pg_catalog', 'information_schema')
      AND table_schema NOT LIKE '%\_test'
    ORDER BY table_schema"
}

# 여러 줄을 빈칸으로 이은 한 줄
one_line() {
  printf '%s' "$1" | tr '\n' ' '
}

# 그 DB 의 표의 수
table_count() {
  psql --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 --dbname="$1" --command="
    SELECT count(*) FROM information_schema.tables
    WHERE table_type = 'BASE TABLE' AND table_schema NOT IN ('pg_catalog', 'information_schema')"
}

# 푼 파일을 빈 DB 에 풀고, 지금의 DB 에 있는 스키마가 다 들어 있는지 본다.
# 줄 수는 맞춰 보지 않는다. 지금의 DB 는 백업을 뜬 뒤에도 바뀐다(줄 수까지 맞추는 것은 CI 의 db-backup check 가 한다)
restore_check() {
  file="$1"
  admin_sql "DROP DATABASE IF EXISTS \"$CHECK_DB\"" || return 1
  admin_sql "CREATE DATABASE \"$CHECK_DB\"" || return 1
  if ! pg_restore --exit-on-error --dbname="$CHECK_DB" "$file" >/dev/null 2>&1; then
    log "빈 DB 에 풀지 못했다"
    return 1
  fi
  live="$(schemas_with_tables "${PGDATABASE:-trpg}")" || return 1
  restored="$(schemas_with_tables "$CHECK_DB")" || return 1
  if [ "$live" != "$restored" ]; then
    log "풀어 본 DB 의 스키마가 지금의 DB 와 다르다: 풀어 본 것 [$(one_line "$restored")], 지금 [$(one_line "$live")]"
    return 1
  fi
  tables="$(table_count "$CHECK_DB")" || return 1
  log "빈 DB 에 풀었다: 스키마 [$(one_line "$restored")], 표 ${tables}개"
}

# 버킷의 백업 하나를 받아 풀고 맞춰 본다. 지우는 일은 부른 쪽(verify)이 한다
verify_object() {
  key="$1"
  encrypted="$WORK_DIR/check$CIPHER_SUFFIX"
  plain="$WORK_DIR/check$SUFFIX"
  if ! s3 s3 cp "s3://$BACKUP_S3_BUCKET/$key" "$encrypted" --only-show-errors; then
    log "받지 못했다 $key"
    return 1
  fi
  if ! age -d -i "$CHECK_KEY" -o "$plain" "$encrypted" 2>/dev/null; then
    log "풀지 못했다 $key. 확인 열쇠가 받는 쪽 열쇠가 아니었거나 파일이 상했다"
    return 1
  fi
  expected="$(remote_digest "$key")" || return 1
  if [ "$(sha256_of "$plain")" != "$expected" ]; then
    log "푼 파일이 올릴 때의 원본과 다르다 $key"
    return 1
  fi
  restore_check "$plain" || return 1
  log "풀어 봤다 $key: 확인 열쇠로 풀리고, 원본과 같고, 빈 DB 에 풀린다"
}

# 버킷의 가장 최근 백업을 실제로 풀어 본다. 성공하면 그 시각을 남기고, 실패하면 지운다(상태 확인이 곧바로 실패한다)
verify() {
  require_settings
  mkdir -p "$WORK_DIR" "$STATE_DIR"
  rm -f "$STATE_DIR/last-verify"
  check_key_is_a_recipient || return 1
  key="$(newest_remote)" || return 1
  if [ -z "$key" ]; then
    log "버킷에 백업이 없다"
    return 1
  fi
  result=0
  verify_object "$key" || result=1
  rm -f "$WORK_DIR/check$CIPHER_SUFFIX" "$WORK_DIR/check$SUFFIX"
  admin_sql "DROP DATABASE IF EXISTS \"$CHECK_DB\"" || result=1
  [ "$result" -eq 0 ] || return 1
  touch "$STATE_DIR/last-verify"
}

# 마지막으로 풀어 본 지 정한 간격이 지났는가(한 번도 풀어 보지 않았으면 지난 것이다)
verify_due() {
  [ -z "$(find "$STATE_DIR" -maxdepth 1 -name last-verify -mmin "-$VERIFY_EVERY_MINUTES" 2>/dev/null)" ]
}

# 그 이름의 파일이 정한 분 안에 바뀌었는가
touched_within() {
  [ -n "$(find "$STATE_DIR" -maxdepth 1 -name "$1" -mmin "-$2" 2>/dev/null)" ]
}

health() {
  touched_within last-upload "$HEALTH_UPLOAD_MINUTES" && touched_within last-verify "$HEALTH_VERIFY_MINUTES"
}

stop() {
  log "멈춘다"
  exit 0
}

# 한 시간마다 올리고, 일주일마다 풀어 본다. 실패해도 멈추지 않는다. 풀어 보기가 실패하면 다음 바퀴(한 시간 뒤)에 다시 한다
loop() {
  trap stop TERM INT
  require_settings
  while true; do
    upload || log "다 올리지 못했다. ${INTERVAL_SECONDS}초 뒤에 다시 한다"
    if verify_due; then
      verify || log "풀어 보지 못했다. ${INTERVAL_SECONDS}초 뒤에 다시 한다"
    fi
    sleep "$INTERVAL_SECONDS" &
    wait $!
  done
}

main() {
  case "${1:-}" in
    loop) loop ;;
    upload) upload ;;
    verify) verify ;;
    health) health ;;
    *)
      echo "사용: $0 loop | upload | verify | health" >&2
      return 2 ;;
  esac
}

main "$@"
