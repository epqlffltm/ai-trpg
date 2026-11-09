// web/apps/web/src/pages/trpg/studio/scenarios/encountersForm.ts
// 조우(B9 몬스터 탭). 장소 하나에 몬스터 하나가 1~10 마리, 누가 기습하는가. 순수한 함수다.
// 같은 장소의 같은 몬스터는 한 줄이다. 시트를 적은 몬스터만 놓을 수 있다(encounter_monster_missing).
// 네임드 몬스터는 판 전체에 한 마리다: 한 줄에 둘 이상이거나 두 줄 이상에 나오면 막는다(unique_monster_repeated).
// 순찰 경로(#254)는 처음 자리에서 적은 장소들을 차례로 돌고 처음 자리로 돌아온다. 같은 장소가 잇달아 오면 막는다
// (처음 자리로 돌아오는 끝도 본다). 장소끼리 이웃하지 않아도 된다(서버가 가장 짧은 길로 간다).

import type { Encounter, EncounterBody, Surprise } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import type { MonsterChoice } from './useBestiaryMonsters';

export const MAX_ENCOUNTERS = 50;
export const ENCOUNTER_MAX_COUNT = 10;
// 서버의 한도(trpg-server/app/assets/models.py 의 PATROL_MAX_PLACES)
export const PATROL_MAX_PLACES = 10;

const SURPRISES: Record<Surprise, string> = { none: '기습 없음', monsters: '몬스터가 매복', party: '일행이 기습' };

export const SURPRISE_VALUES = Object.keys(SURPRISES) as Surprise[];

export function surpriseLabel(surprise: Surprise): string {
  return SURPRISES[surprise];
}

export type EncounterDraft = {
  place: string;
  monster: string;
  count: string;
  surprise: Surprise;
  /** 순찰 경로(#254). 장소 항목의 id 들이다 */
  patrol: string[];
};

export function encounterDraft(encounter: Encounter | null): EncounterDraft {
  return {
    place: encounter?.place_id ?? '',
    monster: encounter?.monster_id ?? '',
    count: String(encounter?.count ?? 1),
    surprise: encounter?.surprise ?? 'none',
    patrol: encounter?.patrol ?? [],
  };
}

/** 보내기 전에 알릴 것. at 은 고치는 줄의 차례(새 줄이면 null) */
export function encounterHints(draft: EncounterDraft, encounters: Encounter[], at: number | null, monsters: MonsterChoice[]): Record<string, string> {
  const hints: Record<string, string> = {};
  const others = encounters.filter((_, index) => index !== at);
  if (draft.place === '') hints.place = '장소를 골라 주세요.';
  if (draft.monster === '') hints.monster = '몬스터를 골라 주세요.';
  else if (others.some((one) => one.place_id === draft.place && one.monster_id === draft.monster)) hints.monster = '이 장소에 이 몬스터의 줄이 이미 있습니다. 한 줄에 마리 수로 적어 주세요.';
  const count = wholeNumber(draft.count, 1, ENCOUNTER_MAX_COUNT);
  if (count === null) hints.count = `1~${ENCOUNTER_MAX_COUNT} 사이의 정수입니다.`;
  const patrol = patrolHint(draft.place, draft.patrol);
  if (patrol) hints.patrol = patrol;
  const unique = monsters.find((monster) => monster.id === draft.monster)?.unique ?? false;
  if (unique && !hints.monster) {
    if (count !== null && count > 1) hints.count = '네임드 몬스터는 판 전체에 한 마리입니다.';
    else if (others.some((one) => one.monster_id === draft.monster)) hints.monster = '네임드 몬스터는 판 전체에 한 마리입니다. 다른 장소에 이미 있습니다.';
  }
  return hints;
}

/** 순찰 경로의 문제. 고르지 않은 줄이 있거나, 같은 장소가 잇달아 오면(처음 자리로 돌아오는 끝도) 글이 있다 */
export function patrolHint(place: string, patrol: string[]): string | null {
  if (patrol.length === 0) return null;
  if (patrol.some((one) => one === '')) return '순찰할 장소를 골라 주세요.';
  const loop = [place, ...patrol];
  const repeats = loop.some((here, index) => here === loop[(index + 1) % loop.length]);
  return repeats ? '같은 장소가 잇달아 있습니다. 순찰은 처음 자리에서 시작해 처음 자리로 돌아옵니다.' : null;
}

/** 순찰 경로의 한 줄을 바꾸거나(at), 끝에 빈 줄을 더하거나(at 이 null), 뺀다(place 가 null) */
export function withPatrolPlace(patrol: string[], at: number | null, place: string | null): string[] {
  if (at === null) return patrol.length < PATROL_MAX_PLACES ? [...patrol, ''] : patrol;
  if (place === null) return patrol.filter((_, index) => index !== at);
  return patrol.map((one, index) => (index === at ? place : one));
}

export function toEncounter(draft: EncounterDraft): EncounterBody {
  return { place_id: draft.place, monster_id: draft.monster, count: Number(draft.count.trim()), surprise: draft.surprise, patrol: draft.patrol };
}

export function withEncounter(encounters: Encounter[], at: number | null, encounter: EncounterBody): EncounterBody[] {
  return at === null ? [...encounters, encounter] : encounters.map((one, index) => (index === at ? encounter : one));
}

export function withoutEncounter(encounters: Encounter[], at: number): EncounterBody[] {
  return encounters.filter((_, index) => index !== at);
}

/** 목록의 한 줄. "지하 묘지 · 구울 ×3 · 몬스터가 매복 · 순찰 2곳" */
export function encounterLine(encounter: Encounter, placeName: (id: string) => string, monsterName: (id: string) => string): string {
  const parts = [placeName(encounter.place_id), `${monsterName(encounter.monster_id)} ×${encounter.count}`];
  if (encounter.surprise !== 'none') parts.push(surpriseLabel(encounter.surprise));
  const patrol = encounter.patrol ?? [];
  if (patrol.length > 0) parts.push(`순찰 ${patrol.length}곳`);
  return parts.join(' · ');
}
