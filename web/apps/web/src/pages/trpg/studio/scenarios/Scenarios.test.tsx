// web/apps/web/src/pages/trpg/studio/scenarios/Scenarios.test.tsx
// 시나리오 조립의 뼈대(B9). 만들기 → 고치기 화면과 게시 점검, 점검에서 탭으로 가기, 재료와 스타팅의 저장 본문,
// 등급과 추천 모델의 실패, 게시와 판의 목록. 입력의 순수한 함수(재료 고르기, 스타팅, 시계, 모델 상태, 문제의 글).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME } from '../../../../test/tableFixtures';
import { basicsHints, modelStatusText, type BasicsDraft } from './basicsForm';
import { toggleId, toMaterialsBody, withChosen } from './materialsForm';
import { addOpening, moveOpeningUp, openingsHints, OPENINGS_MAX } from './openingsForm';
import { problemLine } from './publishProblems';
import { isTab, tabOf } from './scenarioTabs';

const GAME = '/api/v1/game';
const SCENARIOS = `${GAME}/scenarios`;
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';

const MODELS = {
  free: false,
  models: [
    { slug: 'glm-air', display_name: 'GLM Air', vendor: 'Z.ai', grade: 'basic', retires_on: null, options: [] },
    { slug: 'gemini-flash', display_name: 'Gemini Flash', vendor: 'Google', grade: 'standard', retires_on: null, options: [] },
  ],
};

