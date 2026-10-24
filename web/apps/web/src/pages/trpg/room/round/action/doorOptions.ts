// web/apps/web/src/pages/trpg/room/round/action/doorOptions.ts
// 문을 다루는 행동(#281)의 고를 거리. 순수한 함수다. 서버의 app/rounds/door_actions.py 를 따른다.
//
// - 문은 내가 선 장소에 닿은 아는 길의 것이다. 길의 방향은 보지 않는다(한쪽 길도 어느 끝에서든 다룬다). 길은 반대편 장소로 가리킨다
// - 화면이 아는 문의 상태(locked, barred, bar_side, broken)로 지금 할 수 있는 것만 보인다. 안내일 뿐이다.
//   앞 차례에 누가 문을 열거나 열쇠를 건넸을 수 있어, 맞는지는 차례가 올 때 서버가 본다(못 하면 결과에 까닭)
//   - 잠그기: 부서지지 않은 문의 열린 자물쇠, 또는 빗장 쪽에 서 있을 때 풀린 빗장
//   - 열기: 잠긴 자물쇠, 또는 빗장 쪽에 서 있을 때 걸린 빗장
//   - 따기: 따는 판정이 있는 잠긴 자물쇠. 부수기: 부수는 판정이 있고 잠겼거나 걸린 문. 고치기: 고치는 판정이 있는 부서진 문
// - 무슨 열쇠로 여는지, 따거나 고치는 도구는 화면이 모른다(서버가 주지 않는다). 지녔는지는 서버가 본다

import type { DoorDevice, TableMap } from '../../../../../api/types';
import { placeName } from '../../status/statusView';

export type DoorKind = 'lock' | 'unlock' | 'pick' | 'force' | 'repair';
type MapRoute = TableMap['routes'][number];

/** 내 장소에 닿은 문 하나. place 는 길의 반대편 장소(행동의 place) */
export type Door = { place: string; name: string; route: MapRoute };

export const DOOR_KINDS: DoorKind[] = ['unlock', 'lock', 'pick', 'force', 'repair'];

const DEVICE_LABELS: Record<DoorDevice, string> = { lock: '자물쇠', bar: '빗장' };

export function isDoorKind(kind: string): kind is DoorKind {
  return (DOOR_KINDS as string[]).includes(kind);
}

export function deviceLabel(device: DoorDevice): string {
  return DEVICE_LABELS[device];
}

/** 자물쇠나 빗장이 있는 길인가 */
function hasDoor(route: MapRoute): boolean {
  return route.locked != null || route.barred != null;
}

/** 내 장소에 닿은 아는 길의 문들. 반대편 장소의 이름 차례로 */
export function doorsHere(map: TableMap | null | undefined, here: string | null | undefined): Door[] {
  if (!map || !here) return [];
  const doors: Door[] = [];
  for (const route of map.routes) {
    const place = route.from_place === here ? route.to_place : route.to_place === here ? route.from_place : null;
    const name = place ? placeName(map, place) : null;
    if (place && name && hasDoor(route)) doors.push({ place, name, route });
  }
  return doors.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

/** 잠그기와 열기가 이 문에서 다룰 수 있는 장치. 빗장은 빗장 쪽에 서 있어야 한다 */
export function doorDevices(kind: 'lock' | 'unlock', route: MapRoute, here: string): DoorDevice[] {
  const shut = kind === 'lock';
  if (shut && route.broken) return [];
  const devices: DoorDevice[] = [];
  if (route.locked != null && route.locked !== shut) devices.push('lock');
  if (route.barred != null && route.barred !== shut && route.bar_side === here) devices.push('bar');
  return devices;
}

/** 이 문에 지금 그 행동을 할 수 있어 보이는가 */
export function canHandleDoor(kind: DoorKind, route: MapRoute, here: string): boolean {
  switch (kind) {
    case 'lock':
    case 'unlock':
      return doorDevices(kind, route, here).length > 0;
    case 'pick':
      return route.pick != null && route.locked === true;
    case 'force':
      return route.force != null && (route.locked === true || route.barred === true);
    case 'repair':
      return route.repair != null && route.broken;
  }
}

/** 그 행동을 할 수 있는 문들 */
export function doorsFor(kind: DoorKind, map: TableMap | null | undefined, here: string | null | undefined): Door[] {
  if (!here) return [];
  return doorsHere(map, here).filter((door) => canHandleDoor(kind, door.route, here));
}

/** 문의 지금 상태 한 줄. "자물쇠 잠김 · 빗장 걸림(수도원 문 쪽) · 부서짐" */
export function doorState(door: Door, map: TableMap): string {
  const { route } = door;
  const parts: string[] = [];
  if (route.locked != null) parts.push(`자물쇠 ${route.locked ? '잠김' : '열림'}`);
  if (route.barred != null) {
    const side = route.bar_side ? placeName(map, route.bar_side) : null;
    parts.push(`빗장 ${route.barred ? '걸림' : '풀림'}${side ? `(${side} 쪽)` : ''}`);
  }
  if (route.broken) parts.push('부서짐');
  return parts.join(' · ');
}

/**
 * 보낼 장치. 고른 것이 할 수 있는 것이면 그것, 아니면 할 수 있는 것의 첫째. 하나도 없으면 고른 것(비면 null).
 * 자물쇠와 빗장이 다 있는 길은 서버가 장치를 적으라고 하므로, 고를 수 있으면 늘 적어 보낸다
 */
export function chosenDevice(devices: DoorDevice[], chosen: string): DoorDevice | null {
  const picked = devices.find((device) => device === chosen);
  if (picked) return picked;
  if (devices[0]) return devices[0];
  return chosen === 'lock' || chosen === 'bar' ? chosen : null;
}
