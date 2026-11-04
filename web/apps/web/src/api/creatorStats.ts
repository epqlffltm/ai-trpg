// web/apps/web/src/api/creatorStats.ts
// 제작자 숫자(#991). 내 작품마다 시작한 수(모든 기간, 최근 7일)다. 로그인한 사람의 것만 온다.
// 시나리오는 게임 서버(연 테이블을 바로 센다), 캐릭터와 세계관은 asset 서버(한 시간마다 받아 온 수)를 서버마다 따로 부른다(#593).
// 최근의 수가 많은 것부터 100개까지이고, total 과 recent 는 내 작품 모두를 더한 것이다.

import type { components as Asset } from './generated/asset';
import type { components as Trpg } from './generated/trpg';
import { apiRequest } from './http';

export type ScenarioStats = Trpg['schemas']['ScenarioStats'];
export type WorkStats = Asset['schemas']['WorkStats'];
/** 두 서버의 모양이 같다. asset 의 것에만 받아 온 시각(refreshed_at)이 있다 */
export type CreatorStats = ScenarioStats | WorkStats;

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export function fetchScenarioStats(signal?: AbortSignal): Promise<ScenarioStats> {
  return apiRequest<ScenarioStats>('/api/v1/game/me/stats/scenarios', withSignal(signal));
}

export function fetchCharacterStats(signal?: AbortSignal): Promise<WorkStats> {
  return apiRequest<WorkStats>('/api/v1/asset/me/stats/characters', withSignal(signal));
}

export function fetchWorldStats(signal?: AbortSignal): Promise<WorkStats> {
  return apiRequest<WorkStats>('/api/v1/asset/me/stats/worlds', withSignal(signal));
}
