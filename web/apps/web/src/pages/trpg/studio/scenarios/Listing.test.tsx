// web/apps/web/src/pages/trpg/studio/scenarios/Listing.test.tsx
// 시나리오의 소개 탭과 공개(B9). 소개(한줄소개, 소개글, 장르 셋까지, 쉼표로 나눈 태그)를 탭의 저장으로 보내기,
// 공개 중에 비우기 막기, 낸 판의 공개와 바꾸기와 내리기(한 번 더 묻기), 소개가 비면 공개를 끄고 소개 탭으로 보내기,
// 운영자의 제재로 막힌 공개, 표지(#1164)를 내가 올린 그림에서 고르고 떼기. 입력과 실패의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME } from '../../../../test/tableFixtures';
import { listingHints, toListingBody } from './listingForm';
import { describeListingProblem, describePublicationProblem } from './listingProblem';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const LISTING = `${SCENARIO}/listing`;
const PUBLICATION = `${LISTING}/publication`;
const COVER = '00000000-0000-4000-8000-0000000000c1';

type Listing = { tagline: string; description: string; genre: string | null; tags: string[]; unlisted: boolean; version: number | null; cover_image_id?: string | null };

const EMPTY: Listing = { tagline: '', description: '', genre: null, tags: [], unlisted: false, version: null };
const READY: Listing = { tagline: '비 내리는 밤의 수도원', description: '', genre: 'horror', tags: ['수도원'], unlisted: false, version: 1 };

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
    [`GET ${GAME}/portraits`]: () => json(200, { items: [{ id: COVER, created_at: '2026-11-05T00:00:00Z' }], total: 1 }),
    [`GET ${GAME}/portraits/${COVER}/image`]: () => new Response('png', { status: 200 }),
  });
}

