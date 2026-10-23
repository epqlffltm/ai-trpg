// web/apps/web/src/pages/chat/studio/characters/mapItemsForms.test.ts
// 지도와 물건 탭(C6)의 입력: 화면이 붙이는 id, 장소를 지우면 길과 처음 있는 장소를 비우기, 길의 규칙, 그림 칸을 그대로 두기,
// 물건을 지우면 시작 소지품도 지우기, 시작 소지품의 규칙, 보낼 때 다듬기.

import { describe, expect, it } from 'vitest';
import type { AssetCharacterDetail, AssetPlace } from '../../../../api/types';
import {
  addItem,
  addStartItem,
  changeItem,
  countOf,
  hasItemsHints,
  isStartItem,
  ITEMS_MAX,
  itemsDraft,
  itemsHints,
  removeItem,
  toItemsBody,
  type ItemsDraft,
} from './itemsForm';
import { newKey } from './keys';
import {
  addPath,
  addPlace,
  hasMapHints,
  mapDraft,
  mapHints,
  minutesOf,
  pathsTouching,
  PLACES_MAX,
  removePlace,
  toMapBody,
  type MapDraft,
} from './mapForm';

const IMAGE = '00000000-0000-4000-8000-0000000000f1';
const NEWER = '00000000-0000-4000-8000-0000000000f2';
/** 아직 아무것도 저장하지 않은 캐릭터 */
const EMPTY = { places: [], items: [] } as unknown as AssetCharacterDetail;

function place(id: string, name: string, extra: Partial<AssetPlace> = {}): AssetPlace {
  return { id, name, description: '', image_id: null, backgrounds: {}, ...extra };
}

describe('id', () => {
  it('서버가 받는 글자로 붙이고 겹치면 다시 뽑는다', () => {
    const picks = ['aaaa1111', 'bbbb2222'];
    expect(newKey('place', ['place-aaaa1111'], () => picks.shift() as string)).toBe('place-bbbb2222');
    expect(newKey('item', [])).toMatch(/^item-[0-9a-f]{8}$/);
  });
});

describe('지도', () => {
  const two: MapDraft = {
    places: [place('p1', '집'), place('p2', '시장')],
    paths: [{ a: 'p1', b: 'p2', minutes: '15' }],
    startPlace: 'p1',
  };

  it('장소를 지우면 그 장소를 잇는 길과 처음 있는 장소를 비운다', () => {
    expect(pathsTouching(two, 'p1')).toBe(1);
    expect(removePlace(two, 'p1')).toEqual({ places: [place('p2', '시장')], paths: [], startPlace: '' });
    expect(removePlace(two, 'p2').startPlace).toBe('p1');
  });

  it('길은 서로 다른 두 장소, 0~1440 분, 같은 두 장소 사이에 하나다', () => {
    expect([minutesOf('0'), minutesOf('1440'), minutesOf('1441'), minutesOf('-1'), minutesOf('')]).toEqual([0, 1440, null, null, null]);
    const paths = [
      { a: 'p1', b: 'p2', minutes: '5' },
      { a: '', b: 'p2', minutes: '5' },
      { a: 'p1', b: 'p1', minutes: '5' },
      { a: 'p1', b: 'p2', minutes: 'x' },
      { a: 'p2', b: 'p1', minutes: '5' },
    ];
    const hints = mapHints({ ...two, paths });
    expect(hints.paths[0]).toBeUndefined();
    expect(hints.paths[1]).toMatch(/두 장소를 골라/);
    expect(hints.paths[2]).toMatch(/서로 다른/);
    expect(hints.paths[3]).toMatch(/0~1440/);
    expect(hints.paths[4]).toMatch(/이미 있습니다/);
  });

  it('장소의 이름은 1~30자, 설명은 1,000자', () => {
    const hints = mapHints({ ...two, places: [place('p1', ' '), place('p2', '가'.repeat(31), { description: '가'.repeat(1001) })] });
    expect(hints.places.p1).toEqual({ name: expect.stringMatching(/적어 주세요/) });
    expect(hints.places.p2).toEqual({ name: expect.stringMatching(/30자/), description: expect.stringMatching(/1000자/) });
    expect(hasMapHints(mapHints(two))).toBe(false);
  });

  it('더하기는 상한까지, 길은 비어 시작한다', () => {
    const full = { ...two, places: Array.from({ length: PLACES_MAX }, (_, i) => place(`p${i}`, '곳')) };
    expect(addPlace(full, 'new')).toBe(full);
    expect(addPlace(two, 'p3').places.at(-1)).toEqual(place('p3', ''));
    expect(addPath(two).paths.at(-1)).toEqual({ a: '', b: '', minutes: '10' });
  });

  it('새 장소의 그림 칸은 그대로 두고, 고르지 않은 처음 장소는 null 이다', () => {
    const pictured = place('p1', ' 집 ', { image_id: IMAGE, backgrounds: { night: IMAGE } });
    expect(toMapBody({ places: [pictured], paths: [], startPlace: '' }, EMPTY)).toEqual({
      places: [{ id: 'p1', name: '집', description: '', image_id: IMAGE, backgrounds: { night: IMAGE } }],
      paths: [],
      start_place: null,
    });
    expect(toMapBody(two, EMPTY)).toMatchObject({ paths: [{ a: 'p1', b: 'p2', minutes: 15 }], start_place: 'p1' });
    const character = { places: [pictured], paths: [{ a: 'p1', b: 'p9', minutes: 3 }], start_place: null } as unknown as AssetCharacterDetail;
    expect(mapDraft(character)).toEqual({ places: [pictured], paths: [{ a: 'p1', b: 'p9', minutes: '3' }], startPlace: '' });
  });
});

