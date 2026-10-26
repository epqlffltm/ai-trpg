// web/apps/web/src/pages/chat/character/useStartConversation.ts
// 고른 시작 상황과 페르소나로 대화를 시작하고 대화(C3)로 간다. 한 번에 하나만 보낸다.
//   - 시작하면 내 대화의 목록(['chat', 'conversations'] 아래)을 다시 읽게 한다
//   - 판이 바뀌었을 수 있는 실패(404, start_not_found)면 캐릭터의 판을 다시 읽는다

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { startConversation } from '../../../api/chatCharacters';
import { publicCharacterQuery } from '../../gallery/galleryQueries';
import { describeStartProblem } from './startProblem';

/** 고른 시작 상황과 페르소나. persona 가 undefined 면 보내지 않는다(서버가 지난번 것을 쓴다), null 이면 없이 시작한다 */
export type StartChoice = { start: number; persona: string | null | undefined };

export function useStartConversation(characterId: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: ({ start, persona }: StartChoice) => startConversation(persona === undefined ? { character_id: characterId, start } : { character_id: characterId, start, persona_id: persona }),
    onSuccess: (conversation) => {
      void queryClient.invalidateQueries({ queryKey: ['chat', 'conversations'] });
      void navigate(`/chat/conversations/${conversation.id}`);
    },
    onError: (error) => {
      if (describeStartProblem(error).reread) void queryClient.invalidateQueries({ queryKey: publicCharacterQuery(characterId).queryKey });
    },
  });
  return {
    busy: mutation.isPending,
    problem: mutation.error ? describeStartProblem(mutation.error) : null,
    start: (choice: StartChoice) => {
      if (!mutation.isPending) mutation.mutate(choice);
    },
  };
}
