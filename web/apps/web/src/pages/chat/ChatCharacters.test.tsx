// web/apps/web/src/pages/chat/ChatCharacters.test.tsx
// chat 의 캐릭터 탐색(C1)과 소개(C2). 로그인 없이 탐색과 더 보기, 소개(거른 HTML, 글 속 그림, 호감도의 단계, 시작 상황),
// 로그인으로 보내는 단추, 시작 상황을 골라 대화 시작(대화로 감), 시작의 실패(성인 확인, 새 판), 내 대화(새 판이 있음),
// 일러스트의 칸, 볼 수 없는 캐릭터. 소개 글을 거르는 순수한 함수와 글을 짓는 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { conversationLine, hasNewerVersion, profileLine, stageNames, startTimeLabel } from './character/characterView';
import { cleanStyle, sanitizeIntro } from './character/introHtml';
import { describeStartProblem } from './character/startProblem';
import { nextOffset } from './chatQueries';

const LUNA = '00000000-0000-4000-8000-00000000c201';
const PORTRAIT = '00000000-0000-4000-8000-00000000a201';
const INLINE = '00000000-0000-4000-8000-00000000a202';
const SCENE = '00000000-0000-4000-8000-00000000a203';
const CONVERSATION = '00000000-0000-4000-8000-00000000d201';
const LISTINGS = '/api/v1/asset/listings/characters';

function summary(n: number) {
  return { id: n === 1 ? LUNA : `00000000-0000-4000-8000-0000000c2${String(n).padStart(3, '0')}`, image_id: null, name: n === 1 ? '루나' : `캐릭터 ${n}`, published_at: '2026-10-20T00:00:00Z', rating: 'all', tags: ['다정함'], version: 3 };
}

const DOCUMENT = {
  name: '루나',
  age: '20대',
  gender: '여성',
  tags: ['다정함', '카페'],
  rating: 'all',
  image_id: PORTRAIT,
  greeting: '어서 와요.',
  intro_html: `<p style="color: red; position: fixed">카페의 <b>주인</b></p><script>alert(1)</script><img src="/api/v1/asset/images/${INLINE}" alt="카페 사진"><a href="https://example.com/x" onclick="x()">블로그</a><a href="javascript:alert(1)">나쁜 링크</a>`,
  starts: [
    { title: '비 오는 오후', situation: '비를 피해 카페에 들어온다.', hour: 15 },
    { title: '문 닫을 무렵', situation: '마지막 손님이 된다.' },
  ],
  affection: { display: 'stage', start: 0, stages: [{ name: '친한 사이', at: 50 }, { name: '처음 본 사이', at: 0 }], rules: [] },
  event_scenes: [{ id: 'rain', title: '비 오는 창가', image_id: SCENE, description: '', collectible: true, when: { kind: 'reach_place', target: 'cafe' } }],
};

type Routes = Record<string, (request: SeenRequest) => Response>;

function routes(extra: Routes = {}): Routes {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
  return {
    [`GET ${LISTINGS}`]: (request) => {
      const offset = new URL(request.url, 'http://x').searchParams.get('offset');
      return offset === '20' ? json(200, { items: [summary(21)], total: 21 }) : json(200, { items: Array.from({ length: 20 }, (_, i) => summary(i + 1)), total: 21 });
    },
    [`GET ${LISTINGS}/${LUNA}`]: () => json(200, { id: LUNA, version: 3, published_at: '2026-10-20T00:00:00Z', document: DOCUMENT }),
    [`GET /api/v1/asset/images/${PORTRAIT}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${INLINE}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${SCENE}`]: () => new Response('png', { status: 200 }),
    ...extra,
  };
}

function signedOut(extra: Routes = {}) {
  return installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }), ...routes(extra) });
}

