// web/apps/web/src/pages/trpg/room/useTypingPeople.ts
// 채팅을 입력 중인 사람들. 스트림의 typing 을 받으면 SHOW_MS 동안 보이고 스스로 지운다(서버는 멈췄다고 알리지 않는다).
// 그 사람의 채팅이 오면 바로 지운다. 화면이 닫혀도 남는 것이 없다(메모리에만).

import { useCallback, useEffect, useState } from 'react';

export const SHOW_MS = 5000;

export type TypingPeople = {
  /** 지금 입력 중인 사람의 ID */
  userIds: string[];
  add: (userId: string) => void;
  remove: (userId: string) => void;
};

export function useTypingPeople(): TypingPeople {
  const [until, setUntil] = useState<ReadonlyMap<string, number>>(new Map());

  const add = useCallback((userId: string) => {
    setUntil((current) => new Map(current).set(userId, Date.now() + SHOW_MS));
  }, []);

  const remove = useCallback((userId: string) => {
    setUntil((current) => withoutKey(current, userId));
  }, []);

  useEffect(() => {
    if (until.size === 0) return undefined;
    const soonest = Math.min(...until.values());
    const timer = setTimeout(() => setUntil((current) => withoutExpired(current, Date.now())), Math.max(0, soonest - Date.now()));
    return () => clearTimeout(timer);
  }, [until]);

  return { userIds: [...until.keys()], add, remove };
}

function withoutKey(map: ReadonlyMap<string, number>, key: string): ReadonlyMap<string, number> {
  if (!map.has(key)) return map;
  const next = new Map(map);
  next.delete(key);
  return next;
}

export function withoutExpired(map: ReadonlyMap<string, number>, now: number): ReadonlyMap<string, number> {
  return new Map([...map].filter(([, end]) => end > now));
}
