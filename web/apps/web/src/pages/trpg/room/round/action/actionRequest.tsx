// web/apps/web/src/pages/trpg/room/round/action/actionRequest.tsx
// 상태 패널(B7)에서 선언 입력으로 가는 길. 패널의 "쓰기", "건네기", "가기" 같은 단추가 행동의 칸을 채워 달라고 부탁하고,
// 선언 입력이 그것을 받아 채운다. 보내는 것은 선언 입력이다(패널은 상태를 바꾸지 않는다).
//
// 둘은 화면의 다른 가지에 있어 테이블 방(TableRoom)이 이 부탁 하나를 들고 나눠 준다.
// 부탁은 한 번 받으면 지운다(take). 같은 단추를 다시 누르면 새 부탁이다(번호가 바뀐다).

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import type { ActionDraft } from './actionDraft';

export type ActionRequest = { id: number; patch: Partial<ActionDraft> };

type ActionRequests = {
  pending: ActionRequest | null;
  request: (patch: Partial<ActionDraft>) => void;
  take: (id: number) => void;
};

const NO_REQUESTS: ActionRequests = { pending: null, request: () => undefined, take: () => undefined };

const ActionRequestContext = createContext<ActionRequests>(NO_REQUESTS);

export function ActionRequestProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<ActionRequest | null>(null);
  const request = useCallback((patch: Partial<ActionDraft>) => {
    setPending((current) => ({ id: (current?.id ?? 0) + 1, patch }));
  }, []);
  const take = useCallback((id: number) => {
    setPending((current) => (current?.id === id ? null : current));
  }, []);
  const value = useMemo(() => ({ pending, request, take }), [pending, request, take]);
  return <ActionRequestContext.Provider value={value}>{children}</ActionRequestContext.Provider>;
}

export function useActionRequests(): ActionRequests {
  return useContext(ActionRequestContext);
}
