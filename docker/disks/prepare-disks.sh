#!/usr/bin/env bash
# docker/disks/prepare-disks.sh
#
# staging VM 의 데이터 디스크 둘에 컨테이너가 쓸 폴더를 만든다(#539, docs/operations/staging-vm.md 의 3번과 5번).
#   DB 디스크(/mnt/db)               postgres
#   관측 디스크(/mnt/observability)   loki, prometheus, alertmanager, tempo, grafana, alloy
# docker-compose.staging.yml 이 이 폴더들을 그 컨테이너에 붙인다. 폴더마다 그 컨테이너가 도는 사용자(uid)의 것으로 둔다.
# 디스크마다 빈 폴더 probe 도 만든다. Alloy 가 읽기 전용으로 붙여 그 디스크의 크기를 잰다(docker/alloy/metrics.alloy).
#
# 디스크가 마운트되어 있지 않으면 아무것도 만들지 않고 멈춘다. 마운트 전에 만들면 폴더가 기본 디스크에 생기고,
# 컨테이너가 데이터 디스크 대신 기본 디스크에 써도 아무도 모른다.
# 여러 번 돌려도 된다. 이미 있는 폴더는 주인과 권한만 맞춘다. 안의 데이터는 건드리지 않는다.
#
#   사용(VM 의 저장소 루트에서):  sudo bash docker/disks/prepare-disks.sh
#   주인의 표만 찍는다:          bash docker/disks/prepare-disks.sh --owners
#     한 줄에 "서비스 uid" 다. CI(.github/scripts/stack-smoke.sh)가 컨테이너가 실제로 도는 uid 와 견준다.
#     이미지를 올려 사용자가 바뀌면 CI 가 실패한다. 그때 이 표를 고친다
#
# 디스크의 자리는 환경 변수로 바꿀 수 있다(CI 가 임시 디스크로 이 스크립트를 돌려 본다). VM 에서는 바꾸지 않는다.
# docker-compose.staging.yml 이 /mnt/db, /mnt/observability 를 그대로 적는다

set -euo pipefail

DB_DISK="${DB_DISK:-/mnt/db}"
OBSERVABILITY_DISK="${OBSERVABILITY_DISK:-/mnt/observability}"

# Alloy 가 디스크의 크기를 재려고 붙이는 빈 폴더의 이름
PROBE=probe

# 폴더마다: 디스크(db, observability), 폴더와 서비스의 이름, 주인(uid), 권한.
# uid 는 이미지가 정한 사용자다. alloy 는 docker-compose.yml 의 user 가 정한다
FOLDERS=(
  "db postgres 999 700"
  "observability loki 10001 750"
  "observability prometheus 65534 750"
  "observability alertmanager 65534 750"
  "observability tempo 10001 750"
  "observability grafana 472 750"
  "observability alloy 473 750"
)

# 서비스의 이름. 폴더의 이름과 같다. postgres 의 폴더는 db 서비스의 것이다
service_of() {
  if [[ "$1" == postgres ]]; then echo db; else echo "$1"; fi
}

# 디스크의 이름을 마운트한 자리로
disk_path() {
  case "$1" in
    db) echo "$DB_DISK" ;;
    observability) echo "$OBSERVABILITY_DISK" ;;
  esac
}

# 표를 "서비스 uid" 로 찍는다
print_owners() {
  local disk folder uid mode
  for row in "${FOLDERS[@]}"; do
    read -r disk folder uid mode <<<"$row"
    echo "$(service_of "$folder") $uid"
  done
}

# 디스크 둘이 마운트되어 있는가. 아니면 무엇이 빠졌는지 알리고 실패한다
require_mounted() {
  local path missing=0
  for path in "$DB_DISK" "$OBSERVABILITY_DISK"; do
    if ! mountpoint -q "$path"; then
      echo "$path 에 디스크가 마운트되어 있지 않다. docs/operations/staging-vm.md 의 3번을 먼저 한다" >&2
      missing=1
    fi
  done
  return "$missing"
}

# 폴더 하나를 만들고 주인과 권한을 맞춘다
prepare_folder() {
  local path="$1" uid="$2" mode="$3"
  mkdir -p "$path"
  chown "$uid:$uid" "$path"
  chmod "$mode" "$path"
}

# 디스크마다 빈 폴더(probe)를 만든다. root 의 것이고 아무도 쓰지 않는다
prepare_probes() {
  local path
  for path in "$DB_DISK" "$OBSERVABILITY_DISK"; do
    prepare_folder "$path/$PROBE" 0 755
  done
}

prepare_all() {
  local disk folder uid mode
  if [[ "$(id -u)" != 0 ]]; then
    echo "주인을 바꾸려면 root 로 돌린다: sudo bash $0" >&2
    return 1
  fi
  require_mounted
  for row in "${FOLDERS[@]}"; do
    read -r disk folder uid mode <<<"$row"
    prepare_folder "$(disk_path "$disk")/$folder" "$uid" "$mode"
    echo "만들었다 $(disk_path "$disk")/$folder ($uid, $mode)"
  done
  prepare_probes
  echo "만들었다 $DB_DISK/$PROBE, $OBSERVABILITY_DISK/$PROBE"
}

case "${1:-}" in
  --owners) print_owners ;;
  "") prepare_all ;;
  *)
    echo "쓰는 법: sudo bash $0  또는  bash $0 --owners" >&2
    exit 2
    ;;
esac
