// web/apps/web/src/pages/trpg/room/status/statusView.ts
// 상태 패널(B7)이 보일 글. 순수한 함수다. 값은 모두 서버가 준 것이고, 이름표(str, broken_arm …)를 규칙의 이름으로 읽는다.
// 화면은 HP 나 소지품을 계산하지 않는다. 바뀌면 서버의 값을 다시 읽는다.

import { itemKindLabel, rarityLabel } from '../../labels';
import type {
  ClockTime,
  GameClock,
  HeldItem,
  Quest,
  Ruleset,
  Sheet,
  SheetInjury,
  TableDetail,
  TableMap,
  TableMember,
} from '../../../../api/types';

const TIMES_OF_DAY: Record<ClockTime['time_of_day'], string> = {
  dawn: '새벽',
  morning: '아침',
  day: '낮',
  evening: '저녁',
  night: '밤',
};

const QUEST_STATUS: Record<Quest['status'], string> = {
  hidden: '숨김(방장만)',
  active: '진행 중',
  succeeded: '성공',
  failed: '실패',
};

export type Condition = 'none' | 'standing' | 'downed' | 'dead';

/** 캐릭터의 몸 상태. 시트가 없으면(정하지 않음) none, HP 가 0 이하이면 쓰러짐 */
export function conditionOf(sheet: Sheet | null): Condition {
  if (!sheet) return 'none';
  if (sheet.dead) return 'dead';
  return sheet.hp <= 0 ? 'downed' : 'standing';
}

/** HP 의 비율(0~1). 막대의 길이에 쓴다 */
export function hpRatio(sheet: Sheet): number {
  if (sheet.max_hp <= 0) return 0;
  return Math.min(1, Math.max(0, sheet.hp / sheet.max_hp));
}

/** "죽음의 굴림 성공 1/3 · 실패 0/3". 규칙에 죽음의 굴림이 없으면 센 수만 */
export function deathSaveProgress(sheet: Sheet, rules: Ruleset): string {
  const save = rules.death_save;
  const successes = save ? `${sheet.death_successes}/${save.successes}` : String(sheet.death_successes);
  const failures = save ? `${sheet.death_failures}/${save.failures}` : String(sheet.death_failures);
  return `죽음의 굴림 성공 ${successes} · 실패 ${failures}`;
}

/** 부상의 이름. 규칙에 없는 이름표는 그대로 */
export function injuryName(rules: Ruleset, key: string): string {
  return rules.injuries.find((injury) => injury.key === key)?.name ?? key;
}

/** 부상이 풀리는 때. 짧은 것은 라운드, 오래 가는 것은 게임 안의 시각, 결손은 낫지 않는다 */
export function injuryTiming(injury: SheetInjury, rules: Ruleset): string {
  if (injury.ends_after_round !== null) return `라운드 ${injury.ends_after_round}까지`;
  if (injury.heals_at) return `${clockTimeLabel(injury.heals_at)}에 나음`;
  const healing = rules.injuries.find((entry) => entry.key === injury.injury)?.healing;
  return healing === 'permanent' ? '낫지 않음' : '치료가 필요함';
}

/** "3일째 14:05" */
export function clockTimeLabel(time: Pick<ClockTime, 'day' | 'hour' | 'minute'>): string {
  return `${time.day}일째 ${pad(time.hour)}:${pad(time.minute)}`;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

/** "3일째 14:05 · 낮" */
export function clockLabel(clock: GameClock): string {
  return `${clockTimeLabel(clock)} · ${TIMES_OF_DAY[clock.time_of_day]}`;
}

/** "30분", "2시간", "1시간 30분" */
export function minutesLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}분`;
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`;
}

export function questStatusLabel(status: Quest['status']): string {
  return QUEST_STATUS[status];
}

/** "소모품 · 희귀" */
export function itemLabel(item: Pick<HeldItem, 'kind' | 'rarity'>): string {
  return `${itemKindLabel(item.kind)} · ${rarityLabel(item.rarity)}`;
}

