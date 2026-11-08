// web/apps/web/src/pages/attendance/useClaimAttendance.ts
// 오늘의 출석 보상을 받는다(A9). 한 번에 하나만 보낸다. 받으면 오늘의 출석과 잔액·원장을 다시 읽는다.
// 실버는 인증 서버의 워커가 몇 초 뒤 지갑에 맡긴다. 받은 직후의 잔액은 그 전의 것이라, 잔액이 바뀔 때까지 몇 번 더 읽는다
// (useWalletCatchUp). 바뀌기 전에 화면을 떠나면 멈춘다.
// 이미 받았다(409)면 오늘의 출석을 다시 읽어 단추를 막는다. 받은 것(실버, 상자)은 화면에 남겨 둔다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { claimAttendance } from '../../api/attendance';
import type { AttendanceClaim } from '../../api/attendance';
import { useWalletCatchUp } from '../wallet/useWalletCatchUp';
import { WALLET_KEY, walletQuery } from '../wallet/walletQueries';
import { describeClaimProblem } from './attendanceProblem';
import { ATTENDANCE_KEY } from './attendanceQueries';

type State = { busy: boolean; problem: string | null; claimed: AttendanceClaim | null };

export function useClaimAttendance() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<State>({ busy: false, problem: null, claimed: null });
  const catchUp = useWalletCatchUp();

  function refresh(wallet: boolean) {
    void queryClient.invalidateQueries({ queryKey: [...ATTENDANCE_KEY, 'today'] });
    if (wallet) void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
  }

  async function claim() {
    if (state.busy) return;
    setState({ busy: true, problem: null, claimed: null });
    // 받기 전의 잔액. 이것과 달라질 때까지 따라잡는다
    const before = queryClient.getQueryData(walletQuery().queryKey);
    try {
      const claimed = await claimAttendance();
      setState({ busy: false, problem: null, claimed });
      refresh(true);
      catchUp.start(before);
    } catch (error) {
      const problem = describeClaimProblem(error);
      setState({ busy: false, problem: problem.message, claimed: null });
      if (problem.alreadyClaimed) refresh(false);
    }
  }

  return { ...state, claim };
}
