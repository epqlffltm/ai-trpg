// web/apps/web/src/api/rankings.ts
// 이번 주 인기(#985). 시나리오는 게임 서버, 캐릭터와 세계관은 asset 서버의 랭킹을 서버마다 따로 부른다(#593).
// 최근 7일에 시작한 수(테이블, 대화, 세션)가 많은 것부터다. 캐릭터와 세계관의 수는 asset 서버가 한 시간마다 받아 온다.
// 로그인하지 않아도 부른다(전체이용가만 온다). 공개 목록처럼 보는 사람의 설정을 싣는다(listingPreferences.ts).

import type { components as Asset } from './generated/asset';
import type { components as Trpg } from './generated/trpg';
import { apiRequest } from './http';
import { listingPreferences } from './listingPreferences';

export type ScenarioRanking = Trpg['schemas']['ScenarioRanking'];
export type CharacterRanking = Asset['schemas']['CharacterRanking'];
export type WorldRanking = Asset['schemas']['WorldRanking'];

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export function fetchScenarioRanking(limit: number, signal?: AbortSignal): Promise<ScenarioRanking> {
  return apiRequest<ScenarioRanking>('/api/v1/game/rankings/scenarios', { query: { limit, ...listingPreferences() }, ...withSignal(signal) });
}

export function fetchCharacterRanking(limit: number, signal?: AbortSignal): Promise<CharacterRanking> {
  return apiRequest<CharacterRanking>('/api/v1/asset/rankings/characters', { query: { limit, ...listingPreferences() }, ...withSignal(signal) });
}

export function fetchWorldRanking(limit: number, signal?: AbortSignal): Promise<WorldRanking> {
  return apiRequest<WorldRanking>('/api/v1/asset/rankings/worlds', { query: { limit, ...listingPreferences() }, ...withSignal(signal) });
}
