// web/apps/web/src/pages/trpg/studio/campaigns/Campaigns.test.tsx
// 캠페인(#481 B). 만들면 그 캠페인으로 간다. 편: 내 시나리오를 더하고 앞으로 옮기고 이름을 정해 차례대로 보내고, 저장하면 점검을 다시 읽는다.
// 게시: 점검의 문제가 있으면 끄고, 통과하면 게시해 판의 목록을 다시 읽는다. 알릴 것은 막지 않는다.
// 시나리오를 쓰는 캠페인이 있으면 지우지 못한다(409). 편의 순수한 함수와 점검의 글.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME } from '../../../../test/tableFixtures';
import { describeDeleteProblem } from '../studioProblem';
import { problemText, warningText } from './checkLines';
import {
  addEpisode,
  CAMPAIGN_MAX_EPISODES,
  episodesChanged,
  longTitles,
  moveEpisode,
  removeEpisode,
  toEpisodesBody,
  unusedScenarios,
  type EpisodeDraft,
} from './episodesDraft';

const CAMPAIGNS = '/api/v1/game/campaigns';
const SCENARIOS = '/api/v1/game/scenarios';
const ID = '00000000-0000-4000-8000-0000000000d1';
const FIRST = '00000000-0000-4000-8000-0000000000e1';
const SECOND = '00000000-0000-4000-8000-0000000000e2';
const AT = '2026-11-02T00:00:00Z';

function scenario(id: string, title: string) {
  return { id, title, description: '', visibility: 'private' as const, created_at: AT, updated_at: AT };
}

type Episode = { scenario_id: string; title: string; scenario_title: string; last_version: number | null };

function campaign(title: string, episodes: Episode[] = [], updated = AT) {
  return {
    id: ID,
    title,
    description: '',
    visibility: 'private',
    rating: 'all',
    episode_count: episodes.length,
    episodes,
    created_at: AT,
    updated_at: updated,
  };
}