function summary(id: string, title: string) {
  return { id, title, description: '', visibility: 'private', created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z' };
}

function scenario(extra: Record<string, unknown> = {}) {
  return scenarioDetail({
    ...extra,
  });
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/tables/narration-models`]: () => json(200, MODELS),
    [`GET ${GAME}/rulebooks`]: () => json(200, { items: [summary(RULEBOOK, '수도원 규칙')], total: 1 }),
    [`GET ${GAME}/worlds`]: () => json(200, { items: [], total: 0 }),
    [`GET ${GAME}/lorebooks`]: () => json(200, { items: [summary(LOREBOOK, '수도원 사람들')], total: 1 }),
    [`GET ${GAME}/bestiaries`]: () => json(200, { items: [], total: 0 }),
    [`GET ${SCENARIOS}/${ID}/versions`]: () => json(200, []),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === url);
}

async function panel(name: string) {
  return within(await screen.findByRole('tabpanel', { name }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('시나리오 만들기와 게시 점검', () => {
  it('제목과 추천 모델로 만들면 고치기로 가고, 점검의 문제에서 그 탭으로 간다', async () => {
    const { seen } = signedIn({
      [`POST ${SCENARIOS}`]: () => json(201, scenario()),
      [`GET ${SCENARIOS}/${ID}`]: () => json(200, scenario()),
      [`GET ${SCENARIOS}/${ID}/publish-check`]: () =>
        json(200, { ready: false, problems: ['rulebook_missing', 'opening_missing', 'unique_monster_repeated'] }),
    });
    renderApp('/trpg/studio/scenarios/new');

    const form = within(await screen.findByRole('form', { name: '시나리오' }));
    await userEvent.type(form.getByLabelText('제목'), '비 내리는 수도원');
    expect(form.getByRole('button', { name: '만들기' })).toBeDisabled();
    await form.findByRole('option', { name: /GLM Air/ });
    await userEvent.selectOptions(form.getByLabelText('추천 서술 모델'), 'glm-air');
    await userEvent.click(form.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '비 내리는 수도원', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', SCENARIOS)[0]?.body).toEqual({ title: '비 내리는 수도원', description: '', narration_model: 'glm-air' });

    const check = within(await screen.findByRole('list', { name: '고칠 것' }));
    expect(check.getByText('룰북을 고르지 않았습니다.')).toBeInTheDocument();
    expect(check.getByText('(몬스터: 화면 준비 중)')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '기본' })).toHaveAttribute('aria-selected', 'true');

    await userEvent.click(check.getByRole('button', { name: '재료 탭으로' }));
    expect(screen.getByRole('tab', { name: '재료' })).toHaveAttribute('aria-selected', 'true');
    expect((await panel('재료')).getByLabelText('룰북')).toBeVisible();
  });
});

describe('탭마다 저장', () => {
  it('재료는 그 탭의 칸만 보내고, 저장하면 점검을 다시 읽는다', async () => {
    const { seen } = signedIn({
      [`GET ${SCENARIOS}/${ID}`]: () => json(200, scenario()),
      [`GET ${SCENARIOS}/${ID}/publish-check`]: () => json(200, { ready: false, problems: ['rulebook_missing'] }),
      [`PATCH ${SCENARIOS}/${ID}`]: (request) => json(200, scenario(request.body as Record<string, unknown>)),
    });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=materials`);

    const materials = await panel('재료');
    await materials.findByRole('option', { name: '수도원 규칙' });
    await userEvent.selectOptions(materials.getByLabelText('룰북'), RULEBOOK);
    await userEvent.click(await materials.findByRole('checkbox', { name: '수도원 사람들' }));
    expect(materials.getByText('(1 / 10)')).toBeInTheDocument();
    await userEvent.click(materials.getByRole('button', { name: '저장' }));

    expect(await materials.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `${SCENARIOS}/${ID}`)[0]?.body).toEqual({
      rulebook_id: RULEBOOK,
      world_id: null,
      lorebook_ids: [LOREBOOK],
      bestiary_ids: [],
    });
    await vi.waitFor(() => expect(sent(seen, 'GET', `${SCENARIOS}/${ID}/publish-check`)).toHaveLength(2));
  });

  it('스타팅을 더하고 앞으로 옮기고 지운 차례대로 보낸다. 빈 스타팅은 보내지 않는다', async () => {
    const { seen } = signedIn({
      [`GET ${SCENARIOS}/${ID}`]: () => json(200, scenario({ openings: ['종이 울린다.'] })),
      [`GET ${SCENARIOS}/${ID}/publish-check`]: () => json(200, { ready: true, problems: [] }),
      [`PATCH ${SCENARIOS}/${ID}`]: (request) => json(200, scenario(request.body as Record<string, unknown>)),
    });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=openings`);

    const openings = await panel('스타팅');
    await openings.findByRole('textbox', { name: '스타팅 1' });
    await userEvent.click(openings.getByRole('button', { name: '스타팅 더하기' }));
    expect(openings.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(openings.getByRole('textbox', { name: '스타팅 2' }), '문이 열린다.');
    await userEvent.click(openings.getByRole('button', { name: '스타팅 더하기' }));
    await userEvent.type(openings.getByRole('textbox', { name: '스타팅 3' }), '비가 그친다.');
    await userEvent.click(openings.getByRole('button', { name: '스타팅 2 앞으로' }));
    await userEvent.click(openings.getByRole('button', { name: '스타팅 3 지우기' }));
    await userEvent.click(openings.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(sent(seen, 'PATCH', `${SCENARIOS}/${ID}`)[0]?.body).toEqual({ openings: ['문이 열린다.', '종이 울린다.'] }));
  });

  it('성인 확인 없이 성인용으로 저장하면 등급 칸에, 서비스하지 않는 모델이면 모델 칸에 알린다', async () => {
    let answer = json(403, { detail: '성인 인증을 한 사람만 이용할 수 있습니다.', code: 'adult_content_required' });
    signedIn({
      [`GET ${SCENARIOS}/${ID}`]: () =>
        json(200, scenario({ narration_model_status: { state: 'retiring', retires_on: '2026-12-01', replacement: 'gemini-flash' } })),
      [`GET ${SCENARIOS}/${ID}/publish-check`]: () => json(200, { ready: true, problems: [] }),
      [`PATCH ${SCENARIOS}/${ID}`]: () => answer,
    });
    renderApp(`/trpg/studio/scenarios/${ID}`);

    const basics = await panel('기본');
    expect(await basics.findByText('추천 서술 모델이 12월 1일에 서비스를 마칩니다. 다른 모델로 바꿔 두세요.')).toBeInTheDocument();
    await userEvent.selectOptions(basics.getByLabelText('등급'), 'adult');
    await userEvent.click(basics.getByRole('button', { name: '저장' }));
    expect(await basics.findAllByText('성인용은 본인인증으로 성인 확인을 한 사람만 고를 수 있습니다.')).toHaveLength(2);

    answer = json(422, { detail: '서비스 중인 모델이 아닙니다.', field: 'narration_model', reason: 'not_offered' });
    await userEvent.selectOptions(basics.getByLabelText('등급'), 'all');
    await userEvent.click(basics.getByRole('button', { name: '저장' }));
    expect(await basics.findAllByText('지금 서비스하지 않는 모델입니다. 추천 서술 모델을 다시 골라 주세요.')).toHaveLength(2);
  });
});

describe('게시', () => {
  it('점검을 통과하면 게시하고 판의 목록을 다시 읽는다. 문제가 있으면 게시를 끈다', async () => {
    let ready = true;
    let versions: unknown[] = [];
    const { seen } = signedIn({
      [`GET ${SCENARIOS}/${ID}`]: () => json(200, scenario()),
      [`GET ${SCENARIOS}/${ID}/publish-check`]: () => json(200, ready ? { ready: true, problems: [] } : { ready: false, problems: ['opening_missing'] }),
      [`GET ${SCENARIOS}/${ID}/versions`]: () => json(200, versions),
      [`POST ${SCENARIOS}/${ID}/versions`]: (request) => {
        versions = [{ id: 'v1', number: 1, note: (request.body as { note: string }).note, created_at: '2026-10-23T00:00:00Z' }];
        ready = false;
        return json(201, { ...(versions[0] as object), snapshot: {} });
      },
    });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=publish`);

    const publish = await panel('게시');
    expect(await screen.findByText('지금 게시할 수 있습니다.')).toBeInTheDocument();
    expect(await publish.findByText('아직 낸 판이 없습니다.')).toBeInTheDocument();
    await userEvent.type(publish.getByLabelText('바뀐 것(선택)'), '첫 판');
    await userEvent.click(publish.getByRole('button', { name: '게시' }));

    expect(await publish.findByText('1판을 게시했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', `${SCENARIOS}/${ID}/versions`)[0]?.body).toEqual({ note: '첫 판' });
    expect(await within(publish.getByRole('list', { name: '판' })).findByText('첫 판')).toBeInTheDocument();
    expect(await screen.findByText('스타팅이 하나도 없습니다.')).toBeInTheDocument();
    expect(publish.getByRole('button', { name: '게시' })).toBeDisabled();
  });
});

