// web/apps/web/src/pages/trpg/studio/scenarios/useBestiaryMonsters.ts
// 시나리오에 붙인 몬스터 모음들의 몬스터(B9 몬스터 탭). 모음마다 몬스터를 읽어(monstersQuery) 모은다.
// 저장된 몬스터 모음 목록을 따른다. 네임드(unique)는 판 전체에 한 마리만 둘 수 있다.

import { useQueries } from '@tanstack/react-query';
import type { Monster } from '../../../../api/types';
import { monstersQuery } from '../bestiaries/bestiaryQueries';

export type MonsterChoice = { id: string; name: string; unique: boolean };

export function monstersOf(lists: (Monster[] | undefined)[]): MonsterChoice[] {
  return lists.flatMap((monsters) => (monsters ?? []).map(({ id, name, unique }) => ({ id, name, unique })));
}

export function useBestiaryMonsters(bestiaryIds: string[]) {
  const results = useQueries({ queries: bestiaryIds.map((bestiaryId) => monstersQuery(bestiaryId)) });
  return {
    monsters: monstersOf(results.map((result) => result.data)),
    pending: results.some((result) => result.isPending),
    failed: results.some((result) => result.isError),
  };
}

/** 몬스터의 이름. 붙인 모음에 없으면(뗐거나 지웠다) 그렇다고 적는다 */
export function monsterNameOf(monsters: MonsterChoice[]): (monsterId: string) => string {
  return (monsterId) => monsters.find((monster) => monster.id === monsterId)?.name ?? '(붙인 모음에 없는 몬스터)';
}
