// web/apps/web/src/settings/useSettings.ts
// 화면 쪽 설정(A12)을 읽는 훅. 설정이 바뀌면 다시 그린다.

import { useSyncExternalStore } from 'react';
import { getSettingsSnapshot, subscribeSettings } from './settingsStore';

export function useSettings() {
  return useSyncExternalStore(subscribeSettings, getSettingsSnapshot);
}
