// web/apps/web/src/pages/trpg/studio/scenarios/useScenarioRules.ts
// 시나리오에 저장된 룰북의 규칙(능력치, 장비의 칸, 양의 등급 …). 캐릭터 탭과 물건·돈 탭이 칸을 만들 때 읽는다.
// 룰북이 없으면 읽지 않고 rules 는 null 이다.

import { useQuery } from '@tanstack/react-query';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { rulebookQuery } from '../rulebooks/rulebookQueries';

export function useScenarioRules(scenario: ScenarioDetail): { rules: Ruleset | null; pending: boolean; failed: boolean } {
  const rulebookId = scenario.rulebook_id;
  const query = useQuery({ ...rulebookQuery(rulebookId ?? ''), enabled: rulebookId !== null });
  return {
    rules: query.data?.rules ?? null,
    pending: rulebookId !== null && query.isPending,
    failed: query.isError,
  };
}
