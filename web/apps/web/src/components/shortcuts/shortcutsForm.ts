// web/apps/web/src/components/shortcuts/shortcutsForm.ts
// 단축어 목록의 입력(#981). 순수한 함수다. 캐릭터와 세계관의 단축어 탭, 내 단축어 화면이 함께 쓴다.
// 규칙은 서버와 같다(asset-server/app/shortcuts/schemas.py).
//
//   - 이름은 대화에서 "/이름"으로 부르는 말이다. 빈칸과 / 가 없는 10자까지, 한 목록 안에서 겹치지 않는다
//   - 설명은 고를 때 보이는 30자까지(비워도 된다), 본문은 그 턴에 붙는 400자까지(비울 수 없다)
//   - 한 목록에 20개까지. 목록의 차례가 고르는 목록의 차례다. 저장은 목록을 통째로 보낸다
//   - 본문은 사람의 입력처럼 모델에 간다. 게임의 상태(호감도, 소지품)를 바꾸지 못한다

import type { components } from '../../api/generated/asset';

export type Shortcut = components['schemas']['Shortcut'];

export const SHORTCUTS_MAX = 20;
export const SHORTCUT_NAME_MAX = 10;
export const SHORTCUT_DESCRIPTION_MAX = 30;
export const SHORTCUT_BODY_MAX = 400;

export type ShortcutDraft = { name: string; description: string; body: string };

export function shortcutDrafts(shortcuts: readonly Shortcut[] | null | undefined): ShortcutDraft[] {
  return (shortcuts ?? []).map((shortcut) => ({ name: shortcut.name, description: shortcut.description ?? '', body: shortcut.body }));
}

/** 이름의 문제. 없으면 undefined */
export function nameProblem(name: string, others: string[]): string | undefined {
  const trimmed = name.trim();
  if (trimmed === '') return '이름을 적어 주세요.';
  if (/[\s/]/.test(trimmed)) return '이름에는 빈칸과 / 를 쓸 수 없습니다.';
  if (trimmed.length > SHORTCUT_NAME_MAX) return `이름은 ${SHORTCUT_NAME_MAX}자까지입니다.`;
  if (others.includes(trimmed)) return '같은 이름의 단축어가 있습니다.';
  return undefined;
}

/** 단축어마다의 문제. 차례(0 부터) → 칸 이름 → 글 */
export function shortcutsHints(shortcuts: ShortcutDraft[]): Record<number, Record<string, string>> {
  const hints: Record<number, Record<string, string>> = {};
  shortcuts.forEach((shortcut, index) => {
    const found: Record<string, string> = {};
    const before = shortcuts.slice(0, index).map((other) => other.name.trim());
    const name = nameProblem(shortcut.name, before);
    if (name) found.name = name;
    if (shortcut.description.trim().length > SHORTCUT_DESCRIPTION_MAX) found.description = `설명은 ${SHORTCUT_DESCRIPTION_MAX}자까지입니다.`;
    if (shortcut.body.trim() === '') found.body = '본문을 적어 주세요.';
    else if (shortcut.body.trim().length > SHORTCUT_BODY_MAX) found.body = `본문은 ${SHORTCUT_BODY_MAX}자까지입니다.`;
    if (Object.keys(found).length > 0) hints[index] = found;
  });
  return hints;
}

/** 빈 단축어를 끝에 더한다. 가득 찼으면 그대로 */
export function addShortcut(shortcuts: ShortcutDraft[]): ShortcutDraft[] {
  return shortcuts.length < SHORTCUTS_MAX ? [...shortcuts, { name: '', description: '', body: '' }] : shortcuts;
}

export function removeShortcut(shortcuts: ShortcutDraft[], index: number): ShortcutDraft[] {
  return shortcuts.filter((_, at) => at !== index);
}

export function changeShortcut(shortcuts: ShortcutDraft[], index: number, changes: Partial<ShortcutDraft>): ShortcutDraft[] {
  return shortcuts.map((shortcut, at) => (at === index ? { ...shortcut, ...changes } : shortcut));
}

/** 한 칸 앞으로. 맨 앞이면 그대로 */
export function moveShortcutUp(shortcuts: ShortcutDraft[], index: number): ShortcutDraft[] {
  if (index <= 0 || index >= shortcuts.length) return shortcuts;
  const moved = [...shortcuts];
  [moved[index - 1], moved[index]] = [moved[index] as ShortcutDraft, moved[index - 1] as ShortcutDraft];
  return moved;
}

/** 보낼 목록. 힌트가 없을 때만 부른다. 앞뒤 빈칸을 다듬는다(서버도 다듬는다) */
export function toShortcuts(shortcuts: ShortcutDraft[]): Shortcut[] {
  return shortcuts.map((shortcut) => ({ name: shortcut.name.trim(), description: shortcut.description.trim(), body: shortcut.body.trim() }));
}
