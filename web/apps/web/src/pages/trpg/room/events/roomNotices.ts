// web/apps/web/src/pages/trpg/room/events/roomNotices.ts
// 방 위의 알림. 일어난 일 가운데 지금 서술을 막는 것만 고른다. 순수한 함수다.
//
// - 이번 라운드의 일: 크레딧이 모자람, 모델을 팔지 않음, 서술 실패와 그만둠, 자리에서 빠짐.
//   라운드가 넘어가면(서술이 끝나 다음 라운드가 열리면) 저절로 사라진다. 같은 사람의 같은 알림은 마지막 것 하나만
// - 모델의 일: 쓸 수 없음, 곧 끝남. 마지막 것 하나만. 그 뒤에 모델이 바뀌었으면(방장이 고름, 서버가 바꿈) 보이지 않는다
// 알림은 이벤트로만 정한다. 다시 읽은 테이블이나 라운드의 값과 섞지 않는다.

import type { TableEvent } from '../../../../api/types';
import { eventLine, eventRound, type EventContext, type EventType } from './eventLines';

export type RoomNotice = { key: string; text: string; tone: 'info' | 'error' };

/** 이번 라운드에만 뜻이 있는 일. error 는 지금 서술을 막는다 */
const ROUND_NOTICES: ReadonlyMap<EventType, RoomNotice['tone']> = new Map<EventType, RoomNotice['tone']>([
  ['narration_credits_short', 'error'],
  ['narration_model_not_for_sale', 'error'],
  ['narration_failed', 'error'],
  ['narration_abandoned', 'info'],
  ['member_dropped', 'info'],
]);

const MODEL_NOTICES: ReadonlyMap<EventType, RoomNotice['tone']> = new Map<EventType, RoomNotice['tone']>([
  ['narration_model_unavailable', 'error'],
  ['narration_model_retiring', 'info'],
]);

/** 이것이 오면 그 앞의 모델 알림은 지난 일이다 */
const MODEL_SETTLED: ReadonlySet<EventType> = new Set<EventType>(['narration_model_changed', 'narration_model_replaced']);

function noticeKey(event: TableEvent): string {
  const userId = event.payload?.user_id;
  return `${event.type}:${typeof userId === 'string' ? userId : ''}`;
}

/** 이번 라운드의 알림이 될 이벤트. 같은 종류와 같은 사람이면 나중 것 */
export function roundNoticeEvents(events: TableEvent[], currentRound: number | null): TableEvent[] {
  if (currentRound === null) return [];
  const latest = new Map<string, TableEvent>();
  for (const event of events) {
    if (ROUND_NOTICES.has(event.type) && eventRound(event) === currentRound) latest.set(noticeKey(event), event);
  }
  return [...latest.values()];
}

/** 모델의 알림이 될 이벤트. 마지막 모델 알림이 그 뒤의 모델 바꿈보다 나중일 때만 */
export function modelNoticeEvent(events: TableEvent[]): TableEvent | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index] as TableEvent;
    if (MODEL_SETTLED.has(event.type)) return null;
    if (MODEL_NOTICES.has(event.type)) return event;
  }
  return null;
}

function toNotice(event: TableEvent, ctx: EventContext): RoomNotice | null {
  const line = eventLine(event, ctx);
  const tone = ROUND_NOTICES.get(event.type) ?? MODEL_NOTICES.get(event.type) ?? 'info';
  return line ? { key: String(event.sequence), text: line.text, tone } : null;
}

/** 방 위에 보일 알림. 모델의 알림이 먼저, 그다음 이번 라운드의 알림을 일어난 차례로. events 는 번호 차례다 */
export function roomNotices(events: TableEvent[], currentRound: number | null, ctx: EventContext): RoomNotice[] {
  const model = modelNoticeEvent(events);
  const chosen = [...(model ? [model] : []), ...roundNoticeEvents(events, currentRound).sort((a, b) => a.sequence - b.sequence)];
  return chosen.map((event) => toNotice(event, ctx)).filter((notice): notice is RoomNotice => notice !== null);
}
