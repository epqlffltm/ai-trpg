// web/apps/web/src/pages/trpg/studio/rulebooks/Rulebooks.test.tsx
// 룰북 화면(B9). 마이페이지에서 빈 목록으로, 세이브 방식으로 만들기(본문), 고치기에서 방어 규칙 바꾸기(PATCH 본문),
// 고치기에서 성장(레벨표, #286)을 켜고 줄을 더하기(PATCH 본문), 판정 방식을 d100 의 눈 ≤ 기량으로 바꾸기(#404),
// 쓰는 시나리오가 있어 지우지 못함(409), 지우고 목록으로, 없는 룰북을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME } from '../../../../test/tableFixtures';

const BASE = '/api/v1/game/rulebooks';
const ID = '00000000-0000-4000-8000-0000000000c1';

const ONE_OVER = { count: 1, style: 'over', shifts: {} };
const DIFFICULTIES = [{ key: 'medium', name: '보통', target: 15 }, { key: 'hard', name: '어려움', target: 20 }];

function rules(template: string, armor: unknown) {
  return { template, die: 20, roll: ONE_OVER, difficulties: DIFFICULTIES, armor, abilities: [{ key: 'heart', name: '마음' }], resources: [], narration: { tone: '영웅담', outcomes: [], avoid: [] } };
}

const TEMPLATES = {
  default: 'srd5',
  items: [
    { key: 'srd5', name: 'd20 판타지', summary: '모험의 기본', attribution: ['SRD 5.1, CC-BY-4.0'], notes: [], rules: rules('srd5', { mode: 'ac', save_target: null, pierce_base: 10 }) },
    { key: 'horror', name: '공포', summary: '살아남기', attribution: [], notes: [], rules: rules('horror', { mode: 'reduce', save_target: null, pierce_base: 10 }) },
  ],
};

