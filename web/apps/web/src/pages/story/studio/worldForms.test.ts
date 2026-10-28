// web/apps/web/src/pages/story/studio/worldForms.test.ts
// 세계관 만들기(D7)의 입력의 순수한 함수. 기본, 진행(시간대, 기한, 보이기, 시작), 지도(배경, 지우기), 물건, 게시의 글, 실패의 글.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { toWorldBasicsBody, worldBasicsHints, worldNameHint } from './worldBasicsForm';
import { addWorldItem, removeWorldItem, toWorldItemsBody, worldItemsHints } from './worldItemsForm';
import { addWorldPlace, removeWorldPlace, setBackground, toWorldMapBody, worldMapDraft, worldMapHints } from './worldMapForm';
import { describeWorldProblem, describeWorldPublishProblem, isMissingWorld } from './worldProblem';
import { addSlot, changeSlot, countOf, hourOf, progressDraft, progressHints, removeSlot, toProgressBody, togglePanel } from './worldProgressForm';
import { worldProblemLine, worldWarningText } from './worldPublishText';
import { worldTabOf } from './worldTabs';

function world(extra: Partial<StoryWorldDetail> = {}): StoryWorldDetail {
  return {
    id: 'w1',
    name: '여름 학교',
    intro_html: '',
    tags: ['학원'],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [
      { id: 'morning', name: '아침', start_hour: 7 },
      { id: 'night', name: '밤', start_hour: 21 },
    ],
    start_slot: 'night',
    deadline_days: 30,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro', 'age', 'gender', 'affection'] },
    places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }],
    paths: [],
    start_place: 'park',
    items: [{ id: 'flower', name: '꽃', description: '', consumable: false, image_id: null }],
    start_items: [{ item: 'flower', count: 2 }],
    cast: [],
    events: [],
    endings: [],
    lorebooks: [],
    latest_version: null,
    published_at: null,
    created_at: '',
    updated_at: '',
    ...extra,
  } as StoryWorldDetail;
}

describe('세계관의 입력', () => {
  it('기본: 이름과 태그를 검사하고 겹친 태그를 뺀다', () => {
    expect(worldNameHint(' ')).toBe('이름을 적어 주세요.');
    expect(worldNameHint('가'.repeat(51))).toMatch(/50자/);
    expect(worldBasicsHints({ name: '가', tags: Array.from({ length: 11 }, (_, i) => `t${i}`).join(','), rating: 'all', visibility: 'private', imageId: null }).tags).toMatch(/10개/);
    expect(toWorldBasicsBody({ name: ' 여름 ', tags: 'a, a, b', rating: 'adult', visibility: 'public', imageId: 'img' })).toEqual({ name: '여름', tags: ['a', 'b'], rating: 'adult', visibility: 'public', image_id: 'img' });
  });

  it('진행: 시간대를 하나는 남기고, 지운 시작 시간대를 비우고, 시각과 이름을 검사한다', () => {
    const draft = progressDraft(world());
    expect(draft.deadline).toBe('30');
    const removed = removeSlot(draft, 'night');
    expect(removed.startSlot).toBe('');
    expect(removeSlot(removed, 'morning').slots).toHaveLength(1);
    const added = changeSlot(addSlot(draft, 'slot-1'), 'slot-1', { name: '아침', startHour: '25' });
    const hints = progressHints(added);
    expect(hints.slots['slot-1']).toEqual({ name: '같은 이름의 시간대가 이미 있습니다.', startHour: '시작 시각은 0~23 사이의 정수(시)입니다.' });
    expect(progressHints({ ...draft, deadline: '0' }).deadline).toMatch(/1~365/);
    expect(progressHints({ ...draft, startItems: [{ item: 'flower', count: '1' }, { item: 'flower', count: '1' }] }).startItems[1]).toMatch(/같은 물건/);
    expect(hourOf('07')).toBe(7);
    expect(hourOf('24')).toBeNull();
    expect(countOf('100', 99)).toBeNull();
  });

  it('진행: 비운 칸은 null, 지금 없는 장소와 물건은 보내지 않는다', () => {
    const draft = { ...progressDraft(world()), startSlot: '', deadline: ' ', startPlace: 'park' };
    const body = toProgressBody(draft, { places: [], items: [] });
    expect(body).toMatchObject({ start_slot: null, deadline_days: null, start_place: null, start_items: [] });
    expect(toProgressBody(draft, world()).start_items).toEqual([{ item: 'flower', count: 2 }]);
  });

  it('진행: 인물 창의 항목은 서버의 차례를 지킨다', () => {
    const show = { reveal: 'shown', map: 'shown', panel: ['affection'] } as StoryWorldDetail['show'];
    expect(togglePanel(show, 'intro').panel).toEqual(['intro', 'affection']);
    expect(togglePanel(show, 'affection').panel).toEqual([]);
  });

  it('지도: 시간대 배경을 붙이고 떼며, 없는 시간대의 배경은 보내지 않고, 시작 장소를 지우면 비운다', () => {
    let draft = worldMapDraft(world());
    draft = setBackground(draft, 'park', 'morning', 'img1');
    draft = setBackground(draft, 'park', 'gone', 'img2');
    expect(toWorldMapBody(draft, world()).places?.[0]?.backgrounds).toEqual({ morning: 'img1' });
    expect(setBackground(draft, 'park', 'morning', null).places[0]?.backgrounds).toEqual({ gone: 'img2' });
    expect(toWorldMapBody(draft, world())).not.toHaveProperty('start_place');
    draft = addWorldPlace(draft, 'place-1');
    expect(worldMapHints(draft).places['place-1']).toEqual({ name: '이름을 적어 주세요.' });
    expect(toWorldMapBody(removeWorldPlace(draft, 'park'), world())).toMatchObject({ start_place: null });
  });

  it('물건: 지운 물건의 시작 소지품을 함께 보낸다', () => {
    const items = removeWorldItem(addWorldItem(world().items, 'item-1'), 'flower');
    expect(worldItemsHints(items)['item-1']).toEqual({ name: '이름을 적어 주세요.' });
    expect(toWorldItemsBody(items, world())).toMatchObject({ start_items: [] });
    expect(toWorldItemsBody(world().items, world())).not.toHaveProperty('start_items');
  });

  it('게시의 글과 실패의 글, 탭', () => {
    expect(worldProblemLine('start_place_missing')).toEqual({ text: '장소가 없거나 시작 장소를 고르지 않았습니다.', tab: 'progress' });
    expect(worldProblemLine('cast_empty').tab).toBeUndefined();
    expect(worldProblemLine('new_problem')).toEqual({ text: 'new_problem' });
    expect(worldWarningText('ending_unreachable')).toBe('고를 일이 없는 엔딩이 있습니다.');
    expect(worldTabOf('map')).toBe('map');
    expect(worldTabOf('cast')).toBe('basics');
    expect(describeWorldProblem(new ApiError({ status: 422, detail: 'x', code: 'character_not_owned' })).message).toMatch(/내 캐릭터가 아닌/);
    expect(describeWorldProblem(new ApiError({ status: 403, detail: 'x', code: 'adult_content_required' })).fields).toHaveProperty('rating');
    expect(describeWorldPublishProblem(new ApiError({ status: 409, detail: 'x', body: { problems: ['cast_empty'] } })).message).toMatch(/게시할 조건/);
    expect(isMissingWorld(new ApiError({ status: 404, detail: 'x' }))).toBe(true);
  });
});
