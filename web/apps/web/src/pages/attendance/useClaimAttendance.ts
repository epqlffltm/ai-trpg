// web/apps/web/src/pages/attendance/useClaimAttendance.ts
// 오늘의 출석 보상을 받는다(A9). 한 번에 하나만 보낸다. 받으면 오늘의 출석과 잔액·원장을 다시 읽는다.
// 이미 받았다(409)면 오늘의 출석을 다시 읽어 단추를 막는다. 받은 것(실버, 상자)은 화면에 남겨 둔다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { claimAttendance } from '../../api/attendance';
import type { AttendanceClaim } from '../../api/types';
import { WALLET_KEY } from '../wallet/walletQueries';
import { describeClaimProblem } from './attendanceProblem';
import { ATTENDANCE_KEY } from './attendanceQueries';

type State = { busy: boolean; problem: string | null; claimed: AttendanceClaim | null };

export function useClaimAttendance() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ busy: false, problem: null, claimed: null });

  function refresh(wallet: boolean) {
    void queryClient.invalidateQueries({ queryKey: [...ATTENDANCE_KEY, 'today'] });
    if (wallet) void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
  }

  async function claim() {
    if (state.busy) return;
    setState({ busy: true, problem: null, claimed: null });
    try {
      const claimed = await claimAttendance();
      setState({ busy: false, problem: null, claimed });
      refresh(true);
    } catch (error) {
      const problem = describeClaimProblem(error);
      setState({ busy: false, problem: problem.message, claimed: null });
      if (problem.alreadyClaimed) refresh(false);
    }
  }

  return { ...state, claim };
}
