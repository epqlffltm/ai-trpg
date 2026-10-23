// web/apps/web/src/pages/chat/studio/characters/useCharacterPublish.ts
// 캐릭터를 게시한다(C6). 지금 저장된 초안이 새 판으로 굳는다. 저장하지 않은 탭의 고침은 들어가지 않는다.
// 게시했든 막혔든(409 problems) 점검을 다시 읽는다. 게시했으면 판의 목록과 낱개(latest_version)도 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { publishCharacter } from '../../../../api/characters';
import type { AssetPublishResult } from '../../../../api/types';
import { describeCharacterPublishProblem } from './characterProblem';
import { characterKey, characterListKey } from './characterQueries';
import { useCharacterSending } from './useCharacterSending';

export function useCharacterPublish(characterId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeCharacterPublishProblem);

  /** 낸 판, 못 냈으면 null */
  async function publish(note: string): Promise<AssetPublishResult | null> {
    const result = await sending.send(() => publishCharacter(characterId, note));
    // 낱개 아래의 점검과 판, 낱개 자신(latest_version)을 함께 다시 읽는다
    void queryClient.invalidateQueries({ queryKey: characterKey(characterId) });
    if (result) void queryClient.invalidateQueries({ queryKey: characterListKey() });
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
