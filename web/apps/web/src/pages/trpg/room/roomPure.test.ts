// web/apps/web/src/pages/trpg/room/roomPure.test.ts
// 스트림이 끝난 뒤의 일, 받은 메시지의 갈래, 채팅과 일어난 일 합치기, 입력 중 지우기, 실패의 글을 순수한 함수로 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../api/errors';
import { streamLabel } from './RoomHeader';
import { describeChatProblem, describeStartProblem } from './roomProblem';
import type { TableEvent } from '../../../api/types';
import { event } from '../../../test/tableFixtures';
import { mergeEvents, mergeMessages, nextStep, routeMessage } from './streamPolicy';
import { withoutExpired } from './useTypingPeople';

function chat(sequence: number) {
  return { sequence, user_id: 'u', character_name: null, content: `글 ${sequence}`, created_at: '2026-10-22T00:00:00Z' };
}

describe('nextStep', () => {
  it('끝났거나 앉아 있지 않으면 멈춘다', () => {
    expect(nextStep({ kind: 'closed', reason: 'table_ended' }, 1, 0)).toEqual({ action: 'stop', reason: 'table_ended' });
    expect(nextStep({ kind: 'closed', reason: 'not_seated' }, 1, 0)).toEqual({ action: 'stop', reason: 'not_seated' });
    expect(nextStep({ kind: 'http-error', status: 404 }, 1, 0)).toEqual({ action: 'stop', reason: 'not_seated' });
  });

  it('토큰이 만료됐으면 갱신하고 다시 붙는다', () => {
    expect(nextStep({ kind: 'closed', reason: 'token_expired' }, 1, 0)).toEqual({ action: 'refresh-token' });
    expect(nextStep({ kind: 'unauthorized' }, 1, 0)).toEqual({ action: 'refresh-token' });
  });

  it('서버가 꺼지거나 끊기면 1~5초 사이에서 무작위로 쉬었다가 다시 붙는다', () => {
    expect(nextStep({ kind: 'closed', reason: 'server_shutdown' }, 1, 0)).toEqual({ action: 'reconnect', delayMs: 1000 });
    expect(nextStep({ kind: 'disconnected' }, 3, 0.999)).toEqual({ action: 'reconnect', delayMs: 4996 });
  });

  it('열리지 못하고 이어서 실패하면 쉬는 시간을 늘린다(30초까지)', () => {
    expect(nextStep({ kind: 'http-error', status: 503 }, 1, 0)).toEqual({ action: 'reconnect', delayMs: 1000 });
    expect(nextStep({ kind: 'http-error', status: 503 }, 3, 0)).toEqual({ action: 'reconnect', delayMs: 4000 });
    expect(nextStep({ kind: 'http-error', status: 503 }, 10, 0.5)).toEqual({ action: 'reconnect', delayMs: 30_000 });
  });
});

describe('routeMessage', () => {
  it('종류마다 나누고, 모르는 것과 읽지 못하는 것은 건너뛴다', () => {
    expect(routeMessage({ event: 'typing', data: '{"user_id": "u1"}' })).toEqual({ kind: 'typing', userId: 'u1' });
    expect(routeMessage({ id: '1-1-0', event: 'chat_message', data: JSON.stringify(chat(1)) })).toMatchObject({ kind: 'chat' });
    expect(routeMessage({ id: '2-1-0', event: 'table_event', data: '{"sequence": 2}' })).toMatchObject({ kind: 'event' });
    expect(routeMessage({ event: 'narration_preview', data: '{"round": 1}' })).toEqual({ kind: 'ignore' });
    expect(routeMessage({ event: 'chat_message', data: '깨진 글' })).toEqual({ kind: 'ignore' });
  });
});

describe('mergeMessages', () => {
  it('번호 차례로 합치고 같은 번호는 한 번만 둔다', () => {
    expect(mergeMessages([chat(1), chat(3)], [chat(2), chat(3)]).map((message) => message.sequence)).toEqual([1, 2, 3]);
  });
});

describe('mergeEvents', () => {
  it('일어난 일도 번호 차례로 합치고 같은 번호는 한 번만 둔다(다시 붙을 때 겹친다)', () => {
    const one = (sequence: number) => event(sequence, 'table_started') as unknown as TableEvent;
    expect(mergeEvents([one(1), one(3)], [one(3), one(2)]).map((item) => item.sequence)).toEqual([1, 2, 3]);
  });
});

describe('withoutExpired', () => {
  it('보일 때가 지난 사람을 지운다', () => {
    const map = new Map([
      ['a', 1000],
      ['b', 3000],
    ]);
    expect([...withoutExpired(map, 2000).keys()]).toEqual(['b']);
  });
});

describe('streamLabel', () => {
  it('열려 있거나 끝난 판이면 아무것도 보이지 않는다', () => {
    expect(streamLabel({ state: 'open' })).toBeNull();
    expect(streamLabel({ state: 'stopped', reason: 'table_ended' })).toBeNull();
    expect(streamLabel({ state: 'reconnecting', inMs: 2500 })).toMatch(/3초 뒤/);
  });
});

describe('roomProblem', () => {
  it('시작의 409 는 까닭마다 알리고, 채팅이 너무 빠르면 기다리게 한다', () => {
    const missing = new ApiError({ status: 409, detail: 'x', code: 'characters_missing' });
    expect(describeStartProblem(missing).message).toMatch(/캐릭터를 정하지 않은 사람/);
    expect(describeChatProblem(new ApiError({ status: 429, detail: 'x', retryAfter: 7 }))).toMatchObject({ waitSeconds: 7 });
    expect(describeChatProblem(new ApiError({ status: 409, detail: 'x' })).message).toMatch(/끝난 테이블/);
  });
});
