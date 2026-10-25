// web/apps/web/src/api/rounds.ts
// 테이블 방(B6)의 라운드가 부르는 것. 지금 라운드, 최근의 라운드들, 앞의 라운드(B10), 장면의 인물과 몬스터, 선언 내기, 라운드 닫기(방장).
// 앉아 있는 사람만 부른다. 시작하지 않은 테이블에는 라운드가 없다(409 not_started).
// 선언을 받는 동안에는 남의 선언의 글과 행동이 null 이다(누가 냈는지만 보인다). 마감하면 모두의 것이 보인다.

import { apiRequest } from './http';
import type { DeclarationUpdate, Round, RoundPage, SceneCast } from './types';

/** 한 번에 보일 지난 라운드의 수(지금 라운드를 함께 센다) */
export const ROUND_TAIL = 10;

/** "앞의 라운드 더 보기" 한 번에 더 읽는 수 */
export const ROUND_PAGE = 20;

/** 서버가 한 번에 주는 라운드의 최대 수 */
const ROUND_LIMIT_MAX = 100;

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

/**
 * from 번 라운드부터 끝까지(최대 ROUND_LIMIT_MAX 개). 앞의 라운드를 펼친 뒤에 최근의 라운드를 이 번호에 고정해 읽는다.
 * 라운드의 번호는 1 부터 이어진다. 그래서 from 번은 offset from-1 이다
 */
export function fetchRoundsFrom(tableId: string, from: number, signal?: AbortSignal): Promise<RoundPage> {
  return fetchRounds(tableId, Math.max(0, from - 1), ROUND_LIMIT_MAX, signal);
}

/** before 번 바로 앞의 라운드들(ROUND_PAGE 개, 오래된 것부터). 닫힌 라운드라 바뀌지 않는다 */
export function fetchRoundsBefore(tableId: string, before: number, signal?: AbortSignal): Promise<RoundPage> {
  const from = Math.max(1, before - ROUND_PAGE);
  return fetchRounds(tableId, from - 1, Math.max(0, before - from), signal);
}

function fetchRounds(tableId: string, offset: number, limit: number, signal?: AbortSignal): Promise<RoundPage> {
  return apiRequest<RoundPage>(roundsPath(tableId), { query: { offset, limit }, ...(signal ? { signal } : {}) });
}

/**
 * 가장 최근 라운드의 장면에 나온 인물과 몬스터. 행동의 npc, monster 칸에 적을 id 와 지닌 물건이 있다.
 * 장면에 이름이나 호칭이 나온 인물만, 몬스터는 살아 있는 캐릭터가 선 장소들의 마리만 온다
 */
export function fetchSceneCast(tableId: string, signal?: AbortSignal): Promise<SceneCast> {
  return apiRequest<SceneCast>(roundsPath(tableId, '/current/people'), signal ? { signal } : {});
}

/** 열려 있는 라운드에 선언을 낸다. 다시 내면 통째로 바뀐다. 모두가 내면 닫기 시작한 라운드(closing)가 온다 */
export function declare(tableId: string, body: DeclarationUpdate): Promise<Round> {
  return apiRequest<Round>(roundsPath(tableId, '/current/declaration'), { method: 'PUT', body });
}

/** 방장이 라운드를 닫는다(202). 서술에 실패해 멈춘 라운드에 다시 부르면 서술을 다시 맡긴다 */
export function closeRound(tableId: string): Promise<Round> {
  return apiRequest<Round>(roundsPath(tableId, '/current/close'), { method: 'POST' });
}
