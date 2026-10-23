// web/apps/web/src/pages/chat/studio/characters/basicsForm.ts
// 캐릭터의 기본 탭(이름, 나이, 성별, 태그, 등급, 공개 범위)의 입력. 순수한 함수다.
// 상한은 서버와 같다(asset-server/app/characters/models.py). 태그는 쉼표로 나눠 한 칸에 적는다.

import type { AssetCharacterDetail, AssetCharacterUpdate, AssetRating, AssetVisibility } from '../../../../api/types';

export const NAME_MAX = 50;
export const AGE_MAX = 20;
export const GENDER_MAX = 20;
export const TAGS_MAX = 10;
export const TAG_MAX = 20;

export type BasicsDraft = {
  name: string;
  age: string;
  gender: string;
  tags: string;
  rating: AssetRating;
  visibility: AssetVisibility;
};

export function basicsDraft(character: AssetCharacterDetail): BasicsDraft {
  return {
    name: character.name,
    age: character.age,
    gender: character.gender,
    tags: character.tags.join(', '),
    rating: character.rating,
    visibility: character.visibility,
  };
}

/** 쉼표로 나눈 태그. 앞뒤 빈칸을 떼고, 빈 것과 겹친 것은 뺀다 */
export function parseTags(text: string): string[] {
  const tags = text.split(',').map((tag) => tag.trim()).filter((tag) => tag !== '');
  return [...new Set(tags)];
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글 */
export function basicsHints(draft: BasicsDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = draft.name.trim();
  if (name === '') hints.name = '이름을 적어 주세요.';
  else if (name.length > NAME_MAX) hints.name = `이름은 ${NAME_MAX}자까지입니다.`;
  if (draft.age.trim().length > AGE_MAX) hints.age = `나이는 ${AGE_MAX}자까지입니다.`;
  if (draft.gender.trim().length > GENDER_MAX) hints.gender = `성별은 ${GENDER_MAX}자까지입니다.`;
  const tags = parseTags(draft.tags);
  if (tags.length > TAGS_MAX) hints.tags = `태그는 ${TAGS_MAX}개까지입니다.`;
  else if (tags.some((tag) => tag.length > TAG_MAX)) hints.tags = `태그 하나는 ${TAG_MAX}자까지입니다.`;
  return hints;
}

/** 기본 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toBasicsBody(draft: BasicsDraft): AssetCharacterUpdate {
  return {
    name: draft.name.trim(),
    age: draft.age.trim(),
    gender: draft.gender.trim(),
    tags: parseTags(draft.tags),
    rating: draft.rating,
    visibility: draft.visibility,
  };
}
