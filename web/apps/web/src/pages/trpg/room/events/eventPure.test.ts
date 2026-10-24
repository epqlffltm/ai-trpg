// web/apps/web/src/pages/trpg/room/events/eventPure.test.ts
// 일어난 일(④-2)의 순수한 함수. 이벤트 한 줄의 글, 빠진 칸, 라운드 화면에 있는 것을 빼기, 방 위의 알림 고르기를 본다.

import { describe, expect, it } from 'vitest';
import type { TableDetail, TableEvent } from '../../../../api/types';
import { event, ME, OTHER, tableDetail } from '../../../../test/tableFixtures';
import { eventLine, eventRound, eventRows, type EventContext, type EventType } from './eventLines';
import { modelNoticeEvent, roomNotices, roundNoticeEvents } from './roomNotices';

const NAMES: Record<string, string> = { [ME]: '렌', [OTHER]: '미아' };

const CTX: EventContext = {
  table: tableDetail('t', { status: 'playing' }) as unknown as TableDetail,
  nameOfMember: (userId) => NAMES[userId] ?? '누군가',
  modelName: (slug) => (slug === 'gemini-flash' ? 'Gemini Flash' : slug),
};

function ev(sequence: number, type: EventType, payload: Record<string, unknown> = {}, extra: Record<string, unknown> = {}): TableEvent {
  return event(sequence, type, payload, extra) as unknown as TableEvent;
}

function line(type: EventType, payload: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
  return eventLine(ev(1, type, payload, extra), CTX);
}

// 서버의 EventType 모두(api/generated/trpg.ts). 칸이 없어도 글이 나와야 한다
const ALL: EventType[] = [
  'table_created', 'member_joined', 'member_left', 'member_kicked', 'host_changed', 'abilities_rolled', 'reroll_granted',
  'narration_style_changed', 'round_time_limit_changed', 'narration_tier_changed', 'narration_model_changed', 'credit_wait_changed',
  'whisper_notice_changed', 'references_changed', 'ledger_drafts_changed', 'whisper_sent', 'table_started', 'gm_narration',
  'round_opened', 'player_action', 'check_rolled', 'hp_changed', 'npc_changed', 'npc_attitude_changed', 'monster_changed',
  'monster_attacked', 'npc_attacked', 'injury_gained', 'injury_ended', 'injury_treated', 'naming_resolved', 'death_save_rolled',
  'character_died', 'character_joined', 'items_gained', 'items_lost', 'item_used', 'item_given', 'item_put_down', 'steal_attempted',
  'quest_changed', 'clock_step_changed', 'character_moved', 'happening_occurred', 'place_searched', 'character_rested',
  'character_revived', 'round_closed', 'narration_failed', 'narration_abandoned', 'narration_credits_short',
  'narration_model_not_for_sale', 'narration_model_retiring', 'narration_model_replaced', 'narration_model_unavailable',
  'member_dropped', 'narration_credits_released', 'table_ended', 'item_traded', 'money_paid',
  'equipment_changed', 'door_changed', 'monsters_appeared',
];

const IN_ROUNDS: EventType[] = ['gm_narration', 'player_action', 'check_rolled'];

