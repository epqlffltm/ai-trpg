// web/apps/web/src/pages/trpg/room/round/RoundHistory.test.tsx
// 라운드 기록(B10). 최근 것 위에 앞의 라운드를 쪽으로 잇기(창을 고정해 사이가 비지 않게), 1 번에 닿으면 줄이 사라짐,
// 기록 받기(형식 고르기, 서버의 파일 이름, 429). 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { filenameFromDisposition } from '../../../../api/disposition';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Round } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, round, roomRoutes, sheet, tableDetail } from '../../../../test/tableFixtures';
import { transcriptProblemText } from '../transcript/transcriptProblem';
import { fallbackFilename } from '../transcript/transcriptView';
import { hiddenBefore, mergeRounds } from './roundView';

const TABLE_ID = '00000000-0000-4000-8000-0000000000b8';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const TOTAL = 33;

const PLAYING = tableDetail(TABLE_ID, {
  status: 'playing',
  title: '종탑',
  members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() }), member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() })],
});

function closed(number: number) {
  return round(number, { status: 'closed', waiting_for: [] });
}

/** 서버처럼 offset 과 limit 으로 1..TOTAL 번을 자른다 */
function page(request: SeenRequest) {
  const params = new URL(request.url, 'http://x').searchParams;
  const offset = Number(params.get('offset') ?? 0);
  const limit = Number(params.get('limit') ?? 20);
  const items = [];
  for (let number = offset + 1; number <= Math.min(TOTAL, offset + limit); number += 1) items.push(number === TOTAL ? round(number) : closed(number));
  return json(200, { items, total: TOTAL });
}

function open(transcript: () => Response = () => json(404, { detail: 'x' })) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, {
      [`GET ${BASE}`]: () => json(200, PLAYING),
      [`GET ${BASE}/rounds/current`]: () => json(200, round(TOTAL)),
      [`GET ${BASE}/rounds`]: page,
      [`GET ${BASE}/transcript`]: transcript,
    }),
  });
}

function roundReads(seen: SeenRequest[]): string[] {
  return seen.filter((request) => request.url.startsWith(`${BASE}/rounds?`)).map((request) => request.url.split('?')[1] ?? '');
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('앞의 라운드', () => {
  it('최근 것 위에 20 개씩 잇고, 1 번에 닿으면 줄이 사라진다. 최근의 라운드는 처음 누른 번호에 고정한다', async () => {
    const { seen } = open();
    renderApp(`/trpg/tables/${TABLE_ID}`);

    expect(await screen.findByText('앞의 라운드 23개')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '라운드 23' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '앞의 라운드 더 보기(20개)' }));

    expect(await screen.findByRole('heading', { name: '라운드 4' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '라운드 23' })).toBeInTheDocument();
    expect(screen.getByText('앞의 라운드 3개')).toBeInTheDocument();
    expect(roundReads(seen)).toEqual(expect.arrayContaining(['offset=23&limit=100', 'offset=3&limit=20']));

    await userEvent.click(screen.getByRole('button', { name: '앞의 라운드 더 보기(3개)' }));
    expect(await screen.findByRole('heading', { name: '라운드 1' })).toBeInTheDocument();
    expect(roundReads(seen)).toContain('offset=0&limit=3');
    expect(screen.queryByText(/앞의 라운드 \d+개/)).toBeNull();
    const headings = screen.getAllByRole('heading', { name: /^라운드 \d+$/ }).map((heading) => heading.textContent);
    expect(headings).toHaveLength(TOTAL - 1);
  });
});

describe('기록 받기', () => {
  it('형식을 고르면 서버가 붙인 이름으로 내려받고, 너무 자주면 기다릴 초를 적는다', async () => {
    const create = vi.fn(() => 'blob:x');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    let answer = () =>
      new Response('# 종탑', { status: 200, headers: { 'Content-Type': 'text/markdown', 'Content-Disposition': "attachment; filename*=UTF-8''%EC%A2%85%ED%83%91.md" } });
    const { seen } = open(() => answer());
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '기록 받기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '기록 받기' }));
    await userEvent.click(dialog.getByRole('button', { name: '마크다운(.md)' }));
    expect(await dialog.findByText('받았습니다: 종탑.md')).toBeInTheDocument();
    expect(create).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(seen.some((request) => request.url === `${BASE}/transcript?format=md`)).toBe(true);

    answer = () => json(429, { detail: 'x', code: 'too_many_attempts' }, { 'Retry-After': '120' });
    await userEvent.click(dialog.getByRole('button', { name: '글(.txt)' }));
    expect(await dialog.findByText('기록은 10분에 10번까지 받습니다. 120초 뒤에 다시 받아 주세요.')).toBeInTheDocument();
  });
});

describe('기록의 순수한 함수', () => {
  it('라운드 합치기, 보이지 않는 수, 파일 이름, 실패의 글', () => {
    const merged = mergeRounds([closed(3), closed(1)] as unknown as Round[], [closed(3), closed(4)] as unknown as Round[]);
    expect(merged.map((item) => item.number)).toEqual([1, 3, 4]);
    expect(hiddenBefore(undefined)).toBe(0);
    expect(hiddenBefore(11)).toBe(10);
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%EC%A2%85%ED%83%91.html")).toBe('종탑.html');
    expect(filenameFromDisposition('attachment; filename="a/b.txt"')).toBe('a_b.txt');
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment; filename*=UTF-8''%E0%A4%A")).toBeNull();
    expect(fallbackFilename('종탑: 1부', 'txt')).toBe('종탑_ 1부.txt');
    expect(fallbackFilename('  ', 'md')).toBe('기록.md');
    expect(transcriptProblemText(new ApiError({ status: 404, detail: 'x' }))).toContain('앉아 있지 않아');
  });
});