function signedIn(extra: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: false, legal_adult: false, adult_content: false }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/chat/conversations': () =>
      json(200, {
        items: [{ id: CONVERSATION, title: '비 오는 오후', character: { id: LUNA, image_id: null, name: '루나', rating: 'all', version: 2 }, model: null, created_at: '2026-10-21T00:00:00Z', updated_at: '2026-10-22T00:00:00Z' }],
        total: 1,
      }),
    'GET /api/v1/chat/gallery': () => json(200, { items: [{ character_id: LUNA, scene_id: 'rain', unlocked_at: '2026-10-23T00:00:00Z' }], total: 1 }),
    ...routes(extra),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캐릭터 탐색', () => {
  it('로그인하지 않아도 공개 캐릭터를 보이고, 더 보기로 이어 읽고, 카드를 누르면 소개로 간다', async () => {
    const { seen } = signedOut();
    renderApp('/chat');

    const grid = within(await screen.findByRole('list', { name: '캐릭터' }));
    expect(await grid.findAllByRole('listitem')).toHaveLength(20);
    expect(screen.getByText('21명')).toBeInTheDocument();
    expect(screen.getByText(/로그인하고 성인 확인을 하면 보입니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '더 보기' }));
    expect(await grid.findByText('캐릭터 21')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '더 보기' })).toBeNull();
    expect(seen.some((request) => request.url.endsWith(`${LISTINGS}?limit=20&offset=20`))).toBe(true);

    await userEvent.click(grid.getByRole('link', { name: /루나/ }));
    expect(await screen.findByRole('heading', { name: '루나', level: 1 })).toBeInTheDocument();
  });
});

