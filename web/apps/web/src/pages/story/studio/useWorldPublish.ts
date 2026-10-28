// web/apps/web/src/pages/story/studio/useWorldPublish.ts
// 세계관을 게시한다(D7). 지금 저장된 초안이 새 판으로 굳는다. 저장하지 않은 탭의 고침은 들어가지 않는다.
// 게시했든 막혔든(409 problems) 점검을 다시 읽는다. 게시했으면 판의 목록, 낱개(latest_version), 내 세계관의 목록도 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { publishStoryWorld, type StoryWorldPublished } from '../../../api/storyWorlds';
import { useCharacterSending } from '../../chat/studio/characters/useCharacterSending';
import { describeWorldPublishProblem } from './worldProblem';
import { MY_WORLDS_KEY, worldKey, worldListKey } from './worldQueries';

export function useWorldPublish(worldId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeWorldPublishProblem);

  /** 낸 판, 못 냈으면 null */
  async function publish(note: string): Promise<StoryWorldPublished | null> {
    const result = await sending.send(() => publishStoryWorld(worldId, note));
    void queryClient.invalidateQueries({ queryKey: worldKey(worldId) });
    if (result) {
      void queryClient.invalidateQueries({ queryKey: worldListKey() });
      void queryClient.invalidateQueries({ queryKey: MY_WORLDS_KEY });
    }
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, publish };
}
