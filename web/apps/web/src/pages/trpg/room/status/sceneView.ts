// web/apps/web/src/pages/trpg/room/status/sceneView.ts
// 지금 있는 곳의 인물과 몬스터(#254 의 화면). 순수한 함수다. 장면의 응답(GET /rounds/current/people)에서 고르고 글로 바꾼다.
// 서버는 몬스터의 HP 숫자를 주지 않는다. 몸 상태(condition)와 부상, 지닌 물건만 보인다.
// 몬스터는 내가 선 곳의 것만 보인다(칠 수 있는 것과 같다). 인물은 내가 선 곳의 것과 자리가 없는 것(누구나 겨눈다)을 보인다.

import type { Ruleset, SceneCast, SceneMonster, ScenePerson } from '../../../../api/types';
import { injuryName } from './statusView';

/** 보일 한 줄. kind 와 id 를 합친 것이 행동의 대상(target)이다 */
export type SceneEntry = {
  kind: 'npc' | 'monster';
  id: string;
  name: string;
  /** 몸 상태와 입은 부상. 비어 있으면 붙일 말이 없다 */
  state: string[];
  /** 지닌 물건. 장비 다음 소지품의 차례다(서버의 차례) */
  items: string[];
  /** 칠 수 있는가. 죽은 것은 치지 못한다 */
  harmable: boolean;
};

const PERSON_STATUS: Record<ScenePerson['status'], string | null> = {
  alive: null,
  downed: '쓰러짐',
  dead: '죽음',
};

/** 지금 있는 곳의 인물과 몬스터. 내가 맵에 서 있지 않으면 자리가 없는 인물만 남는다 */
export function sceneHere(cast: SceneCast | undefined, here: string | null | undefined, rules: Ruleset): SceneEntry[] {
  if (!cast) return [];
  const people = cast.people.filter((person) => person.place_id === null || (here && person.place_id === here)).map((person) => personEntry(person, rules));
  const monsters = here ? cast.monsters.filter((monster) => monster.place_id === here).map((monster) => monsterEntry(monster, rules)) : [];
  return [...people, ...monsters];
}

function personEntry(person: ScenePerson, rules: Ruleset): SceneEntry {
  const status = PERSON_STATUS[person.status];
  return {
    kind: 'npc',
    id: person.id,
    name: person.name,
    state: [...(status ? [status] : []), ...injuryNames(person.injuries, rules)],
    items: itemNames(person.items ?? []),
    harmable: person.status !== 'dead',
  };
}

function monsterEntry(monster: SceneMonster, rules: Ruleset): SceneEntry {
  return {
    kind: 'monster',
    id: monster.id,
    name: monster.name,
    state: [monster.condition, ...injuryNames(monster.injuries ?? [], rules)],
    items: itemNames(monster.items ?? []),
    harmable: monster.status !== 'dead',
  };
}

function injuryNames(keys: string[], rules: Ruleset): string[] {
  return keys.map((key) => injuryName(rules, key));
}

function itemNames(items: { name: string; count: number }[]): string[] {
  return items.map((item) => (item.count > 1 ? `${item.name} ×${item.count}` : item.name));
}

/** 한 줄의 덧붙임. 몸 상태와 부상, 지닌 것. 붙일 것이 없으면 null */
export function sceneEntryNote(entry: SceneEntry): string | null {
  const parts = [...entry.state];
  if (entry.items.length > 0) parts.push(`지닌 것: ${entry.items.join(', ')}`);
  return parts.length > 0 ? parts.join(' · ') : null;
}
