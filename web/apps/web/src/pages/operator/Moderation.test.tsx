// web/apps/web/src/pages/operator/Moderation.test.tsx
// 신고 처리(E4). 운영자가 아니면 없는 화면이고 메뉴도 없다. 운영자는 두 목록을 보고,
// 캐릭터의 신고를 펼쳐 처리하고(본문, 처리를 고르기 전에는 보내지 않음) 숨기며,
// 대화 속 답의 신고는 까닭을 적어야 열리고(쿼리의 reason) 처리한다. 다른 운영자가 먼저 처리했으면(409) 알린다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const ASSET = '/api/v1/asset/admin';
const CHAT = '/api/v1/chat/admin';
const CHARACTER = '00000000-0000-4000-8000-0000000000c1';
const REPORT = '00000000-0000-4000-8000-0000000000a1';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

const GROUP = {
  character_id: CHARACTER,
  name: '세라',
  hidden: false,
  open_count: 2,
  reasons: { spam: 1, abuse: 0, sexual: 0, minor: 1, illegal: 0, other: 0 },
  first_reported_at: '2026-10-23T01:00:00Z',
  last_reported_at: '2026-10-23T02:00:00Z',
};

const CHARACTER_REPORTS = [
  { id: 'r2', reason: 'minor', description: '어린 인물', version: 2, created_at: '2026-10-23T02:00:00Z', handled_at: null, outcome: null },
  { id: 'r1', reason: 'spam', description: '', version: 1, created_at: '2026-10-23T01:00:00Z', handled_at: null, outcome: null },
];

const SUMMARY = {
  id: REPORT,
  character_id: CHARACTER,
  character_name: '세라',
  character_version: 3,
  model_slug: 'luna',
  reason: 'sexual',
  created_at: '2026-10-23T03:00:00Z',
};

