// web/apps/web/src/pages/story/storyRecords.ts
// 기록 창(D6)에 보일 것. 세계관 칸(view)의 엔딩·이벤트와 계정에 남은 엔딩(GET /story/endings)을 잇는 순수한 함수다.
// 본 엔딩(view 의 seen: 계정에 남은 것과 이 가지에서 본 것)만 이름과 일러스트가 온다. 못 본 엔딩은 "???" 와 힌트다.
// 처음 본 때는 계정에 남은 엔딩에만 있다(남지 않는 엔딩은 없다).

import type { StoryEndingRecords, StoryView } from '../../api/story';
import { countedEndings } from './storyWorld';

export type EndingRow = { id: string; name: string; seen: boolean; hint: string; imageId: string | null; firstSeenAt: string | null; counted: boolean };

/** 엔딩의 줄들(판에 적힌 차례) */
export function endingRows(view: Pick<StoryView, 'endings'>, records: StoryEndingRecords | undefined): EndingRow[] {
  const first = new Map((records?.items ?? []).map((record) => [record.ending_id, record.first_seen_at]));
  return view.endings.map((ending) => ({
    id: ending.id,
    name: ending.seen ? ending.name || ending.id : '???',
    seen: ending.seen,
    hint: ending.hint,
    imageId: ending.seen ? ending.image_id : null,
    firstSeenAt: first.get(ending.id) ?? null,
    counted: ending.unlock,
  }));
}

/** "엔딩 3/7"(기록에 남는 엔딩 가운데 계정에 남은 수). 남는 엔딩이 없으면 null */
export function endingCount(view: Pick<StoryView, 'endings'>, records: StoryEndingRecords | undefined): string | null {
  const total = countedEndings(view);
  if (total === 0 || !records) return null;
  const counted = new Set(view.endings.filter((ending) => ending.unlock).map((ending) => ending.id));
  const seen = records.items.filter((record) => counted.has(record.ending_id)).length;
  return `엔딩 ${seen}/${total}`;
}

export type EventRow = { id: string; name: string; imageId: string | null };

/** 이 가지에서 열린 이벤트들(서버가 보낸 차례) */
export function eventRows(view: Pick<StoryView, 'events'>): EventRow[] {
  return view.events.map((event) => ({ id: event.id, name: event.name, imageId: event.image_id }));
}
