// web/apps/web/src/pages/story/useStoryTurn.ts
// 답 하나를 받는다(말 보내기, 다시 생성). 한 번에 하나만이다(서버도 한 세션에 한 생성이다).
//   - 흘러 들어오는 조각은 storyTurnState 로 쌓고, 끝나면(done, failed, 끊김) 세션을 다시 읽은 뒤 흘린 글을 지운다. 저장한 답을 믿는다
//   - 시작 전의 거절은 storyTurnProblem 의 한 줄이다. 실패(failed)는 청구하지 않았다는 한 줄이다
//   - 화면을 떠나면 읽기만 멈춘다(서버의 생성은 멈추지 않는다). 멈추기는 stop 이다
// 흐름은 chat 의 useConversationTurn 과 같다. 메시지의 모양(말 조각)이 달라 따로 둔다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { readTurnStream } from '../../api/chatTurns';
import { ApiError } from '../../api/errors';
import { stopStoryGeneration } from '../../api/story';
import { failedText } from '../chat/conversation/turnState';
import type { TurnProblem } from '../chat/conversation/turnProblem';
import { STORY_SESSIONS_KEY, storySessionKey } from './storyQueries';
import { describeStoryTurnProblem } from './storyTurnProblem';
import { applyStoryTurnMessage, EMPTY_STORY_TURN, type StoryTurnState } from './storyTurnState';

export type StoryTurnOpener = (signal: AbortSignal) => Promise<Response>;

export function useStoryTurn(sessionId: string) {
  const queryClient = useQueryClient();
  const running = useRef<AbortController | null>(null);
  const [turn, setTurn] = useState<StoryTurnState | null>(null);
  const [problem, setProblem] = useState<TurnProblem | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => () => running.current?.abort(), []);

  const settle = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: storySessionKey(sessionId) }),
      queryClient.invalidateQueries({ queryKey: STORY_SESSIONS_KEY }),
    ]);
  }, [queryClient, sessionId]);

  /** 답을 받는다. 서버가 말을 받아들였으면(스트림이 열렸거나, 거절이어도 말을 저장했으면) true */
  const run = useCallback(
    async (open: StoryTurnOpener): Promise<boolean> => {
      if (running.current) return false;
      const controller = new AbortController();
      running.current = controller;
      setProblem(null);
      setFailure(null);
      setTurn(EMPTY_STORY_TURN);
      let state = EMPTY_STORY_TURN;
      let taken = false;
      try {
        const response = await open(controller.signal);
        taken = true;
        await readTurnStream(
          response,
          (message) => {
            state = applyStoryTurnMessage(state, message);
            setTurn(state);
          },
          controller.signal,
        );
        if (state.end?.kind === 'failed') setFailure(failedText(state.end.code));
      } catch (error) {
        if (controller.signal.aborted) return taken;
        setProblem(describeStoryTurnProblem(error));
        taken = error instanceof ApiError && typeof error.body.message_id === 'string';
      }
      if (controller.signal.aborted) return taken;
      await settle();
      running.current = null;
      setTurn(null);
      return taken;
    },
    [settle],
  );

  const stop = useCallback(async () => {
    const generationId = turn?.generationId;
    if (!generationId) return;
    try {
      await stopStoryGeneration(generationId);
    } catch {
      // 멈출 것이 없다(이미 끝났다). 끝은 스트림이 알린다
    }
  }, [turn?.generationId]);

  const clearNotice = useCallback(() => {
    setProblem(null);
    setFailure(null);
  }, []);

  return { turn, problem, failure, run, stop, clearNotice };
}
