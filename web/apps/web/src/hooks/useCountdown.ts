// web/apps/web/src/hooks/useCountdown.ts
// 정한 시각까지 남은 초를 1초마다 센다. 다시 누를 수 있을 때까지(429), 티켓이 만료될 때까지 쓴다.
// 남은 초가 아니라 끝나는 시각을 들고 있어서 화면이 다시 그려져도 처음부터 세지 않는다.
// 세기를 시작하는 것(start)은 누른 때(이벤트)에 한다. 지금 시각도 그때 함께 적어 첫 화면부터 맞는 초를 보인다.

import { useCallback, useEffect, useState } from 'react';

export type Countdown = {
  /** 남은 초. 끝났거나 시작하지 않았으면 0 */
  remaining: number;
  start: (seconds: number) => void;
};

export function useCountdown(initialEndsAt: number | null = null): Countdown {
  const [endsAt, setEndsAt] = useState(initialEndsAt);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (endsAt === null) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [endsAt]);

  const start = useCallback((seconds: number) => {
    const startedAt = Date.now();
    setNow(startedAt);
    setEndsAt(startedAt + seconds * 1000);
  }, []);

  const remaining = endsAt === null ? 0 : Math.max(0, Math.ceil((endsAt - now) / 1000));
  return { remaining, start };
}

/** 지금부터 seconds 초 뒤의 시각 */
export function secondsFromNow(seconds: number): number {
  return Date.now() + seconds * 1000;
}

/** 남은 초를 읽기 좋은 글로(4분 30초, 45초) */
export function formatRemaining(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes === 0) return `${rest}초`;
  return rest === 0 ? `${minutes}분` : `${minutes}분 ${rest}초`;
}
