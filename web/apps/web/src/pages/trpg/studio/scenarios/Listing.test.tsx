// web/apps/web/src/pages/trpg/studio/scenarios/Listing.test.tsx
// 시나리오의 소개 탭과 공개(B9). 소개(한줄소개, 소개글, 장르 셋까지, 쉼표로 나눈 태그)를 탭의 저장으로 보내기,
// 공개 중에 비우기 막기, 낸 판의 공개와 바꾸기와 내리기(한 번 더 묻기), 소개가 비면 공개를 끄고 소개 탭으로 보내기,
// 운영자의 제재로 막힌 공개. 입력과 실패의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME } from '../../../../test/tableFixtures';
import { listingHints, toggleGenre, toListingBody } from './listingForm';
import { describeListingProblem, describePublicationProblem } from './listingProblem';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const LISTING = `${SCENARIO}/listing`;
const PUBLICATION = `${LISTING}/publication`;

type Listing = { tagline: string; description: string; genres: string[]; tags: string[]; version: number | null };

const EMPTY: Listing = { tagline: '', description: '', genres: [], tags: [], version: null };
const READY: Listing = { tagline: '비 내리는 밤의 수도원', description: '', genres: ['horror'], tags: ['수도원'], version: 1 };

function detail(listing: Listing) {
  return { scenario_id: ID, ...listing, rating: listing.version === null ? null : 'all', published_at: null, updated_at: null };
}

function version(number: number, note = '') {
  return { id: `v${number}`, number, note, created_at: '2026-10-24T00:00:00Z' };
}