describe('eventLine', () => {
  it('모든 종류가 칸이 비어도 글이 된다. 라운드 화면에 있는 셋만 빠진다', () => {
    for (const type of ALL) {
      const result = eventLine({ ...ev(1, type), payload: undefined } as unknown as TableEvent, CTX);
      if (IN_ROUNDS.includes(type)) expect(result, type).toBeNull();
      else expect(result?.text, type).toBeTruthy();
    }
  });

  it('무작위 조우는 어디에 무엇이 몇 마리 나왔는지, 쉬는 중이었는지 보인다(#283)', () => {
    const place = { entry_id: 'p1', name: '깊은 수로' };
    const monster = { id: 'm1', name: '수로 쥐' };
    expect(line('monsters_appeared', { place, monster, count: 3, cause: 'arrive' })?.text).toBe('조우: 깊은 수로 · 수로 쥐 3마리가 나타났습니다');
    expect(line('monsters_appeared', { place, monster, count: 1, cause: 'rest' })?.text).toBe('조우: 깊은 수로 · 수로 쥐 1마리가 쉬는 중에 덮쳤습니다');
  });

  it('사람은 캐릭터의 이름, 없으면 user_id, 없으면 행한 사람으로 부른다', () => {
    expect(line('member_left', { character_name: '조' })?.text).toBe('조: 나갔습니다.');
    expect(line('member_kicked', { user_id: OTHER })?.text).toBe('미아: 방장이 내보냈습니다.');
    expect(line('member_joined', { via: 'invite' }, { actor_id: ME })?.text).toBe('렌: 들어왔습니다.');
    expect(line('host_changed', { user_id: OTHER })?.text).toBe('미아: 방장이 되었습니다.');
  });

  it('몸과 물건과 장소', () => {
    expect(line('hp_changed', { character_name: '렌', before: 9, after: 0, downed: true })?.text).toBe('렌: HP 9 → 0 · 쓰러짐');
    expect(line('npc_changed', { name: '문지기', kind: 'damage', amount: 3, status: 'downed' })?.text).toBe('문지기: 피해 3 · 쓰러짐');
    expect(line('injury_gained', { name: '문지기', injury: 'broken_arm' })?.text).toBe('문지기: 부러진 팔 입음');
    expect(line('monster_attacked', { name: '수로 쥐', attack: '물기', character_name: '렌', success: true })?.text).toBe('수로 쥐: 물기 → 렌 맞힘');
    const attack = { name: '할퀴기', ability: 'str', difficulty: 'normal', harm: 'light' };
    expect(line('monster_attacked', { name: '고블린', attack, character_name: '렌', success: false })?.text).toBe('고블린: 할퀴기 → 렌 빗나감');
    const blow = {
      weapon: null,
      location: 'body',
      location_name: '몸',
      aimed: false,
      defense: 5,
      mode: 'save',
      pierce: null,
      save: { kind: 'armor', value: 5, roll: 10, target: 7, saved: true },
    };
    expect(line('monster_attacked', { name: '고블린', attack, character_name: '렌', success: true, blow })?.text).toBe(
      '고블린: 할퀴기 → 렌 맞힘 (몸 · 방어 5 · 아머 세이브 10 + 5 → 막음)',
    );
    const npcBlow = { ...blow, weapon: { entry_id: 'w', name: '단검', bonus: 1, ap: 0 }, mode: 'ac', save: null, location_name: null, defense: 0 };
    expect(line('npc_attacked', { name: '문지기', attack, character_name: '렌', success: true, blow: npcBlow })?.text).toBe(
      '문지기: 할퀴기 → 렌 맞힘 (단검 +1)',
    );
    // 모양이 다른 장비 줄은 빼고 적는다(줄이 깨지지 않게)
    expect(line('monster_attacked', { name: '고블린', attack, character_name: '렌', success: true, blow: { ...blow, save: { kind: 'armor' } } })?.text).toBe(
      '고블린: 할퀴기 → 렌 맞힘',
    );
    expect(line('monster_attacked', { name: '고블린', attack: {}, character_name: '렌', success: true })?.text).toBe('고블린: 공격 → 렌 맞힘');
    const place = { entry_id: 'p1', name: '지하 저장고' };
    expect(line('items_gained', { character_name: '미아', name: '은 성배', count: 1, total: 1, source: 'search', place })?.text).toBe(
      '미아: 은 성배 ×1 얻음(지금 1) · 지하 저장고에서 찾음',
    );
    expect(line('items_gained', { character_name: '렌', name: '열쇠', count: 1, total: 1, source: 'npc', npc_name: '문지기' })?.text).toBe(
      '렌: 열쇠 ×1 얻음(지금 1) · 문지기에게서',
    );
    expect(line('item_given', { character_name: '미아', name: '약초', count: 1, given: true, target: { user_id: ME, character_name: '렌' } })?.text).toBe(
      '미아: 약초 ×1 → 렌',
    );
    expect(line('character_moved', { character_name: '미아', from: { name: '부엌' }, to: { name: '회랑' }, carried_by: ME })?.text).toBe(
      '미아: 부엌 → 회랑(업은 사람 렌)',
    );
    expect(line('place_searched', { character_name: '렌', place: { name: '부엌' }, found: [{}], items: [] })?.text).toBe('렌: 부엌에서 길 1개, 물건 0가지를 찾았습니다.');
    expect(line('quest_changed', { name: '울리지 않는 종', status: 'succeeded' })?.text).toBe('퀘스트 「울리지 않는 종」: 성공');
    expect(line('item_traded', { character_name: '렌', side: 'buy', npc_name: '상인', name: '횃불', count: 2, price: 6, traded: true, money: 4 })?.text).toBe(
      '렌: 횃불 ×2 삼 · 상인에게 6(남은 돈 4)',
    );
    expect(line('money_paid', { character_name: '렌', amount: 3, paid: true, target: { user_id: OTHER, character_name: '미아' } })?.text).toBe('렌: 3 → 미아');
    expect(line('naming_resolved', { character_name: '렌', correct: true, name: '마르타' })?.text).toBe('렌: 맞혔습니다. 마르타');
    expect(line('equipment_changed', { character_name: '렌', change: 'wear', name: '대검', slots: ['main_hand', 'off_hand'] })?.text).toBe(
      '렌: 대검 착용 (주손·보조손)',
    );
    expect(line('equipment_changed', { character_name: '렌', change: 'take_off', name: '투구', slots: ['head'] })?.text).toBe('렌: 투구 벗음 (head)');
  });

  it('설정과 모델은 보일 이름으로 적는다', () => {
    expect(line('narration_model_changed', { narration_model: 'gemini-flash', input_step: 0, output_step: 2 })?.text).toBe(
      '서술 모델: Gemini Flash(기억 기본 · 장면 2단계)',
    );
    expect(line('narration_style_changed', { narration_style: 'hardboiled' })?.text).toBe('서술 문체: 하드보일드');
    expect(line('narration_style_changed', { narration_style: null })?.text).toBe('서술 문체: 시나리오의 추천');
    expect(line('round_time_limit_changed', { round_time_limit: 600 })?.text).toBe('라운드 시간 제한: 10분');
    expect(line('round_opened', { number: 3, clock: { day: 1, hour: 22, minute: 20 } })?.text).toBe('라운드 3: 열림 · 1일째 22:20');
  });

  it('서술을 막는 일은 important 이고 할 것을 적는다', () => {
    const short = line('narration_credits_short', { round: 2, user_id: OTHER, reason: 'credits' });
    expect(short).toEqual({ text: expect.stringContaining('미아: 크레딧이 모자라 서술하지 못합니다.') as string, important: true });
    expect(line('narration_model_retiring', { narration_model: 'gemini-flash', retires_on: '2026-11-30', days_left: 7 })?.text).toBe(
      '서술 모델 Gemini Flash: 11월 30일에 끝납니다(7일 남음).',
    );
    expect(line('character_died', { character_name: '조' })?.important).toBe(true);
    expect(line('hp_changed', { character_name: '렌', before: 9, after: 5 })?.important).toBe(false);
  });
});

