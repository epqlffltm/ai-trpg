// web/apps/web/src/pages/chat/studio/lorebooks/lorebookForm.ts
// 로어북의 이름과 설명의 입력. 순수한 함수다. 상한은 서버와 같다(asset-server/app/lorebooks/models.py).
// 설명은 만든 사람만 보는 메모다(모델에는 가지 않는다).

import type { AssetLorebookDetail, AssetLorebookUpdate } from '../../../../api/types';

export const LOREBOOK_NAME_MAX = 50;
export const LOREBOOK_DESCRIPTION_MAX = 1000;

export type InfoDraft = { name: string; description: string };

export function infoDraft(lorebook: AssetLorebookDetail): InfoDraft {
  return { name: lorebook.name, description: lorebook.description };
}

/** 이름의 문제. 빈칸을 빼고 1~50자. 없으면 undefined */
export function nameHint(name: string): string | undefined {
  const trimmed = name.trim();
  if (trimmed === '') return '이름을 적어 주세요.';
  if (trimmed.length > LOREBOOK_NAME_MAX) return `이름은 ${LOREBOOK_NAME_MAX}자까지입니다.`;
  return undefined;
}

/** 보내기 전에 알릴 것. 칸 이름 → 글 */
export function infoHints(draft: InfoDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = nameHint(draft.name);
  if (name) hints.name = name;
  if (draft.description.length > LOREBOOK_DESCRIPTION_MAX) hints.description = `설명은 ${LOREBOOK_DESCRIPTION_MAX}자까지입니다.`;
  return hints;
}

export function toInfoBody(draft: InfoDraft): AssetLorebookUpdate {
  return { name: draft.name.trim(), description: draft.description };
}