describe('탭끼리 그림 칸', () => {
  it('지도 탭은 저장된 장소의 그림 칸을 가장 최근에 받은 것으로 보낸다(그림 탭이 붙인 배경을 되돌리지 않는다)', () => {
    const opened = { places: [place('p1', '집')], paths: [], startPlace: 'p1' };
    const latest = { places: [place('p1', '집', { image_id: NEWER, backgrounds: { night: NEWER } })], items: [] } as unknown as AssetCharacterDetail;

    const body = toMapBody({ ...opened, places: [place('p1', '우리 집')] }, latest);

    expect(body.places).toEqual([{ id: 'p1', name: '우리 집', description: '', image_id: NEWER, backgrounds: { night: NEWER } }]);
  });

  it('물건 탭도 저장된 물건의 그림은 가장 최근에 받은 것으로 보낸다', () => {
    const opened: ItemsDraft = {
      items: [{ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: null }],
      startItems: [],
    };
    const latest = { places: [], items: [{ ...opened.items[0], image_id: NEWER }] } as unknown as AssetCharacterDetail;

    expect(toItemsBody(opened, latest).items?.[0]?.image_id).toBe(NEWER);
  });
});

describe('물건', () => {
  const one: ItemsDraft = {
    items: [{ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: IMAGE }],
    startItems: [{ item: 'i1', count: '2' }],
  };

  it('물건을 지우면 그 물건의 시작 소지품도 지운다', () => {
    expect(isStartItem(one, 'i1')).toBe(true);
    expect(removeItem(one, 'i1')).toEqual({ items: [], startItems: [] });
  });

  it('시작 소지품은 물건을 골라야 하고, 1~99, 물건마다 한 줄', () => {
    expect([countOf('1'), countOf('99'), countOf('0'), countOf('100'), countOf('a')]).toEqual([1, 99, null, null, null]);
    const hints = itemsHints({
      ...one,
      startItems: [
        { item: 'i1', count: '1' },
        { item: '', count: '1' },
        { item: 'i1', count: '0' },
        { item: 'i1', count: '3' },
      ],
    });
    expect(hints.startItems[0]).toBeUndefined();
    expect(hints.startItems[1]).toMatch(/물건을 골라/);
    expect(hints.startItems[2]).toMatch(/1~99/);
    expect(hints.startItems[3]).toMatch(/이미 있습니다/);
  });

  it('물건의 이름은 1~30자, 설명은 500자', () => {
    const named = changeItem(one, 'i1', { name: '', description: '가'.repeat(501) });
    expect(itemsHints(named).items.i1).toEqual({ name: expect.any(String), description: expect.stringMatching(/500자/) });
    expect(hasItemsHints(itemsHints(one))).toBe(false);
  });

  it('더하기와 보내기. 그림은 그대로 둔다', () => {
    const full = { ...one, items: Array.from({ length: ITEMS_MAX }, (_, i) => ({ ...one.items[0], id: `i${i}` }) as ItemsDraft['items'][number]) };
    expect(addItem(full, 'x')).toBe(full);
    expect(addItem(one, 'i2').items.at(-1)).toEqual({ id: 'i2', name: '', description: '', kind: 'thing', consumable: false, giftable: false, image_id: null });
    expect(addStartItem(one).startItems.at(-1)).toEqual({ item: '', count: '1' });
    const clothes = changeItem(one, 'i1', { name: ' 외투 ', kind: 'clothing', giftable: true });
    expect(toItemsBody(clothes, EMPTY)).toEqual({
      items: [{ id: 'i1', name: '외투', description: '', kind: 'clothing', consumable: false, giftable: true, image_id: IMAGE }],
      start_items: [{ item: 'i1', count: 2 }],
    });
    const character = { items: one.items, start_items: [{ item: 'i1', count: 2 }] } as unknown as AssetCharacterDetail;
    expect(itemsDraft(character)).toEqual(one);
  });
});
