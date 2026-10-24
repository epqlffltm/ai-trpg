// web/apps/web/src/test/scenarioFixtures.ts
// 시험의 시나리오 하나(ScenarioDetail). 칸을 모두 빈 값으로 채워 두고 시험마다 필요한 칸만 바꾼다.
// 서버는 칸을 빠짐없이 주므로, 시험도 그렇게 해야 아직 쓰지 않는 탭이 빈 칸에서 넘어지지 않는다.

export const SCENARIO_ID = '00000000-0000-4000-8000-0000000000d1';

export function scenarioDetail(extra: Record<string, unknown> = {}) {
  return {
    id: SCENARIO_ID,
    title: '비 내리는 수도원',
    description: '',
    visibility: 'private',
    created_at: '2026-10-23T00:00:00Z',
    updated_at: '2026-10-23T00:00:00Z',
    rating: 'all',
    rulebook_id: null,
    world_id: null,
    lorebook_ids: [],
    bestiary_ids: [],
    openings: [],
    recommended_players: { min: 1, max: 4 },
    pregens: [],
    character_modes: ['pregen', 'custom'],
    default_sheet: null,
    npc_sheets: [],
    default_npc_sheet: null,
    monster_sheets: [],
    encounters: [],
    wanders: [],
    items: [],
    starting_items: [],
    currency: null,
    quests: [],
    start_place: null,
    routes: [],
    landmarks: [],
    place_items: [],
    covers: [],
    happenings: [],
    npc_places: [],
    player_made_hp: null,
    reroll_allowed: false,
    narration_style: 'classic',
    narration_model: 'glm-air',
    narration_model_status: { state: 'ok', retires_on: null, replacement: null },
    clock: { start_day: 1, start_hour: 8, round_minutes: 10 },
    ...extra,
  };
}
