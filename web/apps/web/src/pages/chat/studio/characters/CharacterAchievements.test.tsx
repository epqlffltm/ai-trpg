// web/apps/web/src/pages/chat/studio/characters/CharacterAchievements.test.tsx
// 캐릭터 고치기(C6)의 업적 탭(docs/architecture/achievements.md 의 "chat"). 업적을 더해 이름, 받는 법, 숨김, 맞추는 법, 조건을 적어 저장한다.
// 조건의 대상은 저장한 장소, 물건, 이벤트 씬, 호감도 단계에서 고르고, 종류를 바꾸면 대상과 수를 비운다. 칸이 틀리면 저장을 막는다.
// 게시 점검의 achievement_target_missing 은 업적 탭을 가리킨다. 입력의 순수한 함수(achievementsForm.ts).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { AssetCharacterDetail } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import {
  ACHIEVEMENT_CONDITIONS_MAX,
  addAchievement,
  addCondition,
  achievementDraft,
  achievementsHints,
  changeCondition,
  conditionChoices,
  EMPTY_CONDITION,
  hasAchievementsHints,
  moveAchievementUp,
  toCondition,
  type AchievementDraft,
} from './achievementsForm';
import { problemLine } from './publishProblems';

const CHARACTERS = '/api/v1/asset/characters';
const ID = '00000000-0000-4000-8000-0000000000e9';
const CAFE = { id: 'cafe', name: '카페', description: '', image_id: null, backgrounds: {} };
const COOKIE = { id: 'cookie', name: '쿠키', description: '', kind: 'thing', consumable: true, giftable: true, image_id: null };
const SCENE = { id: 'confess', title: '고백', image_id: '00000000-0000-4000-8000-00000000b009', description: '', collectible: true, when: { kind: 'reach_place', target: 'cafe' } };
const AFFECTION = { display: 'number', start: 0, model_step: 3, stages: [{ name: '처음', at: 0 }, { name: '연인', at: 80 }], rules: [] };
const SAVED = {
  id: 'regular',
  name: '단골',
  description: '카페에 갔다',
  hidden: false,
  image_id: null,
  when: { match: 'all', items: [{ kind: 'visited_place', target: 'cafe', value: null, count: 1 }] },
};

