// web/apps/web/src/pages/trpg/studio/rulebooks/useRulebookActions.ts
// 룰북을 만들고 고친다(B9). 보내기와 기억하기는 재료가 함께 쓴다(useAssetActions.ts). 지우기는 DeleteAssetButton 이다.

import { createRulebook, updateRulebook } from '../../../../api/rulebooks';
import type { RulebookDetail } from '../../../../api/types';
import { useSaveAsset } from '../useAssetActions';
import { toRulebookCreate, toRulebookUpdate, type RulebookDraft } from './rulebookForm';

export function useCreateRulebook() {
  const saving = useSaveAsset<RulebookDetail>('rulebooks');
  const create = (draft: RulebookDraft) => saving.save(() => createRulebook(toRulebookCreate(draft)));
  return { busy: saving.busy, problem: saving.problem, create };
}

export function useUpdateRulebook(rulebookId: string) {
  const saving = useSaveAsset<RulebookDetail>('rulebooks');
  const update = (draft: RulebookDraft) => saving.save(() => updateRulebook(rulebookId, toRulebookUpdate(draft)));
  return { busy: saving.busy, problem: saving.problem, update };
}
