// web/apps/web/src/pages/trpg/studio/scenarios/wandersForm.ts
// 무작위 조우 표(B9 몬스터 탭, #283). 순수한 함수다(서버의 WanderTable 과 게시의 wander_* 문제를 따른다).
//
// - 표는 장소마다 적는다. 장소를 비우면 판의 기본 표다(표를 하나도 적지 않은 장소에서 쓴다)
// - 때(새벽~밤)를 비우면 언제나다. 한 장소(또는 기본 표)의 표들은 때가 겹치지 못한다. 비운 때는 무엇과도 겹친다
// - 확률은 0~100%. 0 이면 안전한 곳이라 몬스터를 적지 않고, 0 보다 크면 몬스터를 하나는 적는다
// - 몬스터 줄은 10 개까지, 시트를 적은 몬스터만. 한 표에 같은 몬스터는 한 줄. 줄마다 마리 수 1~10, 몫 1~100, 기습
// - 표는 50 개까지. 표가 있으면 맵이 있어야 한다(시작 장소, wander_off_map)

import type { DayTime, Surprise, WanderTable, WanderTableBody } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import { ENCOUNTER_MAX_COUNT, surpriseLabel } from './encountersForm';

export const MAX_WANDERS = 50;
export const WANDER_MAX_MONSTERS = 10;
export const WANDER_MAX_WEIGHT = 100;

export const DAY_TIMES: DayTime[] = ['dawn', 'morning', 'day', 'evening', 'night'];
const DAY_TIME_LABELS: Record<DayTime, string> = { dawn: '새벽', morning: '아침', day: '낮', evening: '저녁', night: '밤' };

export function dayTimeLabel(time: DayTime): string {
  return DAY_TIME_LABELS[time];
}

export type WanderMonsterDraft = { monster: string; count: string; weight: string; surprise: Surprise };

export type WanderDraft = {
  /** 빈 값이면 판의 기본 표 */
  place: string;
  times: DayTime[];
  chance: string;
  monsters: WanderMonsterDraft[];
};

export function newWanderMonster(): WanderMonsterDraft {
  return { monster: '', count: '1', weight: '1', surprise: 'none' };
}

export function wanderDraft(table: WanderTable | null): WanderDraft {
  return {
    place: table?.place_id ?? '',
    times: table?.times ?? [],
    chance: String(table?.chance ?? 10),
    monsters: (table?.monsters ?? []).map((row) => ({ monster: row.monster_id, count: String(row.count), weight: String(row.weight), surprise: row.surprise })),
  };
}

/** 때를 켜거나 끈다. 새벽~밤의 차례를 지킨다 */
export function toggleTime(times: DayTime[], time: DayTime): DayTime[] {
  const next = times.includes(time) ? times.filter((one) => one !== time) : [...times, time];
  return DAY_TIMES.filter((one) => next.includes(one));
}

/** 두 표의 때가 겹치는가. 비운 때는 언제나라서 무엇과도 겹친다 */
export function timesOverlap(one: DayTime[], other: DayTime[]): boolean {
  return one.length === 0 || other.length === 0 || one.some((time) => other.includes(time));
}

export type WanderHints = { fields: Record<string, string>; monsters: Record<number, string> };

/** 보내기 전에 알릴 것. at 은 고치는 표의 차례(새 표면 null). sheeted 는 시트를 적은 몬스터 */
export function wanderHints(draft: WanderDraft, tables: WanderTable[], at: number | null, sheeted: string[]): WanderHints {
  const fields: Record<string, string> = {};
  const others = tables.filter((_, index) => index !== at);
  if (others.some((one) => (one.place_id ?? '') === draft.place && timesOverlap(one.times, draft.times))) {
    fields.times = draft.place === '' ? '기본 표 가운데 같은 때를 쓰는 표가 이미 있습니다.' : '이 장소에 같은 때를 쓰는 표가 이미 있습니다. 때를 나눠 주세요.';
  }
  const chance = wholeNumber(draft.chance, 0, 100);
  if (chance === null) fields.chance = '0~100 사이의 정수입니다.';
  else if (chance > 0 && draft.monsters.length === 0) fields.monsters = '조우가 날 확률이 있으면 나올 몬스터를 하나는 적어 주세요.';
  return { fields, monsters: chance === 0 ? {} : monsterHints(draft.monsters, sheeted) };
}