describe('캐릭터 소개', () => {
  it('거른 소개와 글 속 그림, 호감도의 단계, 시작 상황을 보이고, 로그인하지 않았으면 로그인으로 보낸다', async () => {
    const { seen } = signedOut();
    const { container } = renderApp(`/chat/characters/${LUNA}`);

    expect(await screen.findByRole('heading', { name: '루나', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('20대 · 여성')).toBeInTheDocument();
    const intro = container.querySelector('.intro-html') as HTMLElement;
    expect(intro.querySelector('script')).toBeNull();
    await vi.waitFor(() => expect(intro.querySelector('p')?.style.color).toBe('red'));
    expect(intro.querySelector('p')?.style.position).toBe('');
    expect(within(intro).getByRole('link', { name: '블로그' })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(intro).getByRole('link', { name: '블로그' })).not.toHaveAttribute('onclick');
    expect(within(intro).getByText('나쁜 링크')).not.toHaveAttribute('href');
    await vi.waitFor(() => expect(within(intro).getByAltText('카페 사진')).toHaveAttribute('src', 'blob:image'));
    expect(seen.some((request) => request.url === `/api/v1/asset/images/${INLINE}`)).toBe(true);

    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(expect.arrayContaining(['1. 처음 본 사이', '2. 친한 사이']));
    expect(screen.getByRole('radio', { name: '비 오는 오후' })).toBeChecked();
    expect(screen.getByText('1일째 15시에 시작')).toBeInTheDocument();
    expect(screen.getByText('1일째 12시에 시작')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인하고 대화 시작' })).toHaveAttribute('href', '/login');
    expect(screen.queryByRole('heading', { name: '이 캐릭터와의 대화' })).toBeNull();
    expect(within(await screen.findByRole('list', { name: '일러스트' })).getByText('아직 열지 않음')).toBeInTheDocument();
    expect(screen.getByText('로그인하면 내가 연 일러스트가 보입니다.')).toBeInTheDocument();
  });

  it('시작 상황을 골라 대화를 시작하면 대화로 간다. 내 대화와 새 판, 연 일러스트를 보인다', async () => {
    const { seen } = signedIn({
      'POST /api/v1/chat/conversations': () => json(201, { id: CONVERSATION }),
    });
    renderApp(`/chat/characters/${LUNA}`);

    const mine = within(await screen.findByRole('list', { name: '내 대화' }));
    expect(mine.getByRole('link', { name: '비 오는 오후' })).toHaveAttribute('href', `/chat/conversations/${CONVERSATION}`);
    expect(mine.getByText(/모델을 아직 고르지 않음 · 새 판이 있음/)).toBeInTheDocument();
    const scenes = within(await screen.findByRole('list', { name: '일러스트' }));
    expect(await scenes.findByText('비 오는 창가')).toBeInTheDocument();
    expect(screen.getByText('1 / 1 열림')).toBeInTheDocument();
    expect(seen.some((request) => request.url.includes(`/chat/gallery?character_id=${LUNA}`))).toBe(true);
    expect(seen.some((request) => request.url.includes(`/chat/conversations?character_id=${LUNA}&limit=20&offset=0`))).toBe(true);

    await userEvent.click(screen.getByRole('radio', { name: '문 닫을 무렵' }));
    await userEvent.click(screen.getByRole('button', { name: '대화 시작' }));
    expect(await screen.findByRole('heading', { name: 'chat' })).toBeInTheDocument();
    const posted = seen.filter((request) => request.method === 'POST' && request.url === '/api/v1/chat/conversations');
    expect(posted.map((request) => request.body)).toEqual([{ character_id: LUNA, start: 1 }]);
  });

  it('성인 확인이 필요하면 본인인증으로 가는 길을, 새 판에 시작 상황이 없으면 다시 고르게 하고 판을 다시 읽는다', async () => {
    let answer = json(403, { detail: '성인', code: 'adult_content_required' });
    const { seen } = signedIn({ 'POST /api/v1/chat/conversations': () => answer });
    renderApp(`/chat/characters/${LUNA}`);

    await userEvent.click(await screen.findByRole('button', { name: '대화 시작' }));
    expect(await screen.findByText(/성인 확인을 하면 대화할 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '본인인증하기' })).toHaveAttribute('href', '/me/identity');

    const reads = () => seen.filter((request) => request.url === `${LISTINGS}/${LUNA}`).length;
    const before = reads();
    answer = json(422, { detail: '없음', code: 'start_not_found', starts: 1 });
    await userEvent.click(screen.getByRole('button', { name: '대화 시작' }));
    expect(await screen.findByText(/고른 시작 상황이 새 판에 없습니다/)).toBeInTheDocument();
    await vi.waitFor(() => expect(reads()).toBeGreaterThan(before));
  });

  it('볼 수 없는 캐릭터면 까닭과 탐색으로 가는 길', async () => {
    signedOut({ [`GET ${LISTINGS}/${LUNA}`]: () => json(404, { detail: 'x' }) });
    renderApp(`/chat/characters/${LUNA}`);
    expect(await screen.findByText(/볼 수 없는 캐릭터입니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '다른 캐릭터 찾기' })).toHaveAttribute('href', '/chat');
  });
});

describe('캐릭터 화면의 순수한 함수', () => {
  it('소개 글을 같은 허용 목록으로 거른다', () => {
    expect(cleanStyle('COLOR: blue; position: absolute; background-color: url(x); width:10px;bad')).toBe('color: blue; width: 10px');
    const html = sanitizeIntro(
      `<div style="z-index: 9" class="x" data-x="1"><iframe src="https://e"></iframe><img src="https://evil/a.png"><img src="/api/v1/asset/images/${INLINE}" onerror="x()"><td colspan="2">칸</td><form><input></form><details open><summary>더</summary>속</details></div>`,
    );
    const box = document.createElement('div');
    box.innerHTML = html;
    expect(box.querySelector('iframe, form, input')).toBeNull();
    expect(box.querySelector('div')?.attributes).toHaveLength(0);
    expect(sanitizeIntro('<p style="color: blue; position: fixed">글</p>')).toBe('<p data-intro-style="color: blue">글</p>');
    const images = box.querySelectorAll('img');
    expect([...images].map((image) => [image.getAttribute('src'), image.getAttribute('data-image-id'), image.getAttribute('onerror')])).toEqual([
      [null, null, null],
      [null, INLINE, null],
    ]);
    expect(box.querySelector('details')).toHaveAttribute('open');
  });

  it('호감도의 단계, 시각, 머리의 한 줄, 대화의 한 줄, 새 판, 쪽, 시작의 실패', () => {
    expect(stageNames(DOCUMENT.affection as never)).toEqual(['처음 본 사이', '친한 사이']);
    expect(stageNames({ ...DOCUMENT.affection, display: 'number' } as never)).toEqual([]);
    expect(stageNames(null)).toEqual([]);
    expect(startTimeLabel(undefined)).toBe('1일째 12시에 시작');
    expect(profileLine({ age: ' ', gender: '남성' })).toBe('남성');
    expect(conversationLine({ updated_at: 'x', model: { slug: 'm', display_name: '모델 M', usable: false, grade: 'standard', vendor: 'v', retires_on: null } as never })).toBe('x · 모델 M(지금은 쓸 수 없음)');
    expect(hasNewerVersion({ character: { version: 3 } as never }, 3)).toBe(false);
    expect(nextOffset(1, 20, 21)).toBe(20);
    expect(nextOffset(2, 20, 21)).toBeUndefined();
    expect(describeStartProblem(new ApiError({ status: 503, detail: 'x', retryAfter: 5 })).text).toContain('5초 뒤에');
    expect(describeStartProblem(new ApiError({ status: 404, detail: 'x' })).reread).toBe(true);
  });
});
