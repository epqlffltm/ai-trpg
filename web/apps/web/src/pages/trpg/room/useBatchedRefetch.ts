// web/apps/web/src/pages/trpg/room/useBatchedRefetch.ts
// 이벤트가 몰려 와도 테이블을 한 번만 다시 읽는다. 라운드 하나가 닫힐 때 이벤트가 여럿 온다(화면 명세 B7 의 "값이 바뀜").
// 마지막 부름에서 BATCH_MS 가 지나면 읽는다. 화면을 떠나면 읽지 않는다.

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { tableQuery } from './roomQueries';

export const BATCH_MS = 300;

export function useBatchedRefetch(tableId: string): () => void {
  const queryClient = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  return useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      void queryClient.invalidateQueries({ queryKey: tableQuery(tableId).queryKey });
    }, BATCH_MS);
  }, [queryClient, tableId]);
}
