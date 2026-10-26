// web/apps/web/src/pages/story/storyActions.ts
// 장면(D2)에서 할 수 있는 행동의 고를 거리. 판의 문서와 지금의 상태만 받는 순수한 함수다.
// 할 수 있는지는 엔진이 다시 판정한다(422). 화면은 고를 거리를 보일 뿐이다.

import type { StoryMessage, StoryState } from '../../api/story';
import type { StoryWorldDocument } from '../../api/storyWorlds';
import { hasEpilogue, placeName } from './storyWorld';

function asDocument(document: Record<string, unknown>): Partial<StoryWorldDocument> {
  return document as Partial<StoryWorldDocument>;
}

export type Destination = { id: string; name: string; minutes: number };

/** 지금 장소에서 길로 바로 이어진 곳과 걸리는 분. 길은 양쪽으로 다닌다 */
export function destinations(document: Record<string, unknown>, place: string): Destination[] {
  const found: Destination[] = [];
  for (const path of asDocument(document).paths ?? []) {
    const other = path.a === place ? path.b : path.b === place ? path.a : null;
    if (other && other !== place && !found.some((entry) => entry.id === other)) found.push({ id: other, name: placeName(document, other), minutes: path.minutes });
  }
  return found;
}

export type HeldItem = { id: string; name: string; count: number; description: string };

/** 가진 물건(수가 1 이상). 판에 적은 차례다. 판에 없는 물건은 id 를 이름으로 끝에 둔다 */
export function heldItems(document: Record<string, unknown>, items: Record<string, number>): HeldItem[] {
  const listed = asDocument(document).items ?? [];
  const held = listed
    .filter((item) => (items[item.id] ?? 0) > 0)
    .map((item) => ({ id: item.id, name: item.name || item.id, count: items[item.id] ?? 0, description: item.description ?? '' }));
  const unknown = Object.entries(items)
    .filter(([id, count]) => count > 0 && !listed.some((item) => item.id === id))
    .map(([id, count]) => ({ id, name: id, count, description: '' }));
  return [...held, ...unknown];
}

export type PendingChoices = { eventName: string; choices: { id: string; text: string }[] };

/** 고르기를 기다리는 이벤트의 선택지. 없으면 null */
export function pendingChoices(document: Record<string, unknown>, choosing: string | null): PendingChoices | null {
  if (choosing === null) return null;
  const event = asDocument(document).events?.find((entry) => entry.id === choosing);
  if (!event || event.choices.length === 0) return null;
  return { eventName: event.name || '', choices: event.choices.map((choice) => ({ id: choice.id, text: choice.text })) };
}

/** 이 인물에게 고백을 보일지. 고백이 있는 인물이고, 엔딩 전(후일담에는 고백이 없다)이다 */
export function canConfess(document: Record<string, unknown>, state: StoryState, castId: string): boolean {
  if (state.ending !== null) return false;
  const member = asDocument(document).cast?.find((entry) => entry.id === castId);
  return Boolean(member?.confession);
}

/** 기한의 마지막 날인가. 하루를 마치면 기한의 엔딩이 열린다 */
export function isLastDay(document: Record<string, unknown>, state: StoryState): boolean {
  const deadline = asDocument(document).deadline_days;
  return typeof deadline === 'number' && state.ending === null && state.day >= deadline;
}

/** 시간이 흐르는 행동(시간 보내기, 하루 마치기, 이동)을 보일지. 엔딩 뒤의 후일담에는 기한이 없지만 시간은 흐른다 */
export function canPassTime(document: Record<string, unknown>, state: StoryState): boolean {
  return state.ending === null || hasEpilogue(document);
}

/**
 * 방금 본 엔딩. 끝의 답이 답한 행동 말에 엔딩이 적혀 있으면 그 엔딩이다(엔딩 화면을 띄운다).
 * 다시 생성해도 같은 행동 말이라 다시 뜬다. 닫는 것은 화면이 기억한다
 */
export function freshEnding(messages: StoryMessage[]): { messageId: string; endingId: string } | null {
  const last = messages.at(-1);
  if (last?.role !== 'assistant') return null;
  const parent = messages.find((message) => message.id === last.parent_id);
  return parent?.ending_id ? { messageId: parent.id, endingId: parent.ending_id } : null;
}
