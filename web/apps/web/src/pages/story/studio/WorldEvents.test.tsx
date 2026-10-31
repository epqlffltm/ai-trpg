// web/apps/web/src/pages/story/studio/WorldEvents.test.tsx
// 세계관의 이벤트와 엔딩 탭(D7). 이벤트: 조건(다른 이벤트가 열렸다), 장면(상황, 나오는 인물), 열릴 때의 효과, 선택지와 그 효과, 차례.
// 엔딩: 시작의 대상은 고백할 수 있는 인물만, 시작을 바꾸면 대상을 비우고, 기한은 대상을 보내지 않는다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import type { ConditionChoices } from './conditionsForm';
import { addEffect, changeEffect, effectsHints, toEffects } from './effectsForm';
import { addEnding, changeEnding, toEndingsBody, triggerTargets } from './endingsForm';
import { addEvent, moveEventUp } from './eventsForm';
import { sceneHint, setSceneImage, toggleSceneCast, toScene, EMPTY_SCENE } from './sceneForm';

const WORLDS = '/api/v1/asset/worlds';
const ID = '00000000-0000-4000-8000-0000000000f9';
const MINA = '00000000-0000-4000-8000-0000000000d8';
const JUN = '00000000-0000-4000-8000-0000000000d9';
const AT = '2026-10-28T00:00:00Z';

function member(id: string, characterId: string, confession: boolean) {
  return {
    id,
    character_id: characterId,
    home: 'park',
    schedule: [],
    affection: { display: 'stage', start: 0, stages: [{ name: '친구', at: 0 }, { name: '사랑', at: 70 }], gifts: [] },
    confession: confession ? { stage: '사랑', when: { match: 'all', items: [] }, on_fail: 'continue', fail_drop: 10, cooldown_days: 1 } : null,
    reveal: null,
    map: null,
    map_stage: null,
    panel: null,
  };
}

function world(extra: Partial<StoryWorldDetail> = {}): StoryWorldDetail {
  return {
    id: ID,
    name: '여름 학교',
    intro_html: '',
    genre: 'romance',
    tags: [],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [{ id: 'morning', name: '아침', start_hour: 7 }],
    start_slot: 'morning',
    deadline_days: 30,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro', 'age', 'gender', 'affection'] },
    places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }],
    paths: [],
    start_place: 'park',
    items: [{ id: 'flower', name: '꽃', description: '', consumable: false, image_id: null }],
    start_items: [],
    cast: [member('mina', MINA, true), member('jun', JUN, false)],
    events: [{ id: 'rain', name: '소나기', when: { match: 'all', items: [] }, repeat: false, scene: { text: '비가 온다.', cast: [], image_id: null, collectible: false }, on_open: [], choices: [] }],
    endings: [],
    lorebooks: [],
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StoryWorldDetail;
}