const DETAIL = {
  ...SUMMARY,
  description: '선을 넘음',
  content: '위험한 답.',
  context: [
    { role: 'user', content: '안녕' },
    { role: 'assistant', content: '어서 와.' },
  ],
  handled_at: null,
  outcome: null,
};

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedInAs(roles: string[], routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${ASSET}/character-reports`]: () => json(200, { items: [GROUP], total: 1 }),
    [`GET ${ASSET}/characters/${CHARACTER}/reports`]: () => json(200, CHARACTER_REPORTS),
    [`GET ${CHAT}/message-reports`]: () => json(200, { items: [SUMMARY], total: 1 }),
    [`GET ${CHAT}/message-reports/${REPORT}`]: () => json(200, DETAIL),
    'GET /api/v1/board/reports': () => json(200, { items: [], page: 1, size: 20, total: 0 }),
    ...routes,
  });
}

function calls(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === path);
}

function query(request: SeenRequest): URLSearchParams {
  return new URLSearchParams(request.url.split('?')[1] ?? '');
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('신고 처리', () => {
  it('운영자가 아니면 없는 화면이고 메뉴도 없다. 운영자의 API 를 부르지 않는다', async () => {
    const { seen } = signedInAs([]);
    renderApp('/operator/reports');

    expect(await screen.findByRole('heading', { name: '찾을 수 없습니다' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '신고 처리' })).not.toBeInTheDocument();
    expect(seen.some((request) => request.url.includes('/admin/'))).toBe(false);
  });

  it('운영자는 메뉴로 가서 두 목록을 본다. 사유마다의 수는 미성년부터다', async () => {
    signedInAs(['operator']);
    renderApp('/');

    await userEvent.click(await screen.findByRole('link', { name: '신고 처리' }));

    // 목록은 읽기 전에도 빈 채로 있다. 받은 것이 그려질 때까지 기다린다
    const characters = await screen.findByRole('list', { name: '신고된 캐릭터' });
    expect(await within(characters).findByText('세라')).toBeInTheDocument();
    expect(within(characters).getByText('미성년 인물을 성적으로 1 · 스팸·광고 1')).toBeInTheDocument();
    const answers = await screen.findByRole('list', { name: '신고된 답' });
    expect(await within(answers).findByRole('link', { name: '세라(3번째 판)의 답' })).toHaveAttribute(
      'href',
      `/operator/reports/messages/${REPORT}`,
    );
  });

  it('캐릭터를 펼치면 신고를 읽고, 처리를 고르고 사유를 적어야 보낸다. 보내면 목록을 다시 읽는다', async () => {
    const { seen } = signedInAs(['operator'], {
      [`PUT ${ASSET}/characters/${CHARACTER}/reports/outcome`]: () => json(200, { handled: 2, hidden: true }),
    });
    renderApp('/operator/reports');

    await userEvent.click(await screen.findByText('신고 보기와 처리'));
    const reports = await screen.findByRole('list', { name: '이 캐릭터의 신고' });
    expect(await within(reports).findByText('어린 인물')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '처리하기' }));
    expect(screen.getByText('처리를 골라 주세요.')).toBeInTheDocument();
    expect(screen.getByText(/사유를 적어 주세요/)).toBeInTheDocument();
    expect(calls(seen, 'PUT', `${ASSET}/characters/${CHARACTER}/reports/outcome`)).toHaveLength(0);

    await userEvent.click(screen.getByLabelText('받아들이고 숨기기'));
    await userEvent.type(screen.getByLabelText('처리의 사유'), '  신고 2건 확인  ');
    await userEvent.click(screen.getByRole('button', { name: '처리하기' }));

    expect(await screen.findByText(/숨겨 있습니다/)).toBeInTheDocument();
    const [put] = calls(seen, 'PUT', `${ASSET}/characters/${CHARACTER}/reports/outcome`);
    expect(put?.body).toEqual({ outcome: 'actioned', reason: '신고 2건 확인' });
    await vi.waitFor(() => expect(calls(seen, 'GET', `${ASSET}/character-reports`).length).toBeGreaterThan(1));
  });

  it('숨기기는 사유와 함께 보낸다', async () => {
    const { seen } = signedInAs(['operator'], {
      [`PUT ${ASSET}/characters/${CHARACTER}/hidden`]: () => json(200, { hidden: true }),
    });
    renderApp('/operator/reports');

    await userEvent.click(await screen.findByText('신고 보기와 처리'));
    await userEvent.type(await screen.findByLabelText('숨기는 사유'), '확인 전 임시');
    await userEvent.click(screen.getByRole('button', { name: '숨기기' }));

    expect(await screen.findByRole('button', { name: '숨김 풀기' })).toBeInTheDocument();
    const [put] = calls(seen, 'PUT', `${ASSET}/characters/${CHARACTER}/hidden`);
    expect(put?.body).toEqual({ hidden: true, reason: '확인 전 임시' });
  });

  it('대화 속 답은 까닭을 적어야 열리고, 열면 앞의 말과 답을 보이고 처리한다', async () => {
    const { seen } = signedInAs(['operator'], {
      [`PUT ${CHAT}/message-reports/${REPORT}/outcome`]: () => new Response(null, { status: 204 }),
    });
    renderApp(`/operator/reports/messages/${REPORT}`);

    await userEvent.click(await screen.findByRole('button', { name: '열기' }));
    expect(screen.getByText(/사유를 적어 주세요/)).toBeInTheDocument();
    expect(calls(seen, 'GET', `${CHAT}/message-reports/${REPORT}`)).toHaveLength(0);

    await userEvent.type(screen.getByLabelText('보는 까닭'), '미성년 신고 확인');
    await userEvent.click(screen.getByRole('button', { name: '열기' }));

    expect(await screen.findByText('위험한 답.')).toBeInTheDocument();
    const context = screen.getByRole('list', { name: '앞의 말' });
    expect(within(context).getByText('사람')).toBeInTheDocument();
    expect(within(context).getByText('어서 와.')).toBeInTheDocument();
    const [read] = calls(seen, 'GET', `${CHAT}/message-reports/${REPORT}`);
    expect(query(read as SeenRequest).get('reason')).toBe('미성년 신고 확인');

    await userEvent.click(screen.getByLabelText('기각'));
    await userEvent.type(screen.getByLabelText('처리의 사유'), '문제 없음');
    await userEvent.click(screen.getByRole('button', { name: '처리하기' }));

    expect(await screen.findByText('처리한 신고입니다.')).toBeInTheDocument();
    const [put] = calls(seen, 'PUT', `${CHAT}/message-reports/${REPORT}/outcome`);
    expect(put?.body).toEqual({ outcome: 'dismissed', reason: '문제 없음' });
    // 보는 기록이 쌓이지 않게 다시 읽지 않는다
    expect(calls(seen, 'GET', `${CHAT}/message-reports/${REPORT}`)).toHaveLength(1);
  });

  it('다른 운영자가 먼저 처리했으면 알린다', async () => {
    signedInAs(['operator'], {
      [`PUT ${CHAT}/message-reports/${REPORT}/outcome`]: () =>
        json(409, { detail: '이미 처리한 신고입니다.', code: 'already_handled' }),
    });
    renderApp(`/operator/reports/messages/${REPORT}`);

    await userEvent.type(await screen.findByLabelText('보는 까닭'), '확인');
    await userEvent.click(screen.getByRole('button', { name: '열기' }));
    await userEvent.click(await screen.findByLabelText('받아들임'));
    await userEvent.type(screen.getByLabelText('처리의 사유'), '확인');
    await userEvent.click(screen.getByRole('button', { name: '처리하기' }));

    expect(await screen.findByText(/이미 처리한 신고입니다. 목록을 다시 읽습니다/)).toBeInTheDocument();
  });
});
