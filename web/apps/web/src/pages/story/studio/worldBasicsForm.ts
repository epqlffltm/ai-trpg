// web/apps/web/src/pages/story/studio/worldBasicsForm.ts
// 세계관의 기본 탭(이름, 태그, 등급, 공개 범위, 대표 그림)의 입력. 순수한 함수다.
// 상한은 서버와 같다(asset-server/app/worlds/models.py 의 이름과 태그는 캐릭터와 같다). 태그는 쉼표로 나눠 한 칸에 적는다.

import type { StoryWorldDetail, StoryWorldUpdate } from '../../../api/storyWorlds';
import { NAME_MAX, parseTags, TAG_MAX, TAGS_MAX } from '../../chat/studio/characters/basicsForm';

export { NAME_MAX };

export type WorldRating = StoryWorldDetail['rating'];
export type WorldVisibility = StoryWorldDetail['visibility'];

export type WorldBasicsDraft = { name: string; tags: string; rating: WorldRating; visibility: WorldVisibility; imageId: string | null };

export function worldBasicsDraft(world: StoryWorldDetail): WorldBasicsDraft {
  return { name: world.name, tags: world.tags.join(', '), rating: world.rating, visibility: world.visibility, imageId: world.image_id ?? null };
}

/** 이름의 문제. 없으면 undefined */
export function worldNameHint(name: string): string | undefined {
  const trimmed = name.trim();
  if (trimmed === '') return '이름을 적어 주세요.';
  return trimmed.length > NAME_MAX ? `이름은 ${NAME_MAX}자까지입니다.` : undefined;
}

/** 보내기 전에 알릴 것. 칸 이름(서버의 칸 이름) → 글 */
export function worldBasicsHints(draft: WorldBasicsDraft): Record<string, string> {
  const hints: Record<string, string> = {};
  const name = worldNameHint(draft.name);
  if (name) hints.name = name;
  const tags = parseTags(draft.tags);
  if (tags.length > TAGS_MAX) hints.tags = `태그는 ${TAGS_MAX}개까지입니다.`;
  else if (tags.some((tag) => tag.length > TAG_MAX)) hints.tags = `태그 하나는 ${TAG_MAX}자까지입니다.`;
  return hints;
}

/** 기본 탭의 칸만 보낸다. 힌트가 없을 때만 부른다 */
export function toWorldBasicsBody(draft: WorldBasicsDraft): StoryWorldUpdate {
  return { name: draft.name.trim(), tags: parseTags(draft.tags), rating: draft.rating, visibility: draft.visibility, image_id: draft.imageId };
}
