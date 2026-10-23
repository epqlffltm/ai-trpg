// web/apps/web/src/pages/trpg/studio/collection/collectionForm.ts
// 묶음 재료(로어북, 몬스터 모음) 자신의 입력. 제목과 소개뿐이다. 순수한 함수다.
// 담긴 것(항목, 몬스터)은 묶음을 만든 뒤 그 화면에서 하나씩 더한다.

import type { AssetSummary } from '../../../../api/types';
import { DESCRIPTION_MAX, TITLE_MAX } from '../rulebooks/rulebookForm';

export type CollectionDraft = { title: string; description: string };

export function newCollectionDraft(): CollectionDraft {
  return { title: '', description: '' };
}

export function collectionDraft(asset: AssetSummary): CollectionDraft {
  return { title: asset.title, description: asset.description };
}

/** 보내기 전에 알릴 것. 칸 이름 → 글 */
export function collectionHints(draft: CollectionDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const title = draft.title.trim();
  if (title === '') hints.title = '제목을 적어 주세요.';
  else if (title.length > TITLE_MAX) hints.title = `제목은 ${TITLE_MAX}자까지입니다.`;
  if (draft.description.length > DESCRIPTION_MAX) hints.description = `소개는 ${DESCRIPTION_MAX}자까지입니다.`;
  return hints;
}

/** 만들 때와 고칠 때 같은 본문이다. 고칠 때도 두 칸을 모두 보낸다 */
export function toCollectionBody(draft: CollectionDraft): { title: string; description: string } {
  return { title: draft.title.trim(), description: draft.description };
}

/** 쉼표로 나눈 낱말들. 앞뒤 공백을 떼고 빈 것은 버린다(키워드, 지목할 이름) */
export function splitWords(text: string): string[] {
  return text
    .split(',')
    .map((word) => word.trim())
    .filter((word) => word !== '');
}

/** 낱말 목록의 문제. 개수, 길이, 대소문자만 다른 것까지 겹침(서버의 reject_duplicates). 없으면 null */
export function wordsHint(words: string[], max: number, maxLength: number, what: string): string | null {
  if (words.length > max) return `${what}는 ${max}개까지입니다.`;
  if (words.some((word) => word.length > maxLength)) return `${what} 하나는 ${maxLength}자까지입니다.`;
  const folded = words.map((word) => word.toLowerCase());
  return new Set(folded).size === folded.length ? null : `같은 ${what}가 두 번 있습니다.`;
}
