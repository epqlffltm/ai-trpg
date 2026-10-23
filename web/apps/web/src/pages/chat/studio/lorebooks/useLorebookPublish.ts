// web/apps/web/src/pages/chat/studio/lorebooks/useLorebookPublish.ts
// 로어북을 게시한다. 지금 저장된 초안이 새 판으로 굳는다. 저장하지 않은 고침은 들어가지 않는다.
// 게시하면 낱개(latest_version)와 그 아래의 판, 목록, 고르기 목록(캐릭터의 로어북 탭의 "게시하지 않음")을 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { publishLorebook } from '../../../../api/assetLorebooks';
import type { AssetLorebookVersionDetail } from '../../../../api/types';
import { useCharacterSending } from '../characters/useCharacterSending';
import { describeLorebookProblem } from './lorebookProblem';
import { lorebookKey, lorebookListKey, lorebookPickerKey } from './lorebookQueries';

export function useLorebookPublish(lorebookId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeLorebookProblem);

  /** 낸 판, 못 냈으면 null */
  async function publish(note: string): Promise<AssetLorebookVersionDetail | null> {
    const result = await sending.send(() => publishLorebook(lorebookId, note));
    if (!result) return null;
    void queryClient.invalidateQueries({ queryKey: lorebookKey(lorebookId) });
    void queryClient.invalidateQueries({ queryKey: lorebookListKey() });
    void queryClient.invalidateQueries({ queryKey: lorebookPickerKey() });
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
