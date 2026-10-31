// web/apps/web/src/pages/story/storyWorldView.ts
// 공개 세계관(D1)에 보일 글. 순수한 함수다.

import type { PublicCastMember, PublicWorldSummary } from '../../api/storyWorlds';
import { genreBadge } from '../../genres/genres';
import { ratingBadge } from '../home/labels';

/** 칸의 표시들. 성인, 장르, 기한("30일"), 태그. 같은 것은 한 번 */
export function worldTags(world: Pick<PublicWorldSummary, 'rating' | 'genre' | 'deadline_days' | 'tags'>): string[] {
  const tags = [ratingBadge(world.rating), genreBadge(world.genre), world.deadline_days ? `${world.deadline_days}일` : null, ...world.tags];
  return [...new Set(tags.filter((tag): tag is string => Boolean(tag)))];
}

/** 인물의 이름. 실루엣이면 서버가 이름을 주지 않는다 */
export function castLabel(member: Pick<PublicCastMember, 'name' | 'reveal'>): string {
  return member.reveal === 'silhouette' || !member.name ? '???' : member.name;
}

/** "엔딩 2/5". 기록에 남는 엔딩이 없으면 null. 본 수는 로그인했을 때만 안다 */
export function endingLine(total: number, seen: number | null): string | null {
  if (total <= 0) return null;
  return seen === null ? `엔딩 ${total}개` : `엔딩 ${Math.min(seen, total)}/${total}`;
}
