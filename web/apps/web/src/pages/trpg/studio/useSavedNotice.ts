// web/apps/web/src/pages/trpg/studio/useSavedNotice.ts
// 고치기 화면 위의 한 줄(B9). 막 만들고 왔으면(navigate 의 state.created) "만들었습니다.", 저장하면 "저장했습니다."

import { useState } from 'react';
import { useLocation } from 'react-router';

/** 만들기 화면이 고치기로 넘어갈 때 넘기는 state */
export const CREATED_STATE = { created: true } as const;

function wasCreated(state: unknown): boolean {
  return state !== null && typeof state === 'object' && (state as Record<string, unknown>).created === true;
}

export function useSavedNotice() {
  const location = useLocation();
  const [notice, setNotice] = useState<string | null>(wasCreated(location.state) ? '만들었습니다.' : null);
  return {
    notice,
    clear: () => setNotice(null),
    saved: () => setNotice('저장했습니다.'),
  };
}