function check(problems: string[] = [], warnings: string[] = []) {
  return { ready: problems.length === 0, problems, warnings };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${SCENARIOS}`]: () => json(200, { items: [scenario(FIRST, '고성'), scenario(SECOND, '지하 묘지')], total: 2 }),
    [`GET ${CAMPAIGNS}/${ID}/versions`]: () => json(200, []),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캠페인 화면', () => {
  it('만들면 편 없이 보내고 그 캠페인으로 간다', async () => {
    const { seen } = signedIn({
      [`POST ${CAMPAIGNS}`]: () => json(201, campaign('왕국 연대기')),
      [`GET ${CAMPAIGNS}/${ID}`]: () => json(200, campaign('왕국 연대기')),
      [`GET ${CAMPAIGNS}/${ID}/publish-check`]: () => json(200, check(['episodes_too_few'])),
    });
    renderApp('/trpg/studio/campaigns/new');

    const form = within(await screen.findByRole('form', { name: '캠페인' }));
    await userEvent.type(form.getByLabelText('제목'), '왕국 연대기');
    await userEvent.click(form.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '왕국 연대기' })).toBeInTheDocument();
    expect(await screen.findByText('아직 편이 없습니다. 아래에서 시나리오를 골라 더하세요.')).toBeInTheDocument();
    expect(sent(seen, 'POST', CAMPAIGNS)[0]?.body).toEqual({ title: '왕국 연대기', description: '', episodes: [] });
  });

  it('시나리오를 더하고 앞으로 옮기고 이름을 정한 차례대로 저장하고, 점검을 다시 읽는다', async () => {
    let checks = 0;
    const saved = campaign(
      '왕국 연대기',
      [
        { scenario_id: SECOND, title: '', scenario_title: '지하 묘지', last_version: null },
        { scenario_id: FIRST, title: '서막', scenario_title: '고성', last_version: 2 },
      ],
      '2026-11-02T01:00:00Z',
    );
    const { seen } = signedIn({
      [`GET ${CAMPAIGNS}/${ID}`]: () =>
        json(200, campaign('왕국 연대기', [{ scenario_id: FIRST, title: '', scenario_title: '고성', last_version: 2 }])),
      [`GET ${CAMPAIGNS}/${ID}/publish-check`]: () => {
        checks += 1;
        return json(200, check(['episodes_too_few']));
      },
      [`PATCH ${CAMPAIGNS}/${ID}`]: () => json(200, saved),
    });
    renderApp(`/trpg/studio/campaigns/${ID}`);

    const episodes = within(await screen.findByRole('list', { name: '편' }));
    expect(episodes.getByText('2판까지 게시했습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '편 저장' })).toBeDisabled();
    // 이미 넣은 시나리오는 고를 수 없다
    const picker = await screen.findByLabelText('더할 시나리오');
    expect(within(picker).queryByRole('option', { name: '고성' })).toBeNull();
    await userEvent.selectOptions(picker, '지하 묘지');
    await userEvent.click(screen.getByRole('button', { name: '편 더하기' }));
    expect(episodes.getByText('저장하면 게시한 판을 확인합니다.')).toBeInTheDocument();
    await userEvent.click(episodes.getByRole('button', { name: '2편 앞으로' }));
    await userEvent.type(episodes.getByLabelText('2편의 이름(선택)'), '서막');
    expect(screen.getByText('더할 수 있는 내 시나리오가 없습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '편 저장' }));

    expect(await screen.findByText('편을 저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `${CAMPAIGNS}/${ID}`)[0]?.body).toEqual({
      episodes: [
        { scenario_id: SECOND, title: '' },
        { scenario_id: FIRST, title: '서막' },
      ],
    });
    expect(within(screen.getByRole('list', { name: '편' })).getByText('게시한 판이 없습니다.')).toBeInTheDocument();
    await vi.waitFor(() => expect(checks).toBe(2));
  });

  it('점검의 문제가 있으면 게시를 끄고 글로 알린다. 알릴 것만 있으면 게시하고 판의 목록을 다시 읽는다', async () => {
    let ready = false;
    let versions: unknown[] = [];
    const two = [
      { scenario_id: FIRST, title: '', scenario_title: '고성', last_version: 1 },
      { scenario_id: SECOND, title: '', scenario_title: '지하 묘지', last_version: null },
    ];
    const { seen } = signedIn({
      [`GET ${CAMPAIGNS}/${ID}`]: () => json(200, campaign('왕국 연대기', two)),
      [`GET ${CAMPAIGNS}/${ID}/publish-check`]: () =>
        json(200, ready ? check([], ['items_not_carried']) : check(['episode_unpublished'], ['items_not_carried'])),
      [`GET ${CAMPAIGNS}/${ID}/versions`]: () => json(200, versions),
      [`POST ${CAMPAIGNS}/${ID}/versions`]: (request) => {
        versions = [{ id: 'v1', number: 1, note: (request.body as { note: string }).note, created_at: AT }];
        return json(201, { ...(versions[0] as object), snapshot: {} });
      },
    });
    const view = renderApp(`/trpg/studio/campaigns/${ID}`);

    const problems = within(await screen.findByRole('list', { name: '고칠 것' }));
    expect(problems.getByText(problemText('episode_unpublished'))).toBeInTheDocument();
    expect(screen.getByText(warningText('items_not_carried'))).toBeInTheDocument();
    const form = within(screen.getByRole('form', { name: '캠페인 게시' }));
    expect(form.getByRole('button', { name: '게시' })).toBeDisabled();
    expect(await screen.findByText('아직 낸 판이 없습니다.')).toBeInTheDocument();
    view.unmount();

    ready = true;
    renderApp(`/trpg/studio/campaigns/${ID}`);
    expect(await screen.findByText('지금 게시할 수 있습니다.')).toBeInTheDocument();
    const again = within(screen.getByRole('form', { name: '캠페인 게시' }));
    await userEvent.type(again.getByLabelText('바뀐 것(선택)'), '첫 판');
    await userEvent.click(again.getByRole('button', { name: '게시' }));

    expect(await screen.findByText('1판을 게시했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', `${CAMPAIGNS}/${ID}/versions`)[0]?.body).toEqual({ note: '첫 판' });
    expect(await within(screen.getByRole('list', { name: '판' })).findByText('첫 판')).toBeInTheDocument();
  });

  it('게시가 409 로 막히면 점검을 고치라고 알린다', async () => {
    signedIn({
      [`GET ${CAMPAIGNS}/${ID}`]: () => json(200, campaign('왕국 연대기')),
      [`GET ${CAMPAIGNS}/${ID}/publish-check`]: () => json(200, check()),
      [`POST ${CAMPAIGNS}/${ID}/versions`]: () => json(409, { detail: '게시할 수 없습니다.', problems: ['rulebook_mismatch'] }),
    });
    renderApp(`/trpg/studio/campaigns/${ID}`);

    await userEvent.click(within(await screen.findByRole('form', { name: '캠페인 게시' })).getByRole('button', { name: '게시' }));

    expect(await screen.findByText('게시할 조건을 갖추지 못했습니다. 게시 점검의 문제를 고친 뒤 다시 게시하세요.')).toBeInTheDocument();
  });

  it('만들기 화면의 목록에 캠페인이 있다', async () => {
    signedIn();
    renderApp('/trpg/studio');

    expect(await screen.findByRole('link', { name: '내 캠페인' })).toHaveAttribute('href', '/trpg/studio/campaigns');
  });
});

describe('캠페인의 순수한 함수', () => {
  const one: EpisodeDraft = { scenarioId: FIRST, title: '', scenarioTitle: '고성', lastVersion: 1 };
  const two: EpisodeDraft = { scenarioId: SECOND, title: ' 끝 ', scenarioTitle: '지하 묘지', lastVersion: null };

  it('편을 옮기고 빼고, 끝을 넘으면 그대로다', () => {
    expect(moveEpisode([one, two], 1, -1)).toEqual([two, one]);
    expect(moveEpisode([one, two], 0, -1)).toEqual([one, two]);
    expect(moveEpisode([one, two], 1, 1)).toEqual([one, two]);
    expect(removeEpisode([one, two], 0)).toEqual([two]);
  });

  it('같은 시나리오는 한 번, 열 편까지 더한다. 쓰지 않은 시나리오만 고른다', () => {
    expect(addEpisode([one], scenario(FIRST, '고성'))).toEqual([one]);
    expect(addEpisode([one], scenario(SECOND, '지하 묘지'))[1]).toEqual({
      scenarioId: SECOND,
      title: '',
      scenarioTitle: '지하 묘지',
      lastVersion: undefined,
    });
    const full = Array.from({ length: CAMPAIGN_MAX_EPISODES }, (_, at) => ({ ...one, scenarioId: `s${at}` }));
    expect(addEpisode(full, scenario(SECOND, '지하 묘지'))).toHaveLength(CAMPAIGN_MAX_EPISODES);
    expect(unusedScenarios([scenario(FIRST, '고성'), scenario(SECOND, '지하 묘지')], [one]).map((s) => s.id)).toEqual([SECOND]);
  });

  it('이름은 공백을 떼어 보내고 30자를 넘으면 알린다. 바뀐 것을 안다', () => {
    expect(toEpisodesBody([one, two])).toEqual([
      { scenario_id: FIRST, title: '' },
      { scenario_id: SECOND, title: '끝' },
    ]);
    expect(longTitles([one, { ...two, title: 'ㄱ'.repeat(31) }])).toEqual([1]);
    expect(episodesChanged([one, two], [one, { ...two, title: '끝' }])).toBe(false);
    expect(episodesChanged([one, two], [two, one])).toBe(true);
  });

  it('점검의 글. 모르는 이름은 그대로 보인다', () => {
    expect(problemText('episodes_too_few')).toBe('편이 둘 이상 있어야 합니다.');
    expect(problemText('new_problem')).toBe('new_problem');
    expect(warningText('progression_missing')).toContain('경험치');
  });

  it('시나리오를 쓰는 캠페인이 있으면 그 제목을 알린다', () => {
    const error = new ApiError({ status: 409, detail: '…', body: { used_by: [{ id: ID, title: '왕국 연대기' }] } });
    expect(describeDeleteProblem(error, 'scenarios').message).toBe(
      '이 시나리오를 쓰는 캠페인이 있어 지울 수 없습니다. 캠페인의 편에서 뺀 뒤 다시 지우세요. 쓰는 캠페인: 왕국 연대기.',
    );
  });
});
