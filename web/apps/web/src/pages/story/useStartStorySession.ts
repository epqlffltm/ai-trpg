// web/apps/web/src/pages/story/useStartStorySession.ts
// 세계관의 마지막 판으로 새 세션을 만들고 그 장면(D2)으로 간다. 내 이야기의 "새로 시작"과 엔딩 화면의 "새로 시작"이 함께 쓴다.
// 페르소나를 고르지 않으면(undefined) 보내지 않아 서버가 지난번 세션의 것을 쓴다. 받은 세션을 넣어 두어 장면이 다시 읽지 않고, 내 세션의 목록은 다시 읽게 한다.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { startStorySession } from '../../api/story';
import { STORY_SESSIONS_KEY, storySessionKey } from './storyQueries';

/** 시작할 세계관과 페르소나. persona 가 undefined 면 보내지 않는다, null 이면 없이 시작한다 */
export type StoryStart = { worldId: string; persona?: string | null | undefined };

export function useStartStorySession() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: ({ worldId, persona }: StoryStart) => startStorySession(worldId, persona),
    onSuccess: async (session) => {
      queryClient.setQueryData(storySessionKey(session.id), session);
      await queryClient.invalidateQueries({ queryKey: STORY_SESSIONS_KEY });
      void navigate(`/story/sessions/${encodeURIComponent(session.id)}`);
    },
  });
}
