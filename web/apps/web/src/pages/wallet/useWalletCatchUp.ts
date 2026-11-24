// web/apps/web/src/pages/wallet/useWalletCatchUp.ts
// 늦게 들어오는 돈을 따라잡는다(walletCatchUp.ts). start(전의 잔액)를 부르면 정한 사이마다 잔액을 다시 읽고,
// 바뀌면 원장까지 함께 무르고 멈춘다. 끝까지 그대로면 그냥 멈춘다(돈이 안 들어왔다고 단정하지 않는다. 창에 돌아오면 또 읽는다).
// 다시 부르면 앞의 따라잡기를 멈추고 새로 시작한다. 화면이 사라지면 멈춘다.
// 전의 잔액을 쥐고 있지 않으면 startFresh 다. 지금 잔액을 한 번 읽어 그것을 전의 잔액으로 삼는다.
// 읽어 둔 잔액이 오래됐을 수 있을 때도 그렇다(머리의 잔액은 내 메뉴를 열 때만 읽는다). 오래된 것과 견주면 바로 바뀐 것으로 보고 멈춘다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import type { Wallet } from '../../api/types';
import { CATCH_UP_DELAYS, walletChanged } from './walletCatchUp';
import { WALLET_KEY, walletQuery } from './walletQueries';

export function useWalletCatchUp(delays: number[] = CATCH_UP_DELAYS) {
  const queryClient = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 따라잡기의 차례. 멈추면 늘린다. 읽는 중에 멈췄으면(화면이 사라졌거나 새로 시작했다) 읽은 뒤에 다음을 잡지 않는다
  const run = useRef(0);

  const stop = useCallback(() => {
    run.current += 1;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  }, []);

  useEffect(() => stop, [stop]);

  const follow = useCallback(
    (before: Wallet | undefined, mine: number) => {
      const step = (index: number) => {
        if (index >= delays.length || run.current !== mine) return;
        timer.current = setTimeout(() => {
          void queryClient.fetchQuery({ ...walletQuery(), staleTime: 0 }).then(
            (after) => {
              if (run.current !== mine) return;
              if (walletChanged(before, after)) void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
              else step(index + 1);
            },
            () => step(index + 1),
          );
        }, delays[index]);
      };
      step(0);
    },
    [delays, queryClient],
  );

  const start = useCallback(
    (before: Wallet | undefined) => {
      stop();
      follow(before, run.current);
    },
    [follow, stop],
  );

  const startFresh = useCallback(() => {
    stop();
    const mine = run.current;
    void queryClient.fetchQuery({ ...walletQuery(), staleTime: 0 }).then(
      (before) => follow(before, mine),
      () => follow(undefined, mine),
    );
  }, [follow, queryClient, stop]);

  return { start, startFresh, stop };
}
