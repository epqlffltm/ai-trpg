// web/apps/web/src/pages/me/shortcuts/shortcutsQueries.ts
// 내 단축어(#981)의 읽기. 내 단축어 화면이 읽고, 저장하면 받은 목록을 그대로 넣는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchMyShortcuts } from '../../../api/shortcuts';

export function myShortcutsKey() {
  return ['asset', 'shortcuts'] as const;
}

export function myShortcutsQuery() {
  return queryOptions({ queryKey: myShortcutsKey(), queryFn: ({ signal }) => fetchMyShortcuts(signal) });
}
