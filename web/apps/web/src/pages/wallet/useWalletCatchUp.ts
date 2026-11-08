// web/apps/web/src/pages/wallet/useWalletCatchUp.ts
// 늦게 들어오는 돈을 따라잡는다(walletCatchUp.ts). start(전의 잔액)를 부르면 정한 사이마다 잔액을 다시 읽고,
// 바뀌면 원장까지 함께 무르고 멈춘다. 끝까지 그대로면 그냥 멈춘다(돈이 안 들어왔다고 단정하지 않는다. 창에 돌아오면 또 읽는다).
// 다시 부르면 앞의 따라잡기를 멈추고 새로 시작한다. 화면이 사라지면 멈춘다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import type { Wallet } from '../../api/types';
import { CATCH_UP_DELAYS, walletChanged } from './walletCatchUp';
import { WALLET_KEY, walletQuery } from './walletQueries';

export function useWalletCatchUp(delays: number[] = CATCH_UP_DELAYS) {
  const queryClient = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const start = useCallback(
    (before: Wallet | undefined) => {
      stop();
      const step = (index: number) => {
        if (index >= delays.length) return;
        timer.current = setTimeout(() => {
          void queryClient.fetchQuery({ ...walletQuery(), staleTime: 0 }).then(
            (after) => {
              if (walletChanged(before, after)) void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
              else step(index + 1);
            },
            () => step(index + 1),
          );
        }, delays[index]);
      };
      step(0);
    },
    [delays, queryClient, stop],
  );

  return { start, stop };
}
