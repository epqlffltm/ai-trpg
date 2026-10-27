// web/apps/web/src/pages/gallery/storyGalleryView.ts
// 갤러리(C7)의 story 탭의 칸을 짓는다. 순수한 함수다.
// 세계관은 내 세션에서 모은다(최근에 한 세션의 세계관이 먼저). 연 일러스트는 인물마다 묶고, 인물이 없는 장면은 세계관 칸에 둔다.
// 인물의 이름은 세계관의 공개 판에서 찾는다(숨김·실루엣이거나 판을 읽지 못하면 "???").

import type { StoryIllustration, StorySessionSummary } from '../../api/story';
import type { PublicCastMember } from '../../api/storyWorlds';

export type StoryWorldEntry = { id: string; name: string };

/** 내 세션들의 세계관(겹치지 않게, 세션의 차례대로) */
export function sessionWorlds(sessions: Pick<StorySessionSummary, 'world'>[]): StoryWorldEntry[] {
  const seen = new Map<string, StoryWorldEntry>();
  for (const session of sessions) {
    if (!seen.has(session.world.id)) seen.set(session.world.id, { id: session.world.id, name: session.world.name });
  }
  return [...seen.values()];
}

export type IllustrationCell = { key: string; title: string; imageId: string; firstSeenAt: string };
export type IllustrationGroup = { key: string; title: string; cells: IllustrationCell[] };

const KIND_LABEL: Record<StoryIllustration['kind'], string> = { event: '이벤트', ending: '엔딩' };

export const WORLD_GROUP = '세계관';

/** 인물의 이름. 모르거나 이름을 보이지 않는 인물은 "???" */
export function castLabel(cast: Pick<PublicCastMember, 'id' | 'name'>[] | undefined, castId: string): string {
  return cast?.find((member) => member.id === castId)?.name || '???';
}

/** 인물마다 묶는다(인물이 처음 나온 차례). 여러 인물이 부른 장면은 그 인물들의 칸에 다 있다. 인물이 없으면 세계관 칸 */
export function groupIllustrations(items: StoryIllustration[], cast: Pick<PublicCastMember, 'id' | 'name'>[] | undefined): IllustrationGroup[] {
  const groups = new Map<string, IllustrationGroup>();
  for (const item of items) {
    const cell: IllustrationCell = { key: `${item.kind}:${item.scene_id}`, title: KIND_LABEL[item.kind], imageId: item.image_id, firstSeenAt: item.first_seen_at };
    const owners = item.cast.length > 0 ? item.cast : [null];
    for (const owner of owners) {
      const key = owner ?? '';
      const group = groups.get(key) ?? { key, title: owner === null ? WORLD_GROUP : castLabel(cast, owner), cells: [] };
      group.cells.push(cell);
      groups.set(key, group);
    }
  }
  return [...groups.values()];
}
