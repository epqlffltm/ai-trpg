// web/apps/web/src/test/chatFixtures.ts
// chat 의 대화(C3) 시험이 함께 쓰는 것. 대화 하나(루나, 카페, 말 셋), SSE 의 글, 로그인한 사람의 가짜 서버.

import { REFRESH_PATH } from '../api/refresh';
import type { ConversationDetail, ConversationMessage, SavedChatMessage } from '../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from './fakeFetch';
import { ME } from './tableFixtures';

export const ID = '00000000-0000-4000-8000-00000000d301';
export const CHARACTER = '00000000-0000-4000-8000-00000000c301';
export const GEN = '00000000-0000-4000-8000-00000000e301';
export const PATH = `/api/v1/chat/conversations/${ID}`;
export const M = (n: number) => `00000000-0000-4000-8000-0000000f30${n}`;
export const AT = '2026-10-25T03:00:00Z';

export function message(n: number, role: string, content: string, extra: Partial<ConversationMessage> = {}): ConversationMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content, status: 'complete', created_at: AT, alternatives: [M(n)], changes: [], suggestions: [], edited: false, event_scene: null, expression: null, ...extra };
}

export const MESSAGES = [
  message(1, 'assistant', '어서 와요.'),
  message(2, 'user', '안녕'),
  message(3, 'assistant', '비가 오네요.', { alternatives: [M(3), M(9)], suggestions: ['우산 있어?', '차 한잔 줘'], changes: [{ kind: 'affection', rising: true, delta: null }] }),
];

export function detail(extra: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id: ID,
    title: '비 오는 오후',
    start: { title: '비 오는 오후', situation: '비를 피해 카페에 들어온다.', hour: 15 },
    character: { id: CHARACTER, version: 2, rating: 'all', document: { name: '루나', places: [{ id: 'cafe', name: '카페', description: '', image_id: null }], items: [], event_scenes: [] } },
    persona: null,
    model: { slug: 'glm', display_name: 'GLM', vendor: 'zai', grade: 'standard', retires_on: null, usable: true },
    messages: MESSAGES,
    state: { place: 'cafe', minutes: 30, clock: { day: 1, hour: 15, minute: 30, time_of_day: 'day' }, background: null, sprite: null, inventory: [], visited: [], outfit: [], affection: { display: 'stage', value: null, stage: '친구', stage_index: 1, stages: 4 } },
    generating: false,
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as ConversationDetail;
}

export function sse(...frames: [string, unknown][]): string {
  return frames.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
}

export function saved(n: number, role: string, content: string): SavedChatMessage {
  return { id: M(n), parent_id: M(n - 1), role, content, status: 'complete', created_at: AT, changes: [], suggestions: [], edited: false, event_scene: null, expression: null };
}

export function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}, conversation: () => ConversationDetail = () => detail()) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/chat/conversations': () => json(200, { items: [], total: 0 }),
    [`GET ${PATH}`]: () => json(200, conversation()),
    ...routes,
  });
}

export function posts(seen: SeenRequest[], url: string): SeenRequest[] {
  return seen.filter((request) => request.method !== 'GET' && request.url === url);
}
