// web/apps/web/src/test/tableFixtures.ts
// 테이블 방의 시험에 쓰는 가짜 값과 가짜 스트림. 서버의 모양(TableDetail, MemberOut)에서 시험이 보는 칸만 채운다.
// 가짜 스트림은 정한 글을 차례로 내보내고, 열어 두라면 화면이 끊을(abort) 때까지 열어 둔다.

import type { SeenRequest } from './fakeFetch';
import { json } from './fakeFetch';

export const ME = '00000000-0000-4000-8000-0000000000e1';
export const OTHER = '00000000-0000-4000-8000-0000000000e2';

/** 시험의 규칙. 능력치 셋, 점수 3~18, 보정은 (점수-10)/2 내림, 최대 HP 에 건강의 보정을 더한다 */
export const RULES = {
  abilities: [
    { key: 'str', name: '근력' },
    { key: 'dex', name: '민첩' },
    { key: 'con', name: '건강' },
  ],
  score_min: 3,
  score_max: 18,
  modifier: { base: 10, step: 2 },
  hp_ability: 'con',
  default_difficulty: 'normal',
  difficulties: [
    { key: 'easy', name: '쉬움', target: 10 },
    { key: 'normal', name: '보통', target: 15 },
  ],
  death_save: { target: 10, successes: 3, failures: 3 },
  injuries: [
    { key: 'sprain', name: '삔 발목', healing: 'rounds', aimable: false },
    { key: 'broken_arm', name: '부러진 팔', healing: 'heals', aimable: true },
    { key: 'lost_eye', name: '잃은 눈', healing: 'permanent', aimable: true },
  ],
  magnitudes: [
    { key: 'light', name: '가벼움', count: 1, sides: 4 },
    { key: 'heavy', name: '무거움', count: 2, sides: 6 },
  ],
  treatment: null,
  rest: null,
  steal: null,
  point_buy: {
    budget: 10,
    costs: [
      { score: 8, cost: 0 },
      { score: 10, cost: 2 },
      { score: 12, cost: 4 },
      { score: 14, cost: 7 },
    ],
  },
  score_roll: { count: 4, sides: 6, keep: 3 },
};

export function pregen(name: string, extra: Record<string, unknown> = {}) {
  return {
    name,
    description: `${name}의 설명`,
    sheet: { abilities: { str: 14, dex: 12, con: 10 }, max_hp: 12 },
    taken_by: null,
    dead: false,
    ...extra,
  };
}

/** 시작한 뒤의 시트(SheetOut). 처음 값은 다치지 않았고 지닌 것이 없다 */
export function sheet(extra: Record<string, unknown> = {}) {
  return {
    number: 1,
    abilities: { str: 14, dex: 12, con: 10 },
    max_hp: 12,
    hp: 12,
    death_successes: 0,
    death_failures: 0,
    dead: false,
    injuries: [],
    items: [],
    money: 0,
    place_id: null,
    ...extra,
  };
}

/** 굴린 점수(members[].roll). 능력치 셋이라 점수도 셋이다 */
export function roll(scores: number[], extra: Record<string, unknown> = {}) {
  return {
    dice: scores.map(() => [6, 5, 4, 1]),
    scores,
    times_rolled: 1,
    character_number: 1,
    reroll_granted: false,
    ...extra,
  };
}

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
    rules: RULES,
    character_modes: ['pregen', 'custom', 'manual', 'point_buy', 'rolled'],
    default_sheet: { abilities: { str: 10, dex: 10, con: 10 }, max_hp: 10 },
    player_made_hp: { base: 8, cap: 20 },
    reroll_allowed: true,
    pregens: [pregen('렌'), pregen('미아', { taken_by: OTHER }), pregen('조', { dead: true })],
    items: [],
    currency: null,
    quests: [],
    map: null,
    clock: { day: 1, hour: 8, minute: 0, time_of_day: 'morning', next_step_minutes: 30, default_step_minutes: 30, step_changed: false },
    members: [member(ME, { is_host: true }), member(OTHER)],
    invite_code: 'ABC123',
    started_at: null,
    ended_at: null,
    ...extra,
  };
}

/** 라운드 하나(RoundOut). 처음 값은 선언을 받는 중이고 아무도 내지 않았다 */
export function round(number: number, extra: Record<string, unknown> = {}) {
  return {
    number,
    scene: `${number}번째 장면`,
    status: 'open',
    declarations: [],
    death_saves: [],
    arrivals: [],
    waiting_for: [ME, OTHER],
    created_at: '2026-10-22T00:00:00Z',
    deadline_at: null,
    narration_model: 'gemini-flash',
    price: null,
    closing_at: null,
    closed_at: null,
    narration_failed_at: null,
    narration_failures: 0,
    ...extra,
  };
}

/** 선언 하나(DeclarationOut) */
export function declaration(userId: string, extra: Record<string, unknown> = {}) {
  return {
    user_id: userId,
    character_name: userId === ME ? '렌' : '미아',
    content: null,
    action: null,
    outcome: null,
    ...extra,
  };
}

/** SSE 의 메시지 하나의 글 */
/** 일어난 일 하나(EventOut). payload 는 서버가 앉은 사람에게 보이는 칸만(responses.py 의 VISIBLE) */
export function event(sequence: number, type: string, payload: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  return {
    sequence,
    type,
    actor_id: null,
    payload,
    caused_by_sequence: null,
    action_group_id: null,
    created_at: '2026-10-22T00:00:00Z',
    ...extra,
  };
}

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
    [`GET ${base}/rounds/current`]: () => json(200, round(1)),
    [`GET ${base}/rounds`]: () => json(200, { items: [round(1)], total: 1 }),
    [`GET ${base}/rounds/current/people`]: () => json(200, { round: 1, people: [], monsters: [] }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
    // 일어난 일의 글이 모델의 이름을 찾는다(events/useEventContext). 모델을 보는 시험은 overrides 로 바꾼다
    'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
    ...overrides,
  };
}
