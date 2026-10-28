// web/apps/web/src/pages/story/studio/useWorldSave.ts
// 세계관의 탭 하나를 저장한다(D7). 그 탭의 칸만 PATCH 로 보내고, 받은 세계관을 낱개의 읽기에 넣는다.
// 저장하면 게시 점검과 목록(이름, 고친 날)을 다시 읽는다. 무엇을 고쳤든 게시할 수 있는지가 바뀔 수 있다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateStoryWorld, type StoryWorldDetail, type StoryWorldUpdate } from '../../../api/storyWorlds';
import { useCharacterSending } from '../../chat/studio/characters/useCharacterSending';
import { describeWorldProblem } from './worldProblem';
import { worldCheckKey, worldKey, worldListKey } from './worldQueries';

export function useWorldSave(worldId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeWorldProblem);
  const [saved, setSaved] = useState(false);

  /** 저장한 세계관, 못 했으면 null */
  async function save(body: StoryWorldUpdate): Promise<StoryWorldDetail | null> {
    setSaved(false);
    const result = await sending.send(() => updateStoryWorld(worldId, body));
    if (!result) return null;
    setSaved(true);
    queryClient.setQueryData(worldKey(worldId), result);
    void queryClient.invalidateQueries({ queryKey: worldCheckKey(worldId) });
    void queryClient.invalidateQueries({ queryKey: worldListKey() });
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, saved, save };
}
