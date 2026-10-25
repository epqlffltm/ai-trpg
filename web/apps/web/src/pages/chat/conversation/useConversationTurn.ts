// web/apps/web/src/pages/chat/conversation/useConversationTurn.ts
// 답 하나를 받는다(말 보내기, 다시 생성, 이어서). 한 번에 하나만이다(서버도 한 대화에 한 생성이다).
//   - 흘러 들어오는 글은 turnState 로 쌓고, 끝나면(done, failed, 끊김) 대화를 다시 읽은 뒤 흘린 글을 지운다. 저장한 답을 믿는다
//   - 시작 전의 거절은 turnProblem 의 한 줄이다. 실패(failed)는 청구하지 않았다는 한 줄이다
//   - 끊기면 서버는 끝까지 저장한다. 다시 읽은 대화가 아직 쓰는 중이면 쿼리가 끝날 때까지 다시 묻는다
//   - 화면을 떠나면 읽기만 멈춘다(서버의 생성은 멈추지 않는다). 멈추기는 stop 이다

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { stopGeneration } from '../../../api/chatConversation';
import { ApiError } from '../../../api/errors';
import { readTurnStream } from '../../../api/chatTurns';
import { conversationKey } from './conversationQueries';
import { describeTurnProblem, type TurnProblem } from './turnProblem';
import { applyTurnMessage, EMPTY_TURN, failedText, type TurnState } from './turnState';

export type TurnOpener = (signal: AbortSignal) => Promise<Response>;

export function useConversationTurn(conversationId: string) {
  const queryClient = useQueryClient();
  const running = useRef<AbortController | null>(null);
  const [turn, setTurn] = useState<TurnState | null>(null);
  const [problem, setProblem] = useState<TurnProblem | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => () => running.current?.abort(), []);

  const settle = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: conversationKey(conversationId) }),
      queryClient.invalidateQueries({ queryKey: ['chat', 'conversations'] }),
    ]);
  }, [queryClient, conversationId]);

  /** 답을 받는다. 서버가 말을 받아들였으면(스트림이 열렸거나, 거절이어도 말을 저장했으면) true */
  const run = useCallback(
    async (open: TurnOpener): Promise<boolean> => {
      if (running.current) return false;
      const controller = new AbortController();
      running.current = controller;
      setProblem(null);
      setFailure(null);
      setTurn(EMPTY_TURN);
      let state = EMPTY_TURN;
      let taken = false;
      try {
        const response = await open(controller.signal);
        taken = true;
        await readTurnStream(response, (message) => {
          state = applyTurnMessage(state, message);
          setTurn(state);
        }, controller.signal);
        if (state.end?.kind === 'failed') setFailure(failedText(state.end.code));
      } catch (error) {
        if (controller.signal.aborted) return taken;
        setProblem(describeTurnProblem(error));
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
      await stopGeneration(generationId);
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
