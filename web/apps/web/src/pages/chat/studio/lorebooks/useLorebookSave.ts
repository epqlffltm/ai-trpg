// web/apps/web/src/pages/chat/studio/lorebooks/useLorebookSave.ts
// 로어북의 폼 하나(이름과 설명, 항목)를 저장한다. 그 폼의 칸만 PATCH 로 보내고, 받은 로어북을 낱개의 읽기에 넣는다.
// 저장하면 목록(이름, 항목 수, 고친 날)을 무른다. 게시한 판은 그대로라 캐릭터에는 아직 가지 않는다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateLorebook } from '../../../../api/assetLorebooks';
import type { AssetLorebookDetail, AssetLorebookUpdate } from '../../../../api/types';
import { useCharacterSending } from '../characters/useCharacterSending';
import { describeLorebookProblem } from './lorebookProblem';
import { lorebookKey, lorebookListKey, lorebookPickerKey } from './lorebookQueries';

export function useLorebookSave(lorebookId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeLorebookProblem);
  const [saved, setSaved] = useState(false);

  /** 저장한 로어북, 못 했으면 null */
  async function save(body: AssetLorebookUpdate): Promise<AssetLorebookDetail | null> {
    setSaved(false);
    const result = await sending.send(() => updateLorebook(lorebookId, body));
    if (!result) return null;
    setSaved(true);
    queryClient.setQueryData(lorebookKey(lorebookId), result);
    void queryClient.invalidateQueries({ queryKey: lorebookListKey() });
    void queryClient.invalidateQueries({ queryKey: lorebookPickerKey() });
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, saved, save };
}
