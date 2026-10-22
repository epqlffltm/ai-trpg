// web/apps/web/src/hooks/useNow.ts
// 지금 시각(밀리초)을 정한 사이마다 새로 읽는다. 라운드의 마감까지 남은 시간처럼 서버가 준 시각에 견줄 때 쓴다.
// active 가 꺼지면 세지 않는다(마감이 없는 라운드).

import { useEffect, useState } from 'react';

export function useNow(intervalMs = 1000, active = true): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs, active]);

  return now;
}