function sent(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

async function panel(name: string) {
  return within(await screen.findByRole('tabpanel', { name }));
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:cover'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('소개 탭', () => {
  it('한줄소개, 소개글, 장르(하나), 쉼표로 나눈 태그를 탭의 저장으로 보낸다. 같은 태그는 막는다', async () => {
    const { seen } = signedIn(EMPTY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    expect(form.getByText(/공개하지 않았습니다/)).toBeInTheDocument();
    await userEvent.type(form.getByRole('textbox', { name: '한줄소개' }), '  비 내리는 밤의 수도원  ');
    await userEvent.type(form.getByRole('textbox', { name: '소개글(선택)' }), '종이 열 번 울린다.');
    // 장르는 하나다. 다른 것을 누르면 바뀐다. 남성향·여성향은 장르에 없다(태그)
    const genre = form.getByRole('combobox', { name: '장르' });
    await userEvent.selectOptions(genre, '호러');
    await userEvent.selectOptions(genre, '미스터리');
    expect(genre).toHaveValue('mystery');
    expect(form.queryByRole('option', { name: '남성향' })).not.toBeInTheDocument();
    await userEvent.type(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }), '수도원, 언데드, 수도원');
    expect(form.getByText('같은 태그가 두 번 있습니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.clear(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }));
    await userEvent.type(form.getByRole('textbox', { name: '태그(선택, 쉼표로 나눔)' }), '수도원, 언데드,');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', LISTING)).toEqual([
      { tagline: '비 내리는 밤의 수도원', description: '종이 열 번 울린다.', genre: 'mystery', tags: ['수도원', '언데드'], unlisted: false, cover_image_id: null },
    ]);
    expect(form.getByRole('textbox', { name: '한줄소개' })).toHaveValue('비 내리는 밤의 수도원');
  });

  it('표지를 내가 올린 그림에서 골라 탭의 저장으로 보내고, 떼면 null 을 보낸다', async () => {
    const { seen } = signedIn(READY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    const cover = within(form.getByRole('group', { name: '표지' }));
    expect(cover.getByText('붙인 그림이 없습니다.')).toBeInTheDocument();
    await userEvent.click(cover.getByRole('button', { name: '그림 붙이기' }));
    const shelf = within(await cover.findByRole('region', { name: '표지 고르기' }));
    await userEvent.click(await shelf.findByRole('button', { name: '그림 1 고르기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();

    await userEvent.click(cover.getByRole('button', { name: '떼기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(sent(seen, 'PATCH', LISTING)).toHaveLength(2));
    expect(sent(seen, 'PATCH', LISTING).map((body) => (body as { cover_image_id: string | null }).cover_image_id)).toEqual([COVER, null]);
  });

  it('링크 공개를 고르면 보내고, 공개 중인 링크 공개면 나눌 주소를 보인다', async () => {
    const { seen } = signedIn(READY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    expect(form.queryByText(/링크 공개 주소/)).not.toBeInTheDocument();
    await userEvent.selectOptions(form.getByRole('combobox', { name: '공개 범위' }), '링크 공개');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect((sent(seen, 'PATCH', LISTING)[0] as { unlisted: boolean }).unlisted).toBe(true);
    expect(await form.findByText(`${window.location.origin}/trpg/scenarios/${ID}`)).toBeInTheDocument();
  });

  it('공개 중이면 공개된 소개로 가는 길을 보이고, 한줄소개를 비우면 저장을 막는다', async () => {
    signedIn(READY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    expect(form.getByRole('link', { name: '공개된 소개 보기' })).toHaveAttribute('href', `/trpg/scenarios/${ID}`);
    expect(form.getByRole('combobox', { name: '장르' })).toHaveValue('horror');
    await userEvent.clear(form.getByRole('textbox', { name: '한줄소개' }));
    expect(form.getByText(/공개 중에는 비울 수 없습니다/)).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('아직 쓰지 않은 소개는 장르를 고르기 전까지 저장을 막는다(장르는 반드시 하나다)', async () => {
    signedIn(EMPTY);
    renderApp(`/trpg/studio/scenarios/${ID}?tab=listing`);

    const form = within(await (await panel('소개')).findByRole('form', { name: '소개' }));
    await userEvent.type(form.getByRole('textbox', { name: '한줄소개' }), '비 내리는 밤');
    expect(form.getByText('장르를 골라 주세요. 장르는 반드시 하나입니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(form.getByRole('combobox', { name: '장르' }), '판타지');
    expect(form.getByRole('button', { name: '저장' })).toBeEnabled();
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
    expect(publish.getByText(/한줄소개가 비어 있습니다. 장르를 고르지 않았습니다./)).toBeInTheDocument();
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
  it('태그는 개수·길이·대소문자만 다른 겹침을 막고, 보낼 때 나누고 다듬는다. 장르는 하나를 그대로 보낸다', () => {
    const draft = { tagline: '한 줄', description: '', genre: 'horror' as const, tags: 'Moon, moon', unlisted: false, coverImageId: null };
    expect(listingHints(draft, false).tags).toBe('같은 태그가 두 번 있습니다.');
    expect(listingHints({ ...draft, tags: 'a'.repeat(21) }, false).tags).toBe('태그 하나는 20자까지입니다.');
    expect(listingHints({ ...draft, tagline: '', tags: '' }, false)).toEqual({});
    expect(listingHints({ ...draft, genre: null }, false).genre).toBe('장르를 골라 주세요. 장르는 반드시 하나입니다.');
    expect(listingHints({ ...draft, tagline: ' ', tags: '' }, true).tagline).toContain('공개 중에는 비울 수 없습니다');
    expect(toListingBody({ ...draft, tagline: ' 한 줄 ', tags: ' 달, , 별 ', unlisted: true })).toEqual({ tagline: '한 줄', description: '', genre: 'horror', tags: ['달', '별'], unlisted: true, cover_image_id: null });
  });

  it('실패: 409 의 까닭, 공개 금지, 성인 확인, 없는 판', () => {
    const notReady = new ApiError({ status: 409, detail: 'x', body: { problems: ['genre_missing'] } });
    expect(describePublicationProblem(notReady).message).toBe('소개 탭에서 한줄소개와 장르를 적어야 공개할 수 있습니다. 장르를 고르지 않았습니다.');
    // 장르 없음 하나뿐이면 처음 쓰는 소개 페이지다. 공개를 내리라고 하지 않는다
    expect(describeListingProblem(notReady).message).toBe('장르는 반드시 하나를 골라야 저장할 수 있습니다. 장르를 고르지 않았습니다.');
    const emptied = new ApiError({ status: 409, detail: 'x', body: { problems: ['tagline_empty'] } });
    expect(describeListingProblem(emptied).message).toContain('먼저 게시 탭에서 공개를 내리세요');
    expect(describePublicationProblem(new ApiError({ status: 403, detail: 'x', code: 'publishing_banned' })).message).toContain('공개 금지 중');
    expect(describeListingProblem(new ApiError({ status: 403, detail: 'x', code: 'adult_content_required' })).message).toContain('성인 확인');
    expect(describePublicationProblem(new ApiError({ status: 404, detail: 'x' })).message).toContain('그 판이나 시나리오가 없습니다');
  });
});
