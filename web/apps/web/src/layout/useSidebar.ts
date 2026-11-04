// web/apps/web/src/layout/useSidebar.ts
// 왼쪽 메뉴 열을 펼쳤는지. 플레이 화면에 들어가면 접고, 나오면 편다. 그 사이에는 ☰ 로 바꾼 대로 둔다.
// 브라우저에 두지 않는다. 화면을 새로 열면 화면마다의 처음 모양이다.

import { useCallback, useState } from 'react';
import { isPlayPath } from './sidebarRoutes';

export type Sidebar = { open: boolean; toggle: () => void };

export function useSidebar(pathname: string): Sidebar {
  const play = isPlayPath(pathname);
  const [state, setState] = useState({ play, open: !play });
  const toggle = useCallback(() => setState((before) => ({ ...before, open: !before.open })), []);
  // 플레이 화면에 들고 날 때만 처음 모양으로 돌린다(그리는 중에 이전 값과 비교해 상태를 고친다)
  if (state.play !== play) {
    setState({ play, open: !play });
    return { open: !play, toggle };
  }
  return { open: state.open, toggle };
}
