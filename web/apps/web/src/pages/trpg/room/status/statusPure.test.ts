// web/apps/web/src/pages/trpg/room/status/statusPure.test.ts
// 상태 패널(B7)의 순수한 함수. 몸 상태, 죽음의 굴림, 부상이 풀리는 때, 시각, 회복량, 길과 길 옆의 문·넘기, 단축키를 본다.

import { describe, expect, it } from 'vitest';
import type { Sheet, SheetInjury, TableDetail, TableMap, TableMember } from '../../../../api/types';
import { ME, member, OTHER, RULES, sheet, tableDetail } from '../../../../test/tableFixtures';
import { tabForKey } from './statusTabs';
import {
  clockLabel,
  conditionOf,
  deathSaveProgress,
  healsLabel,
  hpRatio,
  injuryTiming,
  meFirst,
  minutesLabel,
  waysFrom,
  wayNotes,
  whoIsWhere,
} from './statusView';

const rules = RULES as unknown as TableDetail['rules'];

function asSheet(extra: Record<string, unknown> = {}): Sheet {
  return sheet(extra) as unknown as Sheet;
}

const MAP = {
  places: [
    { entry_id: 'p1', name: '수도원 문', items: [] },
    { entry_id: 'p2', name: '부엌', items: [] },
    { entry_id: 'p3', name: '종탑', items: [] },
  ],
  routes: [
    { from_place: 'p1', to_place: 'p2', travel_minutes: 5, two_way: true },
    { from_place: 'p3', to_place: 'p1', travel_minutes: null, two_way: false },
    { from_place: 'p2', to_place: 'p3', travel_minutes: 90, two_way: false },
  ],
} as unknown as TableMap;

describe('statusView', () => {
  it('HP 가 0 이하이면 쓰러짐, 죽었으면 죽음, 시트가 없으면 정하지 않음', () => {
    expect(conditionOf(asSheet())).toBe('standing');
    expect(conditionOf(asSheet({ hp: 0 }))).toBe('downed');
    expect(conditionOf(asSheet({ hp: 0, dead: true }))).toBe('dead');
    expect(conditionOf(null)).toBe('none');
    expect(hpRatio(asSheet({ hp: 3 }))).toBe(0.25);
    expect(hpRatio(asSheet({ hp: -2 }))).toBe(0);
  });

  it('죽음의 굴림은 규칙의 횟수와 함께 적는다', () => {
    expect(deathSaveProgress(asSheet({ death_successes: 1, death_failures: 2 }), rules)).toBe('죽음의 굴림 성공 1/3 · 실패 2/3');
  });

  it('부상은 짧으면 라운드, 오래 가면 시각, 결손은 낫지 않음', () => {
    const base = { round: 2, ends_after_round: null, heals_at: null };
    expect(injuryTiming({ ...base, injury: 'sprain', ends_after_round: 4 } as SheetInjury, rules)).toBe('라운드 4까지');
    const healsAt = { day: 2, hour: 7, minute: 5, time_of_day: 'morning' };
    expect(injuryTiming({ ...base, injury: 'broken_arm', heals_at: healsAt } as SheetInjury, rules)).toBe('2일째 07:05에 나음');
    expect(injuryTiming({ ...base, injury: 'lost_eye' } as SheetInjury, rules)).toBe('낫지 않음');
  });

  it('시각과 흐르는 시간을 읽기 좋게', () => {
    const table = tableDetail('t') as unknown as TableDetail;
    expect(clockLabel(table.clock)).toBe('1일째 08:00 · 아침');
    expect(minutesLabel(45)).toBe('45분');
    expect(minutesLabel(120)).toBe('2시간');
    expect(minutesLabel(90)).toBe('1시간 30분');
  });

  it('소모품의 회복량은 판의 물건과 규칙의 등급에서 찾는다', () => {
    const table = tableDetail('t', {
      items: [{ entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light' }],
    }) as unknown as TableDetail;
    expect(healsLabel(table, 'i1')).toBe('회복 가벼움(1d4)');
    expect(healsLabel(table, 'none')).toBeNull();
  });

  it('갈 수 있는 곳은 나가는 길과 양쪽 길이다. 한쪽 길을 거꾸로 가지 않는다', () => {
    expect(waysFrom(MAP, 'p1')).toMatchObject([{ placeId: 'p2', name: '부엌', minutes: 5 }]);
    expect(waysFrom(MAP, 'p3')).toMatchObject([{ placeId: 'p1', name: '수도원 문', minutes: null }]);
    expect(waysFrom(MAP, 'p3')[0]?.route).toBe(MAP.routes[1]);
    expect(waysFrom(MAP, null)).toEqual([]);
  });

  it('길 옆에 잠긴 자물쇠, 걸린 빗장(이쪽·저쪽), 넘기 판정을 적는다. 열린 문과 부서진 문은 적지 않는다', () => {
    const route = { from_place: 'p1', to_place: 'p2', two_way: true, locked: true, barred: true, bar_side: 'p1', broken: false, cross: { ability: 'str', difficulty: 'normal' } };
    const way = { placeId: 'p2', name: '부엌', minutes: 5, route } as never;
    expect(wayNotes(way, 'p1', rules)).toEqual(['자물쇠 잠김', '빗장 걸림(이쪽)', '넘기 판정: 근력, 보통']);
    expect(wayNotes(way, 'p2', rules)).toContain('빗장 걸림(저쪽)');
    const open = { ...route, locked: false, barred: false, broken: true, cross: null };
    expect(wayNotes({ placeId: 'p2', name: '부엌', minutes: 5, route: open } as never, 'p1', rules)).toEqual([]);
  });

  it('장소마다 누가 있는지, 나를 맨 앞에', () => {
    const members = [
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet({ place_id: 'p2' }) }),
      member(ME, { character: { name: '렌', description: '' }, sheet: sheet({ place_id: 'p2' }) }),
    ] as unknown as TableMember[];
    expect(whoIsWhere(MAP, members)).toEqual([{ name: '부엌', characters: ['미아', '렌'] }]);
    expect(meFirst(members, ME).map((entry) => entry.user_id)).toEqual([ME, OTHER]);
  });
});

describe('tabForKey', () => {
  const press = { ctrlKey: false, altKey: false, metaKey: false, targetTag: 'BODY', targetEditable: false };

  it('C, I, J 로 탭을 고른다. 글을 쓰는 칸과 조합 키는 빼고', () => {
    expect(tabForKey({ ...press, key: 'i' })).toBe('items');
    expect(tabForKey({ ...press, key: 'J' })).toBe('world');
    expect(tabForKey({ ...press, key: 'c', targetTag: 'TEXTAREA' })).toBeNull();
    expect(tabForKey({ ...press, key: 'c', targetEditable: true })).toBeNull();
    expect(tabForKey({ ...press, key: 'c', ctrlKey: true })).toBeNull();
    expect(tabForKey({ ...press, key: 'x' })).toBeNull();
  });
});