function signedIn(start: Listing, refuse?: string) {
  let current = start;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${SCENARIO}`]: () => json(200, scenarioDetail()),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`GET ${SCENARIO}/versions`]: () => json(200, [version(2, '종탑을 더했다'), version(1)]),
    [`GET ${LISTING}`]: () => json(200, detail(current)),
    [`PATCH ${LISTING}`]: (request) => {
      current = { ...current, ...(request.body as Partial<Listing>) };
      return json(200, detail(current));
    },
    [`PUT ${PUBLICATION}`]: (request) => {
      if (refuse) return json(403, { detail: '이 판은 공개할 수 없습니다.', code: refuse });
      current = { ...current, version: (request.body as { version: number | null }).version };
      return json(200, detail(current));
    },
  });
}

function sent(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

async function panel(name: string) {
  return within(await screen.findByRole('tabpanel', { name }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('소개 탭', () => {
  it('한줄소개, 소개글, 장르(셋까지), 쉼표로 나눈 태그를 탭의 저장으로 보낸다. 같은 태그는 막는다', async () => {
    const { seen } = signedIn(EMPTY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    expect(form.getByText(/공개하지 않았습니다/)).toBeInTheDocument();
    await userEvent.type(form.getByRole('textbox', { name: '한줄소개' }), '  비 내리는 밤의 수도원  ');
    await userEvent.type(form.getByRole('textbox', { name: '소개글(선택)' }), '종이 열 번 울린다.');
    for (const genre of ['호러', '미스터리', '판타지']) await userEvent.click(form.getByRole('checkbox', { name: genre }));
    expect(form.getByRole('checkbox', { name: 'SF' })).toBeDisabled();
    await userEvent.type(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }), '수도원, 언데드, 수도원');
    expect(form.getByText('같은 태그가 두 번 있습니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.clear(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }));
    await userEvent.type(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }), '수도원, 언데드,');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', LISTING)).toEqual([
      { tagline: '비 내리는 밤의 수도원', description: '종이 열 번 울린다.', genres: ['horror', 'mystery', 'fantasy'], tags: ['수도원', '언데드'] },
    ]);
    expect(form.getByRole('textbox', { name: '한줄소개' })).toHaveValue('비 내리는 밤의 수도원');
  });

  it('공개 중이면 공개된 소개로 가는 길을 보이고, 한줄소개나 장르를 비우면 저장을 막는다', async () => {
    signedIn(READY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    expect(form.getByRole('link', { name: '공개된 소개 보기' })).toHaveAttribute('href', `/trpg/scenarios/${ID}`);
    await userEvent.click(form.getByRole('checkbox', { name: '호러' }));
    expect(form.getByText(/장르가 없습니다. 공개 중에는 비울 수 없습니다/)).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
  });
});

describe('공개', () => {
  it('낸 판을 공개하고, 다른 판으로 바꾸고, 한 번 더 물은 뒤 내린다', async () => {
    const { seen } = signedIn(READY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=publish`);

    const publish = await panel('게시');
    const list = within(await publish.findByRole('list', { name: '판' }));
    expect(await publish.findByText('1판을 공개 중입니다. 다른 판을 공개하면 그 판으로 바뀝니다.')).toBeInTheDocument();
    expect(list.getAllByText('공개 중')).toHaveLength(1);

    await userEvent.click(list.getByRole('button', { name: '2판 공개' }));
    expect(await list.findByRole('button', { name: '2판 공개 내리기' })).toBeInTheDocument();
    expect(list.getByRole('button', { name: '1판 공개' })).toBeEnabled();

    await userEvent.click(list.getByRole('button', { name: '2판 공개 내리기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '공개 내리기' }));
    expect(await publish.findByText(/공개한 판이 없습니다/)).toBeInTheDocument();
    expect(sent(seen, 'PUT', PUBLICATION)).toEqual([{ version: 2 }, { version: null }]);
  });

  it('소개가 비었으면 공개를 끄고 까닭과 소개 탭으로 가는 단추를 보인다', async () => {
    signedIn(EMPTY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=publish`);

    const publish = await panel('게시');
    const list = within(await publish.findByRole('list', { name: '판' }));
    expect(await list.findByRole('button', { name: '2판 공개' })).toBeDisabled();
    expect(publish.getByText(/한줄소개가 비어 있습니다. 장르를 하나도 고르지 않았습니다./)).toBeInTheDocument();
    await userEvent.click(publish.getByRole('button', { name: '소개 탭으로' }));
    expect(await screen.findByRole('tab', { name: '소개', selected: true })).toBeInTheDocument();
  });

  it('운영자가 제재한 판은 공개하지 못하고 까닭을 알린다', async () => {
    signedIn({ ...READY, version: null }, 'version_sanctioned');
    renderApp(`/trpg/studio/scenarios/${ID}?tab=publish`);

    const publish = await panel('게시');
    await userEvent.click(await publish.findByRole('button', { name: '2판 공개' }));
    expect(await publish.findByText(/운영자가 제재한 판이라 공개할 수 없습니다/)).toBeInTheDocument();
  });
});

describe('소개와 공개의 입력', () => {
  it('장르는 셋까지 켜고, 태그는 개수·길이·대소문자만 다른 겹침을 막고, 보낼 때 나누고 다듬는다', () => {
    expect(toggleGenre(['horror', 'sf', 'comedy'], 'fantasy')).toEqual(['horror', 'sf', 'comedy']);
    expect(toggleGenre(['horror', 'sf'], 'sf')).toEqual(['horror']);
    const draft = { tagline: '한 줄', description: '', genres: ['horror' as const], tags: 'Moon, moon' };
    expect(listingHints(draft, false).tags).toBe('같은 태그가 두 번 있습니다.');
    expect(listingHints({ ...draft, tags: 'a'.repeat(21) }, false).tags).toBe('태그 하나는 20자까지입니다.');
    expect(listingHints({ ...draft, tagline: '', tags: '' }, false)).toEqual({});
    expect(listingHints({ ...draft, tagline: ' ', tags: '' }, true).tagline).toContain('공개 중에는 비울 수 없습니다');
    expect(toListingBody({ ...draft, tagline: ' 한 줄 ', tags: ' 달, , 별 ' })).toEqual({ tagline: '한 줄', description: '', genres: ['horror'], tags: ['달', '별'] });
  });

  it('실패: 409 의 까닭, 공개 금지, 성인 확인, 없는 판', () => {
    const notReady = new ApiError({ status: 409, detail: 'x', body: { problems: ['genre_missing'] } });
    expect(describePublicationProblem(notReady).message).toBe('소개 탭에서 한줄소개와 장르를 적어야 공개할 수 있습니다. 장르를 하나도 고르지 않았습니다.');
    expect(describeListingProblem(notReady).message).toContain('먼저 게시 탭에서 공개를 내리세요');
    expect(describePublicationProblem(new ApiError({ status: 403, detail: 'x', code: 'publishing_banned' })).message).toContain('공개 금지 중');
    expect(describeListingProblem(new ApiError({ status: 403, detail: 'x', code: 'adult_content_required' })).message).toContain('성인 확인');
    expect(describePublicationProblem(new ApiError({ status: 404, detail: 'x' })).message).toContain('그 판이나 시나리오가 없습니다');
  });
});
