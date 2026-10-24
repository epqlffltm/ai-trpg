// web/apps/web/src/pages/notifications/useReadAll.ts
// 모두 읽음. 화면이 받은 가장 새 번호까지만 읽음으로 한다(그 뒤에 막 들어온 것은 남는다). 마치면 목록과 수를 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { markAllNotificationsRead } from '../../api/notifications';
import { NOTIFICATION_KEY } from './notificationQueries';
import { notificationProblemText } from './notificationProblem';

type State = { busy: boolean; problem: string | null };

export function useReadAll() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ busy: false, problem: null });

  async function readAll(upTo: number): Promise<void> {
    if (state.busy) return;
    setState({ busy: true, problem: null });
    try {
      await markAllNotificationsRead(upTo);
      setState({ busy: false, problem: null });
    } catch (error) {
      setState({ busy: false, problem: notificationProblemText(error) });
    }
    void queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEY });
  }

  return { ...state, readAll };
}
