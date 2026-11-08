// web/apps/web/src/pages/trpg/room/stage/tableStageView.ts
// 테이블 방의 그림 창(#1163)에 무엇을 띄울지 고른다. 순수한 함수다. 상태는 바꾸지 않고, 서버가 준 것만 읽는다.
//   - 장소: 앉은 사람의 캐릭터가 가장 많이 선 장소. 같으면 방장의 캐릭터가 선 장소, 그것도 아니면 맵의 차례가 앞인 장소.
//     테이블의 모두가 같은 그림을 본다. 배경은 그 장소의 image_id 다(서버가 아는 장소에만, 지금 때의 그림으로 싣는다)
//   - 인물: 장면의 인물(GET /rounds/current/people) 가운데 그림이 있고 죽지 않았으며, 그 장소에 있거나 자리가 없는 인물
//   - 컷신: 마지막 닫힘의 묶음부터 그 뒤의 이벤트 가운데 마지막으로 일어난 사건(happening_occurred)이나 이룬 퀘스트
//     (quest_changed 의 succeeded)의 그림. 사건과 퀘스트는 라운드를 닫을 때 그 닫힘의 묶음에 적히고 결과는 다음 라운드의
//     서술에 나오므로, 다음 라운드가 닫힐 때까지 보인다. 되돌린 라운드의 일은 뺀다(revertedEvents.ts)

import type { SceneCast, TableDetail, TableEvent, TableMap } from '../../../../api/types';
import { withoutReverted } from '../events/revertedEvents';

export type StagePlace = { id: string; name: string; imageId: string | null };
export type StagePerson = { id: string; name: string; imageId: string };
export type StageCutscene = { title: string; imageId: string };

/** 그림 창의 장소. 맵이 없거나 아무도 맵에 서 있지 않으면 null */
export function stagePlace(map: TableMap | null, members: TableDetail['members']): StagePlace | null {
  if (!map) return null;
  const counts = new Map<string, number>();
  for (const member of members) {
    const placeId = member.sheet?.place_id;
    if (placeId) counts.set(placeId, (counts.get(placeId) ?? 0) + 1);
  }
  const most = Math.max(0, ...counts.values());
  if (most === 0) return null;
  const tied = map.places.filter((place) => counts.get(place.entry_id) === most);
  const hostPlace = members.find((member) => member.is_host)?.sheet?.place_id;
  const chosen = tied.find((place) => place.entry_id === hostPlace) ?? tied[0];
  return chosen ? { id: chosen.entry_id, name: chosen.name, imageId: chosen.image_id ?? null } : null;
}

/** 그림 창에 세울 인물. 서버의 차례를 지킨다 */
export function stagePeople(cast: SceneCast | undefined, placeId: string | null): StagePerson[] {
  if (!cast) return [];
  return cast.people.flatMap((person) => {
    const here = person.place_id === null || person.place_id === placeId;
    if (!person.image_id || person.status === 'dead' || !here) return [];
    return [{ id: person.id, name: person.name, imageId: person.image_id }];
  });
}

/** 이번에 띄울 컷신. 없으면 null */
export function stageCutscene(events: TableEvent[]): StageCutscene | null {
  const shown = withoutReverted(events);
  const window = shown.slice(lastClosingStart(shown));
  for (let index = window.length - 1; index >= 0; index -= 1) {
    const cutscene = cutsceneOf(window[index]);
    if (cutscene) return cutscene;
  }
  return null;
}

/** 마지막 닫힘(round_closed)의 묶음이 시작하는 자리. 닫힘이 없으면 처음 */
function lastClosingStart(events: TableEvent[]): number {
  const closed = [...events].reverse().find((event) => event.type === 'round_closed');
  if (!closed) return 0;
  return events.findIndex((event) => event.action_group_id === closed.action_group_id);
}

/** 컷신이 있는 이벤트(일어난 사건, 이룬 퀘스트)의 그림과 이름 */
function cutsceneOf(event: TableEvent | undefined): StageCutscene | null {
  if (!event) return null;
  const payload = event.payload ?? {};
  const happened = event.type === 'happening_occurred' || (event.type === 'quest_changed' && payload.status === 'succeeded');
  if (!happened || typeof payload.image_id !== 'string') return null;
  return { title: typeof payload.name === 'string' ? payload.name : '', imageId: payload.image_id };
}
