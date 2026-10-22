// web/apps/web/src/test/tableFixtures.ts
// 테이블 방의 시험에 쓰는 가짜 값과 가짜 스트림. 서버의 모양(TableDetail, MemberOut)에서 시험이 보는 칸만 채운다.
// 가짜 스트림은 정한 글을 차례로 내보내고, 열어 두라면 화면이 끊을(abort) 때까지 열어 둔다.

import type { SeenRequest } from './fakeFetch';
import { json } from './fakeFetch';

export const ME = '00000000-0000-4000-8000-0000000000e1';
export const OTHER = '00000000-0000-4000-8000-0000000000e2';

export function member(userId: string, extra: Record<string, unknown> = {}) {
  return {
    user_id: userId,
    is_host: false,
    character: null,
    character_mode: null,
    pregen_index: null,
    roll: null,
    abilities: null,
    sheet: null,
    fallen: [],
    joined_at: '2026-10-22T00:00:00Z',
    ...extra,
  };
}

export function tableDetail(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    scenario_id: '00000000-0000-4000-8000-0000000000a1',
    title: '목요일 모임',
    status: 'recruiting',
    rating: 'all',
    capacity: 4,
    member_count: 2,
    host_id: ME,
    is_public: false,
    has_password: false,
    narration_style: 'classic',
    round_time_limit: 300,
    narration_model: 'gemini-flash',
    credit_wait_seconds: 300,
    remove_short_payers: true,
    whisper_notice: false,
    references_enabled: false,
    created_at: '2026-10-22T00:00:00Z',
    opening: '문 앞에서 시작한다.',
    members: [member(ME, { is_host: true }), member(OTHER)],
    invite_code: 'ABC123',
    started_at: null,
    ended_at: null,
    ...extra,
  };
}

/** SSE 의 메시지 하나의 글 */
export function sse(event: string, data: unknown, id?: string): string {
  return `${id ? `id: ${id}\n` : ''}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** 정한 글을 내보내는 스트림의 응답. keepOpen 이면 요청이 끊길 때까지 닫지 않는다 */
export function sseResponse(request: SeenRequest, chunks: string[], keepOpen = true): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of [': connected\n\n', ...chunks]) controller.enqueue(encoder.encode(chunk));
      if (!keepOpen) controller.close();
      request.signal?.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')));
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

/** 방이 열릴 때 부르는 것들(테이블, 채팅, 번호, 스트림). 바꿀 것만 overrides 로 넘긴다 */
export function roomRoutes(tableId: string, overrides: Record<string, (request: SeenRequest) => Response> = {}) {
  const base = `/api/v1/game/tables/${tableId}`;
  return {
    [`GET ${base}`]: () => json(200, tableDetail(tableId)),
    [`GET ${base}/messages`]: () => json(200, { items: [], last_sequence: 0 }),
    [`GET ${base}/events`]: () => json(200, { items: [], last_sequence: 3 }),
    [`GET ${base}/whispers`]: () => json(200, { items: [], last_sequence: 0 }),
    [`GET ${base}/stream`]: (request: SeenRequest) => sseResponse(request, []),
    'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
    ...overrides,
  };
}