function signedIn(initial = world()) {
  let current = initial;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${WORLDS}/${ID}`]: () => json(200, current),
    [`PATCH ${WORLDS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Partial<StoryWorldDetail>) };
      return json(200, current);
    },
    [`GET ${WORLDS}/${ID}/publish-check`]: () => json(200, { ready: false, problems: ['ending_missing'], warnings: [], removed: [] }),
    [`GET ${WORLDS}/${ID}/versions`]: () => json(200, []),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/characters': () =>
      json(200, {
        items: [
          { id: MINA, name: '미나', latest_version: 2, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
          { id: JUN, name: '준', latest_version: 1, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
        ],
        total: 2,
      }),
  });
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH').map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('이벤트 탭', () => {
  it('조건, 장면, 열릴 때의 효과, 선택지와 효과를 정해 저장하고, 차례를 바꾼다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}?tab=events`);

    const form = within(await screen.findByRole('form', { name: '이벤트' }));
    await userEvent.click(form.getByRole('button', { name: '이벤트 더하기' }));
    await userEvent.type(form.getByLabelText('이벤트 2의 이름'), '고백 전날');
    await userEvent.click(form.getByRole('button', { name: '고백 전날의 조건 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('고백 전날의 조건 1의 종류'), 'event_seen');
    await userEvent.selectOptions(form.getByLabelText('고백 전날의 조건 1의 대상'), 'rain');
    await userEvent.type(form.getByLabelText('고백 전날의 상황'), '미나가 망설인다.');
    await userEvent.click(await form.findByLabelText('고백 전날에 미나'));
    await userEvent.click(form.getByRole('button', { name: '고백 전날이(가) 열릴 때의 효과 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('고백 전날이(가) 열릴 때의 효과 1의 대상'), 'mina');
    await userEvent.click(form.getByRole('button', { name: '고백 전날의 선택지 더하기' }));
    await userEvent.type(form.getByLabelText('고백 전날의 선택지 1의 글'), '꽃을 준다');
    await userEvent.click(form.getByRole('button', { name: '고백 전날의 선택지 1의 효과 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('고백 전날의 선택지 1의 효과 1의 종류'), 'take_item');
    await userEvent.selectOptions(form.getByLabelText('고백 전날의 선택지 1의 효과 1의 대상'), 'flower');
    await userEvent.click(form.getByRole('button', { name: '고백 전날을(를) 위로' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const body = patches(seen)[0] as { events: Record<string, unknown>[] };
    expect(body.events.map((event) => event.name)).toEqual(['고백 전날', '소나기']);
    expect(body.events[0]).toMatchObject({
      when: { match: 'all', items: [{ kind: 'event_seen', target: 'rain', count: 1 }] },
      repeat: false,
      scene: { text: '미나가 망설인다.', cast: ['mina'], image_id: null, collectible: false },
      on_open: [{ kind: 'affection', target: 'mina', amount: 5 }],
      choices: [{ text: '꽃을 준다', effects: [{ kind: 'take_item', target: 'flower', amount: 1 }] }],
    });
  });
});

describe('엔딩 탭', () => {
  it('고백의 대상은 고백할 수 있는 인물만이고, 기한은 대상을 보내지 않는다. 막는 것에서 엔딩 탭으로 간다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}`);

    const problems = within(await screen.findByRole('list', { name: '고칠 것' }));
    await userEvent.click(problems.getByRole('button', { name: '엔딩 탭으로' }));
    const form = within(screen.getByRole('form', { name: '엔딩' }));
    await userEvent.click(form.getByRole('button', { name: '엔딩 더하기' }));
    await userEvent.type(form.getByLabelText('엔딩 1의 이름'), '여름의 약속');
    const target = form.getByLabelText('여름의 약속의 시작의 대상');
    await within(target).findByRole('option', { name: '미나' });
    expect(within(target).queryByRole('option', { name: '준' })).toBeNull();
    await userEvent.selectOptions(target, 'mina');
    await userEvent.type(form.getByLabelText('여름의 약속의 상황'), '불꽃놀이 아래에서.');
    await userEvent.click(form.getByRole('button', { name: '엔딩 더하기' }));
    await userEvent.type(form.getByLabelText('엔딩 2의 이름'), '혼자 남은 여름');
    await userEvent.selectOptions(form.getByLabelText('혼자 남은 여름의 시작'), 'deadline');
    await userEvent.type(form.getByLabelText('혼자 남은 여름의 상황'), '방학이 끝났다.');
    await userEvent.type(form.getByLabelText('혼자 남은 여름의 힌트(선택)'), '아무에게도 마음을 열지 않는다');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const body = patches(seen)[0] as { endings: Record<string, unknown>[] };
    expect(body.endings.map((ending) => ending.trigger)).toEqual([{ kind: 'confess_success', target: 'mina' }, { kind: 'deadline' }]);
    expect(body.endings[1]).toMatchObject({ name: '혼자 남은 여름', unlock: true, hint: '아무에게도 마음을 열지 않는다' });
  });
});

describe('순수한 함수', () => {
  const choices: ConditionChoices = {
    places: [{ id: 'park', name: '공원' }],
    items: [{ id: 'flower', name: '꽃' }],
    cast: [{ id: 'mina', name: '미나', stages: ['친구'] }],
    slots: [],
    events: [{ id: 'rain', name: '소나기' }],
  };

  it('효과: 종류를 바꾸면 크기를 그 종류의 처음 값으로, 대상의 종류가 같으면 대상을 남긴다. 크기를 쓰지 않으면 보내지 않는다', () => {
    let effects = changeEffect(addEffect([]), 0, { target: 'mina' });
    expect(effectsHints(changeEffect(effects, 0, { amount: '0' }), choices)[0]).toBe('0 은 호감도를 바꾸지 않습니다.');
    effects = changeEffect(effects, 0, { kind: 'accompany_start' });
    expect(effects[0]).toEqual({ kind: 'accompany_start', target: 'mina', amount: '' });
    expect(toEffects(effects)).toEqual([{ kind: 'accompany_start', target: 'mina' }]);
    effects = changeEffect(effects, 0, { kind: 'give_item' });
    expect(effects[0]).toEqual({ kind: 'give_item', target: '', amount: '1' });
    expect(effectsHints(changeEffect(effects, 0, { target: 'flower', amount: '100' }), choices)[0]).toMatch(/1~99/);
    expect(toEffects(changeEffect(changeEffect(effects, 0, { kind: 'move_to' }), 0, { target: 'park' }))).toEqual([{ kind: 'move_to', target: 'park' }]);
  });

  it('장면: 인물 넷까지, 일러스트를 떼면 해금도 끈다, 상황은 필수', () => {
    let scene = EMPTY_SCENE;
    for (const id of ['a', 'b', 'c', 'd', 'e']) scene = toggleSceneCast(scene, id);
    expect(scene.cast).toEqual(['a', 'b', 'c', 'd']);
    scene = { ...setSceneImage(scene, 'img'), collectible: true };
    expect(setSceneImage(scene, null).collectible).toBe(false);
    expect(sceneHint({ ...scene, text: ' ' }, [])).toBe('장면의 상황을 적어 주세요.');
    expect(sceneHint({ ...scene, text: '비' }, [])).toMatch(/없는 인물/);
    expect(toScene({ ...EMPTY_SCENE, text: ' 비 ', collectible: true })).toEqual({ text: '비', cast: [], image_id: null, collectible: false });
  });

  it('이벤트와 엔딩: 차례, 시작을 바꾸면 대상을 비운다, 대상의 고를 거리', () => {
    const events = addEvent(addEvent([], 'e1'), 'e2');
    expect(moveEventUp(events, 1).map((event) => event.id)).toEqual(['e2', 'e1']);
    expect(moveEventUp(events, 0)).toBe(events);
    let endings = addEnding([], 'n1');
    endings = changeEnding(endings, 'n1', (ending) => ({ ...ending, target: 'mina' }));
    expect(changeEnding(endings, 'n1', (ending) => ({ ...ending, trigger: 'event' }))[0]?.target).toBe('');
    expect(triggerTargets('deadline', choices.cast, choices.events)).toEqual([]);
    expect(triggerTargets('event', choices.cast, choices.events)).toEqual(choices.events);
    expect(toEndingsBody(changeEnding(endings, 'n1', (ending) => ({ ...ending, trigger: 'deadline' }))).endings?.[0]?.trigger).toEqual({ kind: 'deadline' });
  });
});
