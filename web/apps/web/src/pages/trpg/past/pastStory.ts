// web/apps/web/src/pages/trpg/past/pastStory.ts
// 떠난 테이블의 이벤트를 읽을 이야기로 묶는다. 순수한 함수다.
// 이벤트에는 서술(gm_narration)이 먼저, 그 서술로 여는 라운드(round_opened)가 뒤에 적힌다. 그래서 둘이 이어지면
// 라운드의 머리 아래에 그 장면을 둔다. 선언(player_action)은 캐릭터의 이름과 글, 판정의 굴림(check_rolled)은 한 줄,
// 그 밖의 일은 일어난 일의 한 줄(eventLines.ts).

import type { TableEvent } from '../../../api/types';
import { ACTION_LABELS } from '../room/round/action/actionLabels';
import type { ActionKind } from '../room/round/action/actionOptions';
import { eventLine, type EventContext } from '../room/events/eventLines';

export type StoryBlock =
  | { kind: 'round'; key: number; number: number | null; scene: string | null }
  | { kind: 'narration'; key: number; text: string }
  | { kind: 'action'; key: number; name: string; content: string; action: string | null }
  | { kind: 'line'; key: number; text: string; important: boolean };

type Payload = Record<string, unknown>;

function text(payload: Payload, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value !== '' ? value : null;
}

function actionName(payload: Payload): string | null {
  const action = payload.action;
  if (action === null || typeof action !== 'object') return null;
  const kind = (action as Payload).kind;
  return typeof kind === 'string' ? (ACTION_LABELS[kind as ActionKind] ?? null) : null;
}

function num(payload: Payload, key: string): number | null {
  const value = payload[key];
  return typeof value === 'number' ? value : null;
}

/** 판정의 굴림. 라운드 화면이 선언 옆에 보이는 것을 여기서는 한 줄로 쓴다("렌: 눈 13, 보정 +2, 합 15 / 목표 15 · 성공") */
export function checkLine(payload: Payload): string {
  const modifier = num(payload, 'modifier') ?? 0;
  const sign = modifier >= 0 ? `+${modifier}` : String(modifier);
  const result = payload.success === true ? '성공' : '실패';
  return `${text(payload, 'character_name') ?? '누군가'}: 눈 ${num(payload, 'roll') ?? '?'}, 보정 ${sign}, 합 ${num(payload, 'total') ?? '?'} / 목표 ${num(payload, 'target') ?? '?'} · ${result}`;
}

function roundNumber(event: TableEvent): number | null {
  const value = (event.payload ?? {}).number;
  return typeof value === 'number' ? value : null;
}

function actionBlock(event: TableEvent): StoryBlock {
  const payload: Payload = event.payload ?? {};
  return { kind: 'action', key: event.sequence, name: text(payload, 'character_name') ?? '누군가', content: text(payload, 'content') ?? '', action: actionName(payload) };
}

export function pastStory(events: TableEvent[], ctx: EventContext): StoryBlock[] {
  const blocks: StoryBlock[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index] as TableEvent;
    const next = events[index + 1];
    if (event.type === 'gm_narration' && next?.type === 'round_opened') {
      blocks.push({ kind: 'round', key: next.sequence, number: roundNumber(next), scene: text(event.payload ?? {}, 'text') });
      index += 1;
    } else if (event.type === 'gm_narration') {
      blocks.push({ kind: 'narration', key: event.sequence, text: text(event.payload ?? {}, 'text') ?? '' });
    } else if (event.type === 'round_opened') {
      blocks.push({ kind: 'round', key: event.sequence, number: roundNumber(event), scene: null });
    } else if (event.type === 'player_action') {
      blocks.push(actionBlock(event));
    } else if (event.type === 'check_rolled') {
      blocks.push({ kind: 'line', key: event.sequence, text: checkLine(event.payload ?? {}), important: false });
    } else {
      const line = eventLine(event, ctx);
      if (line) blocks.push({ kind: 'line', key: event.sequence, text: line.text, important: line.important });
    }
  }
  return blocks;
}

const DEPARTURES = { left: '스스로 나감', kicked: '방장이 내보냄', dropped: '크레딧이 모자라 빠짐' } as const;

/** 떠난 길의 말 */
export function departureLabel(kind: keyof typeof DEPARTURES): string {
  return DEPARTURES[kind];
}
