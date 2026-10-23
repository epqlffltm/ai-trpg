// web/apps/web/src/pages/trpg/studio/scenarios/usePublish.ts
// 시나리오를 게시한다(B9). 지금 저장된 내용이 새 판으로 굳는다. 저장하지 않은 탭의 고침은 들어가지 않는다.
// 게시했든 막혔든(409 problems) 점검을 다시 읽는다. 게시했으면 판의 목록도 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { publishScenario } from '../../../../api/scenarios';
import type { VersionDetail } from '../../../../api/types';
import { useSending } from '../useSending';
import { describePublishProblem } from './scenarioProblem';
import { publishCheckKey, versionsKey } from './scenarioQueries';

export function usePublish(scenarioId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();

  /** 낸 판, 못 냈으면 null */
  async function publish(note: string): Promise<VersionDetail | null> {
    const version = await sending.send(() => publishScenario(scenarioId, note), describePublishProblem);
    void queryClient.invalidateQueries({ queryKey: publishCheckKey(scenarioId) });
    if (version) void queryClient.invalidateQueries({ queryKey: versionsKey(scenarioId) });
    return version;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