function detail(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    title: '내 규칙',
    description: '',
    gm_guide: '',
    visibility: 'private',
    created_at: '2026-10-23T00:00:00Z',
    updated_at: '2026-10-23T00:00:00Z',
    rules: rules('srd5', { mode: 'ac', save_target: null, pierce_base: 10 }),
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, {
        public_id: ME,
        username: 'player_one',
        email: 'one@example.com',
        nickname: '모험가',
        identity: { verified: false, legal_adult: false, adult_content: false },
        guardian_consent: 'none',
        consents_pending: [],
        withdrawal_scheduled_at: null,
      }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${BASE}`]: () => json(200, { items: [], total: 0 }),
    'GET /api/v1/game/worlds': () => json(200, { items: [], total: 0 }),
    [`GET ${BASE}/templates`]: () => json(200, TEMPLATES),
    [`GET ${BASE}/${ID}`]: () => json(200, detail()),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === `${BASE}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('룰북', () => {
  it('마이페이지의 만들기에서 빈 목록으로, 세이브 방식을 골라 만들면 그 룰북으로 간다', async () => {
    const { seen } = signedIn({
      [`POST ${BASE}`]: (request) => json(201, detail({ title: '사십천', rules: rules('srd5', (request.body as { armor: unknown }).armor) })),
    });
    renderApp('/me?tab=creator');

    await userEvent.click(await screen.findByRole('link', { name: /재료와 시나리오 만들기/ }));
    await userEvent.click(await screen.findByRole('link', { name: '내 룰북' }));
    expect(await screen.findByText('아직 만든 룰북이 없습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '첫 룰북 만들기' }));

    const form = within(await screen.findByRole('form', { name: '룰북' }));
    expect(form.getByRole('radio', { name: '맞히기 어렵게' })).toBeChecked();
    expect(form.getByText('SRD 5.1, CC-BY-4.0')).toBeInTheDocument();
    await userEvent.type(form.getByLabelText('제목'), '사십천');
    await userEvent.click(form.getByRole('radio', { name: '세이브로 막음' }));
    expect(form.getByRole('button', { name: '만들기' })).toBeDisabled();
    await userEvent.type(form.getByLabelText('세이브의 목표값'), '7');
    await userEvent.click(form.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '사십천' })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', '')[0]?.body).toEqual({
      title: '사십천',
      description: '',
      gm_guide: '',
      template: 'srd5',
      die: 20,
      roll: ONE_OVER,
      armor: { mode: 'save', pierce_base: 10, save_target: 7 },
      resources: [],
      progression: null,
    });
  });

  it('템플릿을 바꾸면 방어 규칙도 그 템플릿의 것으로 돌아간다', async () => {
    signedIn();
    renderApp('/trpg/studio/rulebooks/new');

    const form = within(await screen.findByRole('form', { name: '룰북' }));
    await userEvent.click(form.getByRole('radio', { name: '방어구가 막지 않음' }));
    await userEvent.click(form.getByRole('radio', { name: '공포' }));
    expect(form.getByRole('radio', { name: '피해를 깎음' })).toBeChecked();
  });

  it('고치기에서 방어 규칙을 바꾸면 PATCH 로 보내고, 게시한 판은 바뀌지 않는다고 알린다', async () => {
    const { seen } = signedIn({
      [`PATCH ${BASE}/${ID}`]: () => json(200, detail({ updated_at: '2026-10-23T01:00:00Z', rules: rules('srd5', null) })),
    });
    renderApp(`/trpg/studio/rulebooks/${ID}`);

    expect(await screen.findByText(/게시할 때의 규칙으로 굳어 있어/)).toBeInTheDocument();
    expect(await screen.findByText(/템플릿: d20 판타지/)).toBeInTheDocument();
    const form = within(screen.getByRole('form', { name: '룰북' }));
    expect(form.queryByRole('radio', { name: '공포' })).toBeNull();
    await userEvent.click(form.getByRole('radio', { name: '방어구가 막지 않음' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `/${ID}`)[0]?.body).toEqual({ title: '내 규칙', description: '', gm_guide: '', die: 20, roll: ONE_OVER, armor: null, resources: [], progression: null });
    expect(within(screen.getByRole('form', { name: '룰북' })).getByRole('radio', { name: '방어구가 막지 않음' })).toBeChecked();
  });

  it('고치기에서 d100 의 눈 ≤ 기량으로 바꾸면 난이도마다 기량에 더하는 값을 보낸다. 방어 규칙이 있으면 보내기 전에 알린다', async () => {
    const { seen } = signedIn({
      [`PATCH ${BASE}/${ID}`]: (request) => json(200, detail({ rules: { ...rules('srd5', null), ...(request.body as object) } })),
    });
    renderApp(`/trpg/studio/rulebooks/${ID}`);

    const form = within(await screen.findByRole('form', { name: '룰북' }));
    await userEvent.clear(form.getByLabelText('주사위의 면 수'));
    await userEvent.type(form.getByLabelText('주사위의 면 수'), '100');
    await userEvent.click(form.getByRole('radio', { name: '눈이 기량 이하' }));
    expect(form.getByRole('alert')).toHaveTextContent('방어 규칙과 함께 쓰지 못합니다');
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(form.getByRole('radio', { name: '방어구가 막지 않음' }));
    await userEvent.clear(form.getByLabelText('어려움에서 기량에 더하는 값'));
    await userEvent.type(form.getByLabelText('어려움에서 기량에 더하는 값'), '-20');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    const body = sent(seen, 'PATCH', `/${ID}`)[0]?.body as { die: unknown; roll: unknown; armor: unknown };
    expect([body.die, body.roll, body.armor]).toEqual([100, { count: 1, style: 'under', shifts: { medium: 0, hard: -20 } }, null]);
  });

  it('고치기에서 수치를 더하고 채우면 PATCH 로 보낸다. 틀린 칸은 보내기 전에 알린다', async () => {
    const { seen } = signedIn({
      [`PATCH ${BASE}/${ID}`]: (request) => json(200, detail({ rules: { ...rules('srd5', null), resources: (request.body as { resources: unknown }).resources } })),
    });
    renderApp(`/trpg/studio/rulebooks/${ID}`);

    const form = within(await screen.findByRole('form', { name: '룰북' }));
    await userEvent.click(form.getByRole('button', { name: '수치 더하기' }));
    const row = within(form.getByRole('group', { name: '수치 resource' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    expect(await row.findByText(/이름을 30자까지/)).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `/${ID}`)).toHaveLength(0);

    await userEvent.type(row.getByLabelText('이름'), '마나');
    await userEvent.selectOptions(row.getByLabelText('최대에 더할 능력치의 보정'), 'heart');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect((sent(seen, 'PATCH', `/${ID}`)[0]?.body as { resources: unknown }).resources).toEqual([
      { key: 'resource', name: '마나', min: 0, max: { base: 5, ability: 'heart', cap: null }, start: 'max', rest: { short: null, long: { kind: 'fill', amount: null } }, each_round: null, at_min: null, at_max: null, visibility: 'everyone', holders: ['characters'] },
    ]);
  });

  it('고치기에서 성장을 켜고 레벨을 더하면 레벨표를 PATCH 로 보낸다. 경험치가 줄지 않으면 보내기 전에 알린다', async () => {
    const { seen } = signedIn({
      [`PATCH ${BASE}/${ID}`]: (request) => json(200, detail({ rules: { ...rules('srd5', null), progression: (request.body as { progression: unknown }).progression } })),
    });
    renderApp(`/trpg/studio/rulebooks/${ID}`);

    const form = within(await screen.findByRole('form', { name: '룰북' }));
    expect(form.queryByRole('group', { name: '레벨 2' })).toBeNull();
    await userEvent.click(form.getByRole('checkbox', { name: /경험치를 모아 레벨이 오름/ }));
    await userEvent.click(form.getByRole('button', { name: '레벨 더하기' }));
    const second = within(form.getByRole('group', { name: '레벨 3' }));
    expect(second.getByLabelText('누적 경험치')).toHaveValue('200');
    await userEvent.clear(second.getByLabelText('누적 경험치'));
    await userEvent.type(second.getByLabelText('누적 경험치'), '100');
    expect(second.getByText('레벨 2의 경험치보다 커야 합니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();

    await userEvent.type(second.getByLabelText('누적 경험치'), '0');
    await userEvent.clear(second.getByLabelText('최대 HP 증가'));
    await userEvent.type(second.getByLabelText('최대 HP 증가'), '4');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect((sent(seen, 'PATCH', `/${ID}`)[0]?.body as { progression: unknown }).progression).toEqual({
      levels: [
        { xp: 100, max_hp: 0, points: 1 },
        { xp: 1000, max_hp: 4, points: 1 },
      ],
    });
  });

  it('쓰는 시나리오가 있으면 지우지 못하고 그 제목을 알린다. 없으면 지우고 목록으로 간다', async () => {
    let inUse = true;
    signedIn({
      [`DELETE ${BASE}/${ID}`]: () =>
        inUse ? json(409, { detail: 'x', used_by: [{ id: 's1', title: '안개 마을' }] }) : new Response(null, { status: 204 }),
    });
    renderApp(`/trpg/studio/rulebooks/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '지우기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    expect(await dialog.findByText(/쓰는 시나리오: 안개 마을/)).toBeInTheDocument();

    inUse = false;
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    expect(await screen.findByRole('heading', { name: '내 룰북' })).toBeInTheDocument();
  });

  it('없거나 남의 룰북이면 찾을 수 없다고 알린다', async () => {
    signedIn({ [`GET ${BASE}/${ID}`]: () => json(404, { detail: 'x' }) });
    renderApp(`/trpg/studio/rulebooks/${ID}`);
    expect(await screen.findByText('룰북을 찾을 수 없습니다. 지워졌을 수 있습니다.')).toBeInTheDocument();
  });
});
