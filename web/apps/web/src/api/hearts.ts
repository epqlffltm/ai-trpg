// web/apps/web/src/api/hearts.ts
// 작품의 관심(하트, #989). 시나리오는 게임 서버, 캐릭터와 세계관은 asset 서버가 가진다(#593). 로그인해야 한다.
//   - GET, PUT, DELETE …/{id}/heart: 내가 두었는지와 관심의 수({hearted, heart_count}). 두 번 해도 같다
//     볼 수 없는 작품에 두면 404 다. 거두는 것은 언제나 된다
//   - GET …/hearted: 내 관심 작품. 최근에 둔 것부터, 지금 볼 수 있는 것만이다

import type { components as Trpg } from './generated/trpg';
import { apiRequest } from './http';
import type { PublicWorldPage } from './storyWorlds';
import type { PublicCharacterPage, PublicListingPage } from './types';

export type HeartState = Trpg['schemas']['HeartState'];

/** 관심을 두는 작품의 종류 */
export type HeartKind = 'scenario' | 'character' | 'world';

const BASES: Record<HeartKind, string> = {
  scenario: '/api/v1/game/listings',
  character: '/api/v1/asset/listings/characters',
  world: '/api/v1/asset/listings/worlds',
};

/** 내 관심 작품의 한 묶음에 싣는 수 */
export const HEARTED_LIMIT = 50;

function heartPath(kind: HeartKind, id: string): string {
  return `${BASES[kind]}/${encodeURIComponent(id)}/heart`;
}

function withSignal(signal: AbortSignal | undefined): { signal?: AbortSignal } {
  return signal ? { signal } : {};
}

export function fetchHeart(kind: HeartKind, id: string, signal?: AbortSignal): Promise<HeartState> {
  return apiRequest<HeartState>(heartPath(kind, id), withSignal(signal));
}

/** hearted 가 참이면 두고, 거짓이면 거둔다 */
export function setHeart(kind: HeartKind, id: string, hearted: boolean): Promise<HeartState> {
  return apiRequest<HeartState>(heartPath(kind, id), { method: hearted ? 'PUT' : 'DELETE' });
}

export function fetchHeartedScenarios(signal?: AbortSignal): Promise<PublicListingPage> {
  return apiRequest<PublicListingPage>(`${BASES.scenario}/hearted`, { query: { limit: HEARTED_LIMIT }, ...withSignal(signal) });
}

export function fetchHeartedCharacters(signal?: AbortSignal): Promise<PublicCharacterPage> {
  return apiRequest<PublicCharacterPage>(`${BASES.character}/hearted`, { query: { limit: HEARTED_LIMIT }, ...withSignal(signal) });
}

export function fetchHeartedWorlds(signal?: AbortSignal): Promise<PublicWorldPage> {
  return apiRequest<PublicWorldPage>(`${BASES.world}/hearted`, { query: { limit: HEARTED_LIMIT }, ...withSignal(signal) });
}