/** 소모품의 회복량. "회복 가벼움(1d4)". 판의 물건(TableDetail.items)과 규칙의 등급(magnitudes)에서 찾는다 */
export function healsLabel(table: TableDetail, entryId: string): string | null {
  const key = table.items.find((item) => item.entry_id === entryId)?.heals;
  if (!key) return null;
  const magnitude = table.rules.magnitudes.find((entry) => entry.key === key);
  return magnitude ? `회복 ${magnitude.name}(${magnitude.count}d${magnitude.sides})` : `회복 ${key}`;
}

/** 나를 맨 앞에. 나머지는 들어온 차례 그대로 */
export function meFirst(members: TableMember[], myId: string | undefined): TableMember[] {
  const mine = members.filter((member) => member.user_id === myId);
  return [...mine, ...members.filter((member) => member.user_id !== myId)];
}

export function placeName(map: TableMap, placeId: string | null | undefined): string | null {
  if (!placeId) return null;
  return map.places.find((place) => place.entry_id === placeId)?.name ?? null;
}

/** 갈 수 있는 곳 하나. route 는 그리로 가는 길(문의 상태와 넘기 판정, #281) */
export type Way = { placeId: string; name: string; minutes: number | null; route: TableMap['routes'][number] };

/**
 * 그 장소의 커버(#276). 세이브 방식의 판에서만 센다(다른 방식이면 엄폐를 받지 않는다). 없으면 0.
 * 서버의 app/rounds/covers.py 와 같은 조건이다
 */
export function placeCover(table: TableDetail, placeId: string | null | undefined): number {
  if (table.rules.armor?.mode !== 'save' || !placeId) return 0;
  return table.map?.places.find((place) => place.entry_id === placeId)?.cover ?? 0;
}

/** 이 장소에서 아는 길로 갈 수 있는 곳. 한쪽 길은 나가는 쪽만 센다. 이름 차례로 */
export function waysFrom(map: TableMap, placeId: string | null | undefined): Way[] {
  if (!placeId) return [];
  const ways: Way[] = [];
  for (const route of map.routes) {
    const to = route.from_place === placeId ? route.to_place : route.two_way && route.to_place === placeId ? route.from_place : null;
    const name = to ? placeName(map, to) : null;
    if (to && name) ways.push({ placeId: to, name, minutes: route.travel_minutes ?? null, route });
  }
  return ways.sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}

/**
 * 길을 막거나 굴리게 하는 것(#281). 가기 전에 알 것만 적는다. 없으면 빈 목록.
 * "자물쇠 잠김"(열쇠가 있으면 지나며 연다), "빗장 걸림(이쪽)"(지나며 푼다) 또는 "빗장 걸림(저쪽)"(부수기로만 연다),
 * "넘기 판정: 근력, 보통"(지날 때마다 굴린다). 열린 문, 부서진 문은 막지 않으니 적지 않는다
 */
export function wayNotes(way: Way, here: string, rules: Ruleset): string[] {
  const { route } = way;
  const notes: string[] = [];
  if (route.locked === true) notes.push('자물쇠 잠김');
  if (route.barred === true) notes.push(route.bar_side === here ? '빗장 걸림(이쪽)' : '빗장 걸림(저쪽)');
  if (route.cross) {
    const ability = rules.abilities.find((one) => one.key === route.cross?.ability)?.name ?? route.cross.ability;
    const difficulty = rules.difficulties.find((one) => one.key === route.cross?.difficulty)?.name ?? route.cross.difficulty;
    notes.push(`넘기 판정: ${ability}, ${difficulty}`);
  }
  return notes;
}

/** 장소마다 거기 선 캐릭터의 이름. 맵에 서 있지 않은 사람은 빠진다 */
export function whoIsWhere(map: TableMap, members: TableMember[]): { name: string; characters: string[] }[] {
  return map.places
    .map((place) => ({
      name: place.name,
      characters: members
        .filter((member) => member.sheet?.place_id === place.entry_id && member.character)
        .map((member) => member.character?.name ?? ''),
    }))
    .filter((entry) => entry.characters.length > 0);
}
