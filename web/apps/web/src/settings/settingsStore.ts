// web/apps/web/src/settings/settingsStore.ts
// 화면 쪽 설정(A12)을 브라우저에 두고 화면에 입힌다. 한 곳에서만 바꾸고, 바뀌면 듣는 쪽(useSettings)에 알린다.
// 브라우저 저장소(localStorage)가 막혀 있으면(개인 창, 저장을 막은 브라우저) 이 창이 열려 있는 동안만 둔다(persistent: false).
// 입히기는 문서의 맨 위(html)에 data-theme, data-text-size 를 다는 것이다. 모양은 CSS 가 맡는다.

import { DEFAULT_SETTINGS, parseSettings, type Settings } from './settings';

const STORAGE_KEY = 'ai-trpg.settings';

type Snapshot = { settings: Settings; persistent: boolean };

let snapshot: Snapshot | null = null;
const listeners = new Set<() => void>();

function readStored(): Snapshot {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return { settings: parseSettings(raw ? JSON.parse(raw) : null), persistent: true };
  } catch {
    return { settings: DEFAULT_SETTINGS, persistent: false };
  }
}

function writeStored(settings: Settings): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;
  }
}

/** 지금의 설정. 처음 부를 때 브라우저에서 읽는다 */
export function getSettingsSnapshot(): Snapshot {
  snapshot ??= readStored();
  return snapshot;
}

export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 문서에 설정을 입힌다. 기본값이면 표시를 떼어 CSS 의 기본(기기 설정)이 따른다 */
export function applySettings(settings: Settings): void {
  const root = document.documentElement;
  if (settings.theme === 'system') delete root.dataset.theme;
  else root.dataset.theme = settings.theme;
  if (settings.textSize === 'normal') delete root.dataset.textSize;
  else root.dataset.textSize = settings.textSize;
}

/** 설정을 바꾼다. 저장하고, 입히고, 알린다 */
export function updateSettings(change: Partial<Settings>): void {
  const settings = { ...getSettingsSnapshot().settings, ...change };
  snapshot = { settings, persistent: writeStored(settings) };
  applySettings(settings);
  for (const listener of listeners) listener();
}

/** 시험이 서로 섞이지 않게 기억해 둔 것을 비운다 */
export function resetSettingsForTest(): void {
  snapshot = null;
}