function character(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    name: '세라',
    age: '',
    gender: '',
    genre: 'romance',
    tags: [],
    rating: 'all',
    visibility: 'private',
    intro_html: '',
    greeting: '',
    speech_examples: '',
    starts: [{ title: '비', situation: '비가 온다.', hour: 12 }],
    places: [CAFE],
    paths: [],
    start_place: 'cafe',
    items: [COOKIE],
    start_items: [],
    affection: AFFECTION,
    sprites: [],
    event_scenes: [SCENE],
    lorebooks: [],
    shortcuts: [],
    achievements: [],
    image_id: null,
    hidden_at: null,
    latest_version: null,
    published_at: null,
    created_at: '2026-11-09T00:00:00Z',
    updated_at: '2026-11-09T00:00:00Z',
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(initial = character(), problems: string[] = [], routes: Routes = {}) {
  let current = initial;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${CHARACTERS}`]: () => json(200, { items: [], total: 0 }),
    [`GET ${CHARACTERS}/${ID}`]: () => json(200, current),
    [`PATCH ${CHARACTERS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${CHARACTERS}/${ID}/publish-check`]: () => json(200, { ready: problems.length === 0, problems, removed: [] }),
    [`GET ${CHARACTERS}/${ID}/versions`]: () => json(200, []),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    ...routes,
  });
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url.split('?')[0] === `${CHARACTERS}/${ID}`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캐릭터의 업적 탭', () => {
  it('업적을 더해 조건 둘을 적고 저장한다. 종류마다 쓰는 칸만 보낸다', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee');
    const { seen } = signedIn();
    renderApp(`/chat/studio/characters/${ID}?tab=achievements`);

    const form = await screen.findByRole('form', { name: '업적' });
    expect(within(form).getByText('아직 업적이 없습니다.')).toBeInTheDocument();
    await userEvent.click(within(form).getByRole('button', { name: '업적 더하기' }));
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    expect(within(form).getByText('이름을 적어 주세요.')).toBeInTheDocument();
    expect(within(form).getByText('대상을 골라 주세요.')).toBeInTheDocument();

    await userEvent.type(within(form).getByLabelText('업적 1의 이름'), '수다쟁이');
    const label = '수다쟁이';
    await userEvent.type(within(form).getByLabelText(`${label}의 받는 법(선택)`), '많이 이야기했다');
    await userEvent.click(within(form).getByLabelText(`${label}: 숨긴 업적`));
    await userEvent.selectOptions(within(form).getByLabelText(`${label}의 조건 1의 종류`), 'messages_at_least');
    expect(within(form).queryByLabelText(`${label}의 조건 1의 대상`)).toBeNull();
    const count = within(form).getByLabelText(`${label}의 조건 1의 수(1~9999)`);
    await userEvent.clear(count);
    await userEvent.type(count, '0');
    expect(within(form).getByText('수는 1~9999 사이의 정수로 적어 주세요.')).toBeInTheDocument();
    await userEvent.clear(count);
    await userEvent.type(count, '30');

    await userEvent.click(within(form).getByRole('button', { name: `${label}에 조건 더하기` }));
    await userEvent.selectOptions(within(form).getByLabelText(`${label}의 조건 2의 종류`), 'hold_item');
    await userEvent.selectOptions(within(form).getByLabelText(`${label}의 조건 2의 대상`), '쿠키');
    const held = within(form).getByLabelText(`${label}의 조건 2의 수(1~9999)`);
    await userEvent.clear(held);
    await userEvent.type(held, '3');
    await userEvent.selectOptions(within(form).getByLabelText(`${label}의 맞추는 법`), 'any');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)).toEqual([
      {
        achievements: [
          {
            id: 'achievement-aaaaaaaa',
            name: '수다쟁이',
            description: '많이 이야기했다',
            hidden: true,
            image_id: null,
            when: {
              match: 'any',
              items: [
                { kind: 'messages_at_least', count: 30 },
                { kind: 'hold_item', target: 'cookie', count: 3 },
              ],
            },
          },
        ],
      },
    ]);
  });

  it('저장한 업적을 읽고, 대상은 저장한 이벤트 씬과 호감도 단계에서 고른다. 조건을 지우면 저장을 막는다', async () => {
    const { seen } = signedIn(character({ achievements: [SAVED] }));
    renderApp(`/chat/studio/characters/${ID}?tab=achievements`);

    const form = await screen.findByRole('form', { name: '업적' });
    expect(within(form).getByLabelText('단골의 이름')).toHaveValue('단골');
    expect(within(form).getByLabelText('단골의 조건 1의 대상')).toHaveValue('cafe');
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 종류'), 'scene_seen');
    expect(within(form).getByLabelText('단골의 조건 1의 대상')).toHaveValue('');
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 대상'), '고백');
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 종류'), 'affection_stage');
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 대상'), '연인');

    await userEvent.click(within(form).getByRole('button', { name: '단골의 조건 1 지우기' }));
    expect(within(form).getByText('받는 조건을 하나 이상 적어 주세요.')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(within(form).getByRole('button', { name: '단골에 조건 더하기' }));
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 종류'), 'affection_stage');
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 대상'), '연인');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)).toEqual([
      { achievements: [{ ...SAVED, when: { match: 'all', items: [{ kind: 'affection_stage', value: '연인', count: 1 }] } }] },
    ]);
  });

  it('저장할 것이 없으면 대상 칸에 어디서 더하는지 알린다', async () => {
    signedIn(character({ achievements: [SAVED], places: [], items: [], event_scenes: [], affection: null }));
    renderApp(`/chat/studio/characters/${ID}?tab=achievements`);

    const form = await screen.findByRole('form', { name: '업적' });
    expect(within(form).getByText('저장한 장소가 없습니다. 지도 탭에서 먼저 더해 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText('단골의 조건 1의 종류'), 'scene_seen');
    expect(within(form).getByText('저장한 이벤트 씬이 없습니다. 이벤트 씬 탭에서 먼저 더해 주세요.')).toBeInTheDocument();
  });

  it('게시 점검의 업적 문제는 업적 탭으로 간다', async () => {
    signedIn(character({ achievements: [SAVED] }), ['achievement_target_missing']);
    renderApp(`/chat/studio/characters/${ID}`);

    const problems = await screen.findByRole('list', { name: '고칠 것' });
    expect(within(problems).getByText('업적의 조건이 없는 장소, 물건, 이벤트 씬, 호감도 단계를 가리킵니다.')).toBeInTheDocument();
    await userEvent.click(within(problems).getByRole('button', { name: '업적 탭으로' }));
    expect(screen.getByRole('tab', { name: '업적' })).toHaveAttribute('aria-selected', 'true');
    expect(problemLine('achievement_target_missing').section).toBe('achievements');
  });
});

describe('업적 탭의 입력', () => {
  const draft = (): AchievementDraft => ({ id: 'a', name: '이름', description: '', hidden: false, imageId: null, match: 'all', items: [EMPTY_CONDITION] });

  it('조건의 종류를 바꾸면 대상과 수를 비우고, 같은 종류의 바꿈은 그대로 둔다', () => {
    const picked = changeCondition(draft(), 0, { kind: 'hold_item' });
    const filled = changeCondition(changeCondition(picked, 0, { target: 'cookie' }), 0, { count: '4' });
    expect(filled.items[0]).toEqual({ kind: 'hold_item', target: 'cookie', value: '', count: '4' });
    expect(changeCondition(filled, 0, { kind: 'hold_item', count: '5' }).items[0]).toEqual({ kind: 'hold_item', target: 'cookie', value: '', count: '5' });
    expect(changeCondition(filled, 0, { kind: 'received_item' }).items[0]).toEqual({ ...EMPTY_CONDITION, kind: 'received_item' });
  });

  it('종류마다 쓰는 칸만 보내고 count 는 쓰지 않으면 1 이다', () => {
    expect(toCondition({ kind: 'visited_place', target: 'cafe', value: 'x', count: '7' })).toEqual({ kind: 'visited_place', target: 'cafe', count: 1 });
    expect(toCondition({ kind: 'affection_stage', target: 'x', value: '연인', count: '7' })).toEqual({ kind: 'affection_stage', value: '연인', count: 1 });
    expect(toCondition({ kind: 'messages_at_least', target: 'x', value: 'y', count: ' 12 ' })).toEqual({ kind: 'messages_at_least', count: 12 });
  });

  it('수는 1~9999 의 정수다. 조건은 5개, 업적은 50개까지 더한다', () => {
    const counts = ['1', '9999', '0', '10000', '1.5', '-3', 'abc', ''];
    const hinted = counts.map((count) => Object.keys(achievementsHints([{ ...draft(), items: [{ kind: 'messages_at_least', target: '', value: '', count }] }]).a?.conditions ?? {}).length);
    expect(hinted).toEqual([0, 0, 1, 1, 1, 1, 1, 1]);
    let full = draft();
    for (let index = 0; index < 10; index += 1) full = addCondition(full);
    expect(full.items).toHaveLength(ACHIEVEMENT_CONDITIONS_MAX);
    let many: AchievementDraft[] = [];
    for (let index = 0; index < 60; index += 1) many = addAchievement(many, `a${index}`);
    expect(many).toHaveLength(50);
    expect(moveAchievementUp(many, 1).slice(0, 2).map((one) => one.id)).toEqual(['a1', 'a0']);
    expect(moveAchievementUp(many, 0)).toBe(many);
  });

  it('이름과 받는 법의 길이, 조건이 없음을 알린다', () => {
    const hints = achievementsHints([{ ...draft(), name: ' ', description: '가'.repeat(201), items: [] }]);
    expect(hints.a).toEqual({ name: '이름을 적어 주세요.', description: '받는 법은 200자까지입니다.', when: '받는 조건을 하나 이상 적어 주세요.', conditions: {} });
    expect(achievementsHints([{ ...draft(), name: '가'.repeat(41) }]).a?.name).toBe('이름은 40자까지입니다.');
    expect(hasAchievementsHints(achievementsHints([{ ...draft(), items: [{ kind: 'visited_place', target: 'cafe', value: '', count: '1' }] }]))).toBe(false);
    const stage = (value: string) => achievementsHints([{ ...draft(), items: [{ kind: 'affection_stage', target: '', value, count: '1' }] }]).a?.conditions;
    expect(stage('')).toEqual({ 0: '호감도의 단계를 골라 주세요.' });
    expect(stage('연인')).toEqual({});
  });

  it('저장한 업적을 입력으로 읽고, 고를 대상은 종류마다 다르다', () => {
    expect(achievementDraft(SAVED as never)).toEqual({ id: 'regular', name: '단골', description: '카페에 갔다', hidden: false, imageId: null, match: 'all', items: [{ kind: 'visited_place', target: 'cafe', value: '', count: '1' }] });
    const saved = character() as unknown as AssetCharacterDetail;
    expect(conditionChoices(saved, 'visited_place')).toEqual([{ value: 'cafe', label: '카페' }]);
    expect(conditionChoices(saved, 'received_item')).toEqual([{ value: 'cookie', label: '쿠키' }]);
    expect(conditionChoices(saved, 'hold_item')).toEqual([{ value: 'cookie', label: '쿠키' }]);
    expect(conditionChoices(saved, 'scene_seen')).toEqual([{ value: 'confess', label: '고백' }]);
    expect(conditionChoices(saved, 'affection_stage').map((choice) => choice.value)).toEqual(['처음', '연인']);
    expect(conditionChoices(saved, 'messages_at_least')).toEqual([]);
    expect(conditionChoices({ ...saved, affection: null }, 'affection_stage')).toEqual([]);
  });
});
