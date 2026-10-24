// web/apps/web/src/pages/notifications/useMuteToggle.ts
// 알림의 종류 하나를 끄거나 다시 켠다. 답(바뀐 뒤의 설정 전체)으로 설정을 바꾼다. 한 번에 하나만 보낸다.
// 422(끌 수 없는 종류가 되었다)면 설정을 다시 읽는다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError } from '../../api/errors';
import { setMute } from '../../api/notifications';
import { mutesQuery } from './notificationQueries';
import { notificationProblemText } from './notificationProblem';

type State = { busyKind: string | null; problem: string | null };

export function useMuteToggle() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ busyKind: null, problem: null });

  async function toggle(kind: string, muted: boolean): Promise<void> {
    if (state.busyKind) return;
    setState({ busyKind: kind, problem: null });
    try {
      queryClient.setQueryData(mutesQuery().queryKey, await setMute(kind, muted));
      setState({ busyKind: null, problem: null });
    } catch (error) {
      setState({ busyKind: null, problem: notificationProblemText(error) });
      if (error instanceof ApiError && error.status === 422) void queryClient.invalidateQueries({ queryKey: mutesQuery().queryKey });
    }
  }

  return { ...state, toggle };
}