describe('eventRound, eventRows', () => {
  it('라운드는 round, 라운드를 열고 닫은 일은 number 다', () => {
    expect(eventRound(ev(1, 'hp_changed', { round: 4 }))).toBe(4);
    expect(eventRound(ev(1, 'round_opened', { number: 5 }))).toBe(5);
    expect(eventRound(ev(1, 'member_joined'))).toBeNull();
  });

  it('글이 없는 것은 빼고 최근 것이 위다', () => {
    const rows = eventRows([ev(1, 'table_started'), ev(2, 'gm_narration', { text: '…' }), ev(3, 'round_opened', { number: 1 })], CTX);
    expect(rows.map((row) => row.event.sequence)).toEqual([3, 1]);
  });
});

describe('roomNotices', () => {
  it('이번 라운드의 알림만, 같은 사람의 같은 알림은 나중 것 하나', () => {
    const events = [
      ev(1, 'narration_credits_short', { round: 1, user_id: OTHER }),
      ev(2, 'narration_credits_short', { round: 2, user_id: OTHER }),
      ev(3, 'narration_credits_short', { round: 2, user_id: OTHER, reason: 'gold_required' }),
      ev(4, 'narration_credits_short', { round: 2, user_id: ME }),
      ev(5, 'hp_changed', { round: 2 }),
    ];
    expect(roundNoticeEvents(events, 2).map((one) => one.sequence)).toEqual([3, 4]);
    expect(roundNoticeEvents(events, null)).toEqual([]);
  });

  it('모델의 알림은 그 뒤에 모델이 바뀌면 사라진다', () => {
    const unavailable = ev(1, 'narration_model_unavailable', { narration_model: 'gemini-flash' });
    expect(modelNoticeEvent([unavailable])).toBe(unavailable);
    expect(modelNoticeEvent([unavailable, ev(2, 'narration_model_changed', { narration_model: 'x' })])).toBeNull();
    expect(modelNoticeEvent([ev(2, 'narration_model_replaced'), unavailable])).toBe(unavailable);
  });

  it('내 크레딧이 모자라다는 알림에만 충전으로 가는 길을 붙인다', () => {
    const events = [ev(1, 'narration_credits_short', { round: 2, user_id: ME }), ev(2, 'narration_credits_short', { round: 2, user_id: OTHER })];
    expect(roomNotices(events, 2, CTX, ME).map((notice) => notice.charge)).toEqual([true, false]);
    expect(roomNotices(events, 2, CTX).map((notice) => notice.charge)).toEqual([false, false]);
  });

  it('모델의 알림이 먼저, 막는 일은 error', () => {
    const notices = roomNotices(
      [ev(1, 'narration_model_retiring', { narration_model: 'gemini-flash', days_left: 3 }), ev(2, 'narration_failed', { round: 2, reason: 'timeout' })],
      2,
      CTX,
    );
    expect(notices.map((notice) => [notice.tone, notice.text])).toEqual([
      ['info', '서술 모델 Gemini Flash: 끝납니다(3일 남음).'],
      ['error', '라운드 2: 서술에 실패했습니다(timeout).'],
    ]);
  });
});