describe('입력', () => {
  it('재료: 넣고 빼고, 가득 차면 더 넣지 않는다. 비운 룰북은 null 로 뗀다. 목록 밖의 것도 남긴다', () => {
    expect(toggleId(['a'], 'b', 2)).toEqual(['a', 'b']);
    expect(toggleId(['a', 'b'], 'c', 2)).toEqual(['a', 'b']);
    expect(toggleId(['a', 'b'], 'a', 2)).toEqual(['b']);
    expect(toMaterialsBody({ rulebookId: '', worldId: 'w', lorebookIds: [], bestiaryIds: [] })).toMatchObject({ rulebook_id: null, world_id: 'w' });
    expect(withChosen([summary('a', '가')] as never, ['a', 'z'])).toEqual([
      { id: 'a', title: '가' },
      { id: 'z', title: null },
    ]);
  });

  it('스타팅: 공백뿐이면 알리고, 다섯 개까지, 맨 앞은 앞으로 옮기지 않는다', () => {
    expect(openingsHints(['  ', '문'])).toEqual({ 0: '비어 있습니다. 글을 쓰거나 이 스타팅을 지워 주세요.' });
    expect(openingsHints(['가'.repeat(2001)])[0]).toBe('스타팅 하나는 2000자까지입니다.');
    const full = Array.from({ length: OPENINGS_MAX }, () => '글');
    expect(addOpening(full)).toBe(full);
    expect(moveOpeningUp(['가', '나'], 0)).toEqual(['가', '나']);
    expect(moveOpeningUp(['가', '나', '다'], 2)).toEqual(['가', '다', '나']);
  });

  it('시계는 범위 안의 정수만, 추천 모델은 꼭 고른다', () => {
    const draft: BasicsDraft = {
      title: '수도원',
      description: '',
      rating: 'all',
      narrationModel: '',
      narrationStyle: 'classic',
      startDay: '0',
      startHour: '24',
      roundMinutes: '10.5',
    };
    expect(Object.keys(basicsHints(draft)).sort()).toEqual(['narration_model', 'round_minutes', 'start_day', 'start_hour']);
    expect(basicsHints({ ...draft, narrationModel: 'glm-air', startDay: '999', startHour: '0', roundMinutes: '10080' })).toEqual({});
  });

  it('모델의 상태, 문제의 글과 묶음, 탭', () => {
    const name = (slug: string) => (slug === 'gemini-flash' ? 'Gemini Flash' : slug);
    expect(modelStatusText({ state: 'ok', retires_on: null, replacement: null }, name)).toBeNull();
    expect(modelStatusText({ state: 'unavailable', retires_on: null, replacement: 'gemini-flash' }, name)).toBe(
      '추천 서술 모델을 지금 쓸 수 없습니다. 다른 모델을 골라 주세요. 지금 테이블을 열면 대신 쓰는 모델: Gemini Flash.',
    );
    expect(problemLine('cover_off_map')).toEqual({ text: '맵에 없는 장소에 커버가 있습니다.', section: 'map' });
    expect(problemLine('something_new')).toEqual({ text: 'something_new', section: null });
    expect(isTab('monsters')).toBe(false);
    expect(tabOf('openings')).toBe('openings');
    expect(tabOf('nope')).toBe('basics');
  });
});