function monsterHints(rows: WanderMonsterDraft[], sheeted: string[]): Record<number, string> {
  const hints: Record<number, string> = {};
  rows.forEach((row, index) => {
    const hint = monsterHint(row, rows.slice(0, index), sheeted);
    if (hint) hints[index] = hint;
  });
  return hints;
}

function monsterHint(row: WanderMonsterDraft, before: WanderMonsterDraft[], sheeted: string[]): string | null {
  if (row.monster === '') return '몬스터를 골라 주세요.';
  if (!sheeted.includes(row.monster)) return '시트를 적은 몬스터만 나올 수 있습니다.';
  if (before.some((one) => one.monster === row.monster)) return '같은 몬스터가 두 줄입니다. 한 줄에 마리 수와 몫으로 적어 주세요.';
  if (wholeNumber(row.count, 1, ENCOUNTER_MAX_COUNT) === null) return `마리 수는 1~${ENCOUNTER_MAX_COUNT} 사이의 정수입니다.`;
  if (wholeNumber(row.weight, 1, WANDER_MAX_WEIGHT) === null) return `몫은 1~${WANDER_MAX_WEIGHT} 사이의 정수입니다.`;
  return null;
}

export function hasWanderHints(hints: WanderHints): boolean {
  return Object.keys(hints.fields).length > 0 || Object.keys(hints.monsters).length > 0;
}

/** 보낼 표. 확률이 0 이면 몬스터를 보내지 않는다 */
export function toWander(draft: WanderDraft): WanderTableBody {
  const chance = Number(draft.chance.trim());
  const monsters =
    chance === 0
      ? []
      : draft.monsters.map((row) => ({ monster_id: row.monster, count: Number(row.count.trim()), weight: Number(row.weight.trim()), surprise: row.surprise }));
  return { place_id: draft.place === '' ? null : draft.place, times: draft.times, chance, monsters };
}

export function withWander(tables: WanderTable[], at: number | null, table: WanderTableBody): WanderTableBody[] {
  return at === null ? [...tables, table] : tables.map((one, index) => (index === at ? table : one));
}

export function withoutWander(tables: WanderTable[], at: number): WanderTableBody[] {
  return tables.filter((_, index) => index !== at);
}

/** 몫을 백분율로. "40%". 몫의 합이 0 이면 빈 글 */
export function weightShare(weight: number, total: number): string {
  if (total <= 0) return '';
  return `${Math.round((weight / total) * 100)}%`;
}

/**
 * 목록의 한 줄. "지하 묘지 · 밤, 새벽 · 30% · 구울 ×3(67%), 리치(33%, 몬스터가 매복)",
 * 기본 표는 "기본 표", 때가 없으면 "언제나", 확률 0 이면 "안전(조우 없음)"
 */
export function wanderLine(table: WanderTable, placeName: (id: string) => string, monsterName: (id: string) => string): string {
  const place = table.place_id ? placeName(table.place_id) : '기본 표';
  const times = table.times.length === 0 ? '언제나' : table.times.map(dayTimeLabel).join(', ');
  if (table.chance === 0) return `${place} · ${times} · 안전(조우 없음)`;
  const total = table.monsters.reduce((sum, row) => sum + row.weight, 0);
  const rows = table.monsters.map((row) => {
    const extra = [weightShare(row.weight, total), ...(row.surprise === 'none' ? [] : [surpriseLabel(row.surprise)])].join(', ');
    return `${monsterName(row.monster_id)}${row.count > 1 ? ` ×${row.count}` : ''}(${extra})`;
  });
  return `${place} · ${times} · ${table.chance}% · ${rows.join(', ')}`;
}
