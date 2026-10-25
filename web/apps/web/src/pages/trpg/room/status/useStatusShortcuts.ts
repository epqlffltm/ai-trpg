// web/apps/web/src/pages/trpg/room/status/useStatusShortcuts.ts
// 상태 패널의 단축키(C, I, J, L)를 문서 전체에서 듣는다. 고를 탭은 statusTabs.ts 의 tabForKey 가 정한다.
// 설정(A12)에서 단축키를 끄면 듣지 않는다.

import { useEffect } from 'react';
import { useSettings } from '../../../../settings/useSettings';
import { tabForKey, type StatusTab } from './statusTabs';

export function useStatusShortcuts(onTab: (tab: StatusTab) => void): void {
  const enabled = useSettings().settings.shortcuts;
  useEffect(() => {
    if (!enabled) return undefined;
    function listen(event: KeyboardEvent) {
      const target = event.target instanceof HTMLElement ? event.target : null;
      const tab = tabForKey({
        key: event.key,
        ctrlKey: event.ctrlKey,
        altKey: event.altKey,
        metaKey: event.metaKey,
        targetTag: target?.tagName ?? '',
        targetEditable: target?.isContentEditable ?? false,
      });
      if (tab) onTab(tab);
    }
    document.addEventListener('keydown', listen);
    return () => document.removeEventListener('keydown', listen);
  }, [onTab, enabled]);
}
