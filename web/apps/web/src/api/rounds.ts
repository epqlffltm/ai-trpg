// web/apps/web/src/api/rounds.ts
// 테이블 방(B6)의 라운드가 부르는 것. 지금 라운드, 최근의 라운드들, 선언 내기, 라운드 닫기(방장).
// 앉아 있는 사람만 부른다. 시작하지 않은 테이블에는 라운드가 없다(409 not_started).
// 선언을 받는 동안에는 남의 선언의 글과 행동이 null 이다(누가 냈는지만 보인다). 마감하면 모두의 것이 보인다.

import { apiRequest } from './http';
import type { DeclarationUpdate, Round, RoundPage } from './types';

/** 한 번에 보일 지난 라운드의 수(지금 라운드를 함께 센다) */
export const ROUND_TAIL = 10;

function roundsPath(tableId: string, rest = ''): string {
  return `/api/v1/game/tables/${encodeURIComponent(tableId)}/rounds${rest}`;
}

/** 가장 최근 라운드. 진행 중이면 지금 선언을 받고 있는 라운드다 */
export function fetchCurrentRound(tableId: string, signal?: AbortSignal): Promise<Round> {
  return apiRequest<Round>(roundsPath(tableId, '/current'), signal ? { signal } : {});
}

/**
 * 최근의 라운드들(ROUND_TAIL 개, 오래된 것부터). 서버는 처음 것부터 주고 모두의 수(total)를 함께 준다.
 * 수를 먼저 묻고(한 개만) 끝부분을 읽는다
 */
export async function fetchRecentRounds(tableId: string, signal?: AbortSignal): Promise<RoundPage> {
  const probe = await fetchRounds(tableId, 0, 1, signal);
  if (probe.total <= 1) return probe;
  return fetchRounds(tableId, Math.max(0, probe.total - ROUND_TAIL), ROUND_TAIL, signal);
}

function fetchRounds(tableId: string, offset: number, limit: number, signal?: AbortSignal): Promise<RoundPage> {
  return apiRequest<RoundPage>(roundsPath(tableId), { query: { offset, limit }, ...(signal ? { signal } : {}) });
}

/** 열려 있는 라운드에 선언을 낸다. 다시 내면 통째로 바뀐다. 모두가 내면 닫기 시작한 라운드(closing)가 온다 */
export function declare(tableId: string, body: DeclarationUpdate): Promise<Round> {
  return apiRequest<Round>(roundsPath(tableId, '/current/declaration'), { method: 'PUT', body });
}

/** 방장이 라운드를 닫는다(202). 서술에 실패해 멈춘 라운드에 다시 부르면 서술을 다시 맡긴다 */
export function closeRound(tableId: string): Promise<Round> {
  return apiRequest<Round>(roundsPath(tableId, '/current/close'), { method: 'POST' });
}
