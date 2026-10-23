// web/apps/web/src/pages/chat/studio/lorebooks/ChatLorebooks.test.tsx
// chat 의 로어북. 빈 목록에서 만들기 → 고치기, 항목을 더해 저장(화면이 붙이는 id, 키워드의 겹침을 먼저 알림, 목록을 통째로),
// 이름과 설명만 보내는 저장, 게시(바뀐 것, 판의 목록을 다시 읽기), 운영자만 만드는 때(403), 없는 로어북.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';

const LOREBOOKS = '/api/v1/asset/lorebooks';
const ID = '00000000-0000-4000-8000-00000000f001';

function lorebook(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    name: '바다',
    description: '',
    entries: [],
    latest_version: null,
    published_at: null,
    created_at: '2026-10-24T00:00:00Z',
    updated_at: '2026-10-24T00:00:00Z',
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

/** 로그인한 운영자와, 받은 것을 기억하는 가짜 asset 서버 */
function signedIn(initial: Record<string, unknown> = lorebook(), routes: Routes = {}) {
  let current = initial;
  let versions: Record<string, unknown>[] = [];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${LOREBOOKS}`]: () => json(200, { items: [], total: 0 }),
    [`POST ${LOREBOOKS}`]: (request) => {
      current = lorebook({ name: (request.body as { name: string }).name });
      return json(201, current);
    },
    [`GET ${LOREBOOKS}/${ID}`]: () => json(200, current),
    [`PATCH ${LOREBOOKS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${LOREBOOKS}/${ID}/versions`]: () => json(200, versions),
    [`POST ${LOREBOOKS}/${ID}/versions`]: (request) => {
      const number = versions.length + 1;
      const version = { id: `v${number}`, number, note: (request.body as { note: string }).note, created_at: '2026-10-24T02:00:00Z' };
      versions = [version, ...versions];
      current = { ...current, latest_version: number };
      return json(201, { ...version, document: { name: current.name, entries: [] } });
    },
    ...routes,
  });
}

function calls(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === path);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('chat 의 로어북', () => {
  it('빈 목록에서 만들고, 항목을 더해 저장한다. 겹친 키워드는 먼저 알린다', async () => {
    const { seen } = signedIn();
    renderApp('/chat/studio/lorebooks');

    await userEvent.click(await screen.findByRole('link', { name: '첫 로어북 만들기' }));
    await userEvent.type(await screen.findByLabelText('이름'), ' 바다 ');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '바다', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(calls(seen, 'POST', LOREBOOKS)[0]?.body).toEqual({ name: '바다' });

    const form = screen.getByRole('form', { name: '항목' });
    await userEvent.click(within(form).getByRole('button', { name: '항목 더하기' }));
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText('항목 1의 이름'), '밀물');
    await userEvent.selectOptions(within(form).getByLabelText('항목 1의 종류'), '사건');
    await userEvent.type(within(form).getByLabelText('항목 1의 키워드(선택, 쉼표로 나눔)'), 'Sea, sea');
    await userEvent.type(within(form).getByLabelText('항목 1의 내용'), '하루 두 번 든다.');
    expect(within(form).getByText('같은 키워드가 두 번 있습니다.')).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();

    await userEvent.clear(within(form).getByLabelText('항목 1의 키워드(선택, 쉼표로 나눔)'));
    await userEvent.type(within(form).getByLabelText('항목 1의 키워드(선택, 쉼표로 나눔)'), '바다, 물때');
    await userEvent.click(within(form).getByLabelText('항목 1을 늘 넣기'));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${LOREBOOKS}/${ID}`)[0]?.body).toEqual({
      entries: [{ id: expect.stringMatching(/^lore-[0-9a-f]{8}$/), name: '밀물', kind: 'event', keywords: ['바다', '물때'], content: '하루 두 번 든다.', constant: true }],
    });
  });

  it('이름과 설명은 그 칸만 보내고, 게시하면 판을 알리고 판의 목록을 다시 읽는다', async () => {
    const { seen } = signedIn(lorebook({ entries: [{ id: 'lore-1', name: '밀물', kind: 'event', keywords: [], content: '든다.', constant: false }] }));
    renderApp(`/chat/studio/lorebooks/${ID}`);

    const info = await screen.findByRole('form', { name: '이름과 설명' });
    await userEvent.type(within(info).getByLabelText('설명(선택)'), '바닷가 마을');
    await userEvent.click(within(info).getByRole('button', { name: '저장' }));
    expect(await within(info).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${LOREBOOKS}/${ID}`)[0]?.body).toEqual({ name: '바다', description: '바닷가 마을' });

    expect(await screen.findByText('아직 낸 판이 없습니다.')).toBeInTheDocument();
    const publish = screen.getByRole('form', { name: '게시' });
    await userEvent.type(within(publish).getByLabelText('바뀐 것(선택)'), '첫 판');
    await userEvent.click(within(publish).getByRole('button', { name: '게시' }));

    expect(await within(publish).findByText(/1판을 게시했습니다/)).toBeInTheDocument();
    expect(calls(seen, 'POST', `${LOREBOOKS}/${ID}/versions`)[0]?.body).toEqual({ note: '첫 판' });
    const versions = await screen.findByRole('list', { name: '판' });
    expect(await within(versions).findByText('첫 판')).toBeInTheDocument();
  });

  it('운영자가 아니면 만들기를 막고(403) 알린다', async () => {
    signedIn(lorebook(), {
      [`POST ${LOREBOOKS}`]: () => json(403, { detail: '지금은 운영자만 할 수 있습니다.', code: 'operator_only' }),
    });
    renderApp('/chat/studio/lorebooks/new');

    await userEvent.type(await screen.findByLabelText('이름'), '바다');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByText('지금은 운영자만 로어북을 만들 수 있습니다.')).toBeInTheDocument();
  });

  it('없는 로어북은 찾을 수 없다고 알린다', async () => {
    signedIn(lorebook(), {
      [`GET ${LOREBOOKS}/${ID}`]: () => json(404, { detail: '찾을 수 없습니다.', code: 'lorebook_not_found' }),
    });
    renderApp(`/chat/studio/lorebooks/${ID}`);

    expect(await screen.findByText('로어북을 찾을 수 없습니다. 지워졌을 수 있습니다.')).toBeInTheDocument();
  });
});
