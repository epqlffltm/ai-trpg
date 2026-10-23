// web/apps/web/src/pages/trpg/studio/scenarios/useScenarioSave.ts
// 시나리오의 탭 하나를 저장한다(B9). 그 탭의 칸만 PATCH 로 보내고, 받은 시나리오를 낱개의 읽기에 넣는다(useSaveAsset).
// 저장하면 게시 점검을 다시 읽는다. 무엇을 고쳤든 게시할 수 있는지가 바뀔 수 있다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateScenario } from '../../../../api/scenarios';
import type { ScenarioDetail, ScenarioUpdate } from '../../../../api/types';
import { useSaveAsset } from '../useAssetActions';
import { describeScenarioSaveProblem } from './scenarioProblem';
import { publishCheckKey } from './scenarioQueries';

export function useScenarioSave(scenarioId: string) {
  const queryClient = useQueryClient();
  const saving = useSaveAsset<ScenarioDetail>('scenarios', describeScenarioSaveProblem);
  const [saved, setSaved] = useState(false);

  /** 저장한 시나리오, 못 했으면 null */
  async function save(body: ScenarioUpdate): Promise<ScenarioDetail | null> {
    setSaved(false);
    const result = await saving.save(() => updateScenario(scenarioId, body));
    if (!result) return null;
    setSaved(true);
    void queryClient.invalidateQueries({ queryKey: publishCheckKey(scenarioId) });
    return result;
  }

  return { busy: saving.busy, problem: saving.problem, saved, save };
}
