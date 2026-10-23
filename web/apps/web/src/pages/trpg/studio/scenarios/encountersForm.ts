// web/apps/web/src/pages/trpg/studio/scenarios/encountersForm.ts
// 조우(B9 몬스터 탭). 장소 하나에 몬스터 하나가 1~10 마리, 누가 기습하는가. 순수한 함수다.
// 같은 장소의 같은 몬스터는 한 줄이다. 시트를 적은 몬스터만 놓을 수 있다(encounter_monster_missing).
// 네임드 몬스터는 판 전체에 한 마리다: 한 줄에 둘 이상이거나 두 줄 이상에 나오면 막는다(unique_monster_repeated).

import type { Encounter, EncounterBody, Surprise } from '../../../../api/types';
import { wholeNumber } from '../rulebooks/rulebookForm';
import type { MonsterChoice } from './useBestiaryMonsters';

export const MAX_ENCOUNTERS = 50;
export const ENCOUNTER_MAX_COUNT = 10;

const SURPRISES: Record<Surprise, string> = { none: '기습 없음', monsters: '몬스터가 매복', party: '일행이 기습' };

export const SURPRISE_VALUES = Object.keys(SURPRISES) as Surprise[];

export function surpriseLabel(surprise: Surprise): string {
  return SURPRISES[surprise];
}

export type EncounterDraft = { place: string; monster: string; count: string; surprise: Surprise };

export function encounterDraft(encounter: Encounter | null): EncounterDraft {
  return {
    place: encounter?.place_id ?? '',
    monster: encounter?.monster_id ?? '',
    count: String(encounter?.count ?? 1),
    surprise: encounter?.surprise ?? 'none',
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
  const unique = monsters.find((monster) => monster.id === draft.monster)?.unique ?? false;
  if (unique && !hints.monster) {
    if (count !== null && count > 1) hints.count = '네임드 몬스터는 판 전체에 한 마리입니다.';
    else if (others.some((one) => one.monster_id === draft.monster)) hints.monster = '네임드 몬스터는 판 전체에 한 마리입니다. 다른 장소에 이미 있습니다.';
  }
  return hints;
}

export function toEncounter(draft: EncounterDraft): EncounterBody {
  return { place_id: draft.place, monster_id: draft.monster, count: Number(draft.count.trim()), surprise: draft.surprise };
}

export function withEncounter(encounters: Encounter[], at: number | null, encounter: EncounterBody): EncounterBody[] {
  return at === null ? [...encounters, encounter] : encounters.map((one, index) => (index === at ? encounter : one));
}

export function withoutEncounter(encounters: Encounter[], at: number): EncounterBody[] {
  return encounters.filter((_, index) => index !== at);
}

/** 목록의 한 줄. "지하 묘지 · 구울 ×3 · 몬스터가 매복" */
export function encounterLine(encounter: Encounter, placeName: (id: string) => string, monsterName: (id: string) => string): string {
  const parts = [placeName(encounter.place_id), `${monsterName(encounter.monster_id)} ×${encounter.count}`];
  if (encounter.surprise !== 'none') parts.push(surpriseLabel(encounter.surprise));
  return parts.join(' · ');
}
