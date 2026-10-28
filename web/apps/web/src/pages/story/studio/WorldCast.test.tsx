// web/apps/web/src/pages/story/studio/WorldCast.test.tsx
// 세계관의 인물 탭(D7). 게시한 캐릭터만 고르고, 같은 캐릭터를 두 번 넣지 못하며, 기본 장소·일정과 조건·호감도의 단계와 선물·고백·보이기를
// 저장한 모양 그대로 보낸다. 조건은 종류를 바꾸면 대상을 비우고, 호감도 조건은 그 인물의 단계에서 고른다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { addMember, castChoices, castDraft, castHints, hasCastHints, newCastDraft, toCastBody, toggleConfession, togglePanelField, togglePanelOverride } from './castForm';
import { addCondition, changeCondition, conditionsHints, toConditions, valueChoices, type ConditionChoices } from './conditionsForm';

const WORLDS = '/api/v1/asset/worlds';
const ID = '00000000-0000-4000-8000-0000000000f8';
const MINA = '00000000-0000-4000-8000-0000000000c8';
const JUN = '00000000-0000-4000-8000-0000000000c9';
const AT = '2026-10-28T00:00:00Z';

function world(extra: Partial<StoryWorldDetail> = {}): StoryWorldDetail {
  return {
    id: ID,
    name: '여름 학교',
    intro_html: '',
    tags: [],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [
      { id: 'morning', name: '아침', start_hour: 7 },
      { id: 'night', name: '밤', start_hour: 21 },
    ],
    start_slot: 'morning',
    deadline_days: null,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro', 'age', 'gender', 'affection'] },
    places: [
      { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
      { id: 'cafe', name: '카페', description: '', image_id: null, backgrounds: {} },
    ],
    paths: [],
    start_place: 'park',
    items: [{ id: 'flower', name: '꽃', description: '', consumable: false, image_id: null }],
    start_items: [],
    cast: [],
    events: [{ id: 'rain', name: '소나기', when: { match: 'all', items: [] }, repeat: false, scene: { text: '비', cast: [], image_id: null, collectible: false }, on_open: [], choices: [] }],
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
    [`GET ${WORLDS}/${ID}/publish-check`]: () => json(200, { ready: false, problems: [], warnings: [], removed: [] }),
    [`GET ${WORLDS}/${ID}/versions`]: () => json(200, []),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/characters': () =>
      json(200, {
        items: [
          { id: MINA, name: '미나', latest_version: 2, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
          { id: JUN, name: '준', latest_version: 1, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
          { id: '00000000-0000-4000-8000-0000000000ca', name: '초안만', latest_version: null, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
        ],
        total: 3,
      }),
  });
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH').map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('인물 탭', () => {
  it('인물을 더해 캐릭터, 기본 장소, 일정과 조건, 단계와 선물, 고백, 지도의 단계를 정해 저장한다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}?tab=cast`);

    const form = within(await screen.findByRole('form', { name: '인물' }));
    await userEvent.click(form.getByRole('button', { name: '인물 더하기' }));
    const pick = form.getByLabelText('인물 1의 캐릭터');
    await within(pick).findByRole('option', { name: '미나' });
    expect(within(pick).queryByRole('option', { name: '초안만' })).toBeNull();
    await userEvent.selectOptions(pick, MINA);

    await userEvent.selectOptions(form.getByLabelText('미나의 기본 장소'), 'park');
    await userEvent.click(form.getByRole('button', { name: '미나의 단계 더하기' }));
    await userEvent.type(form.getByLabelText('미나의 단계 2의 이름'), '호감');
    await userEvent.click(form.getByRole('button', { name: '미나의 일정 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('미나의 일정 1의 시간대'), 'night');
    await userEvent.selectOptions(form.getByLabelText('미나의 일정 1의 장소'), 'cafe');
    await userEvent.click(form.getByRole('button', { name: '미나의 일정 1의 조건 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('미나의 일정 1의 조건 1의 종류'), 'affection_at_least');
    await userEvent.selectOptions(form.getByLabelText('미나의 일정 1의 조건 1의 대상'), (within(form.getByLabelText('미나의 일정 1의 조건 1의 대상')).getByRole('option', { name: '미나' }) as HTMLOptionElement).value);
    expect(form.getByText('단계를 골라 주세요.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(form.getByLabelText('미나의 일정 1의 조건 1의 단계'), '호감');

    await userEvent.click(form.getByRole('button', { name: '미나의 선물 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('미나의 선물 1의 물건'), 'flower');
    await userEvent.click(form.getByLabelText('미나에게 고백할 수 있다'));
    await userEvent.selectOptions(form.getByLabelText('미나의 지도'), 'stage');
    await userEvent.selectOptions(form.getByLabelText('미나이(가) 지도에 보이는 단계'), '호감');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const body = patches(seen)[0] as { cast: Record<string, unknown>[] };
    const member = body.cast[0] as Record<string, unknown> & { id: string };
    expect(member).toMatchObject({
      character_id: MINA,
      home: 'park',
      schedule: [{ slot: 'night', place: 'cafe', when: { match: 'all', items: [{ kind: 'affection_at_least', target: member.id, value: '호감', count: 1 }] } }],
      affection: { display: 'stage', start: 0, stages: [{ name: '처음', at: 0 }, { name: '호감', at: 10 }], gifts: [{ item: 'flower', change: 5, once: false }] },
      confession: { stage: '호감', when: { match: 'all', items: [] }, on_fail: 'continue', fail_drop: 10, cooldown_days: 1 },
      reveal: null,
      map: 'stage',
      map_stage: '호감',
      panel: null,
    });
  });

  it('같은 캐릭터를 두 번 넣으면 막는다', async () => {
    signedIn(world({ cast: [toCastBody([{ ...newCastDraft('cast-a'), characterId: MINA }]).cast?.[0] as StoryWorldDetail['cast'][number]] }));
    renderApp(`/story/studio/worlds/${ID}?tab=cast`);

    const form = within(await screen.findByRole('form', { name: '인물' }));
    await userEvent.click(form.getByRole('button', { name: '인물 더하기' }));
    await within(form.getByLabelText('인물 2의 캐릭터')).findByRole('option', { name: '미나' });
    await userEvent.selectOptions(form.getByLabelText('인물 2의 캐릭터'), MINA);
    expect(form.getByText('같은 캐릭터가 이미 다른 인물입니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
  });
});

describe('순수한 함수', () => {
  const choices: ConditionChoices = {
    places: [{ id: 'park', name: '공원' }],
    items: [{ id: 'flower', name: '꽃' }],
    cast: [{ id: 'mina', name: '미나', stages: ['친구', '호감'] }],
    slots: [{ id: 'night', name: '밤' }],
    events: [{ id: 'rain', name: '소나기' }],
  };

  it('조건: 종류를 바꾸면 비우고, 인물을 바꾸면 단계를 비우며, 쓰지 않는 칸은 보내지 않는다', () => {
    let draft = addCondition({ match: 'any', items: [] });
    draft = changeCondition(draft, 0, { target: 'park' });
    expect(toConditions(draft)).toEqual({ match: 'any', items: [{ kind: 'reach_place', target: 'park', count: 1 }] });
    draft = changeCondition(draft, 0, { kind: 'affection_below' });
    expect(draft.items[0]).toEqual({ kind: 'affection_below', target: '', value: '', count: '1' });
    draft = changeCondition(changeCondition(draft, 0, { target: 'mina' }), 0, { value: '호감' });
    expect(valueChoices(draft.items[0] as never, choices).map((choice) => choice.id)).toEqual(['친구', '호감']);
    expect(changeCondition(draft, 0, { target: 'jun' }).items[0]?.value).toBe('');
    draft = changeCondition(draft, 0, { kind: 'day_at_least' });
    expect(conditionsHints(changeCondition(draft, 0, { count: '0' }), choices)[0]).toMatch(/1~365/);
    expect(toConditions(changeCondition(draft, 0, { count: '3' })).items).toEqual([{ kind: 'day_at_least', count: 3 }]);
    expect(conditionsHints(changeCondition(changeCondition(draft, 0, { kind: 'event_seen' }), 0, { target: 'gone' }), choices)[0]).toBe('없는 대상입니다. 다시 골라 주세요.');
  });

  it('인물: 고백을 켜면 마지막 단계, 창 항목의 덮어쓰기, 고를 거리, 문제', () => {
    const member = { ...newCastDraft('cast-a'), characterId: 'c1', stages: [{ name: '처음', at: '0' }, { name: '사랑', at: '70' }] };
    expect(toggleConfession(member).confession?.stage).toBe('사랑');
    expect(toggleConfession(toggleConfession(member)).confession).toBeNull();
    const panel = togglePanelOverride(member, ['intro', 'affection']);
    expect(panel.panel).toEqual(['intro', 'affection']);
    expect(togglePanelField(panel, 'age').panel).toEqual(['intro', 'age', 'affection']);
    const cast = addMember([member], 'cast-b');
    const picked = castChoices(world(), cast, [{ id: 'c1', name: '미나' }]);
    expect(picked.cast.map((entry) => [entry.name, entry.stages])).toEqual([
      ['미나', ['처음', '사랑']],
      ['', ['처음']],
    ]);
    expect(picked.events).toEqual([{ id: 'rain', name: '소나기' }]);
    const hints = castHints(cast, picked, [{ id: 'c1', name: '미나' }]);
    expect(hints['cast-b']?.character).toBe('캐릭터를 골라 주세요.');
    expect(hasCastHints(hints)).toBe(true);
    const bad = { ...member, stages: [{ name: '처음', at: '5' }], start: '101' };
    expect(castHints([bad], picked, [{ id: 'c1', name: '미나' }])['cast-a']).toMatchObject({ start: expect.stringMatching(/0~100/), stages: { 0: '첫 단계는 0 에서 시작합니다.' } });
    const round = castDraft(toCastBody([toggleConfession(member)]).cast?.[0] as StoryWorldDetail['cast'][number]);
    expect(round.confession).toMatchObject({ stage: '사랑', onFail: 'continue', failDrop: '10', cooldownDays: '1' });
  });
});
