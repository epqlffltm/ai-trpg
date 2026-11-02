// web/apps/web/src/pages/chat/conversation/ConversationBookmarks.test.tsx
// 책갈피(#982). 말 아래의 단추로 달고 떼고, 창에서 그 자리로 가고(지금 가지에 없으면 가지를 바꾼다) 메모를 고치고 뗀다.
// 가득 찼다는 서버의 답을 알린다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Bookmark } from '../../../api/bookmarks';
import { ApiError } from '../../../api/errors';
import { detail, ID, M, message, PATH, signedIn } from '../../../test/chatFixtures';
import { json, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { bookmarkProblemText, bookmarkRoleLabel, bookmarksCountLabel, isOnBranch, messageAnchor } from './bookmarksView';

const BOOKMARKS = `${PATH}/bookmarks`;

function mark(n: number, excerpt: string, extra: Partial<Bookmark> = {}): Bookmark {
  return { message_id: M(n), note: null, role: 'assistant', excerpt, created_at: '', ...extra } as Bookmark;
}

function bookmarksServer(initial: Bookmark[], extra: Record<string, (request: SeenRequest) => Response> = {}) {
  let marks = initial;
  return signedIn({
    [`GET ${BOOKMARKS}`]: () => json(200, marks),
    [`PUT ${BOOKMARKS}/${M(3)}`]: (request) => {
      const note = (request.body as { note: string }).note || null;
      marks = [mark(3, '비가 오네요.', { note }), ...marks.filter((entry) => entry.message_id !== M(3))];
      return json(200, marks[0]);
    },
    [`DELETE ${BOOKMARKS}/${M(3)}`]: () => {
      marks = marks.filter((entry) => entry.message_id !== M(3));
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
}

function requests(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('책갈피', () => {
  it('말 아래의 단추로 달고 다시 누르면 뗀다', async () => {
    const { seen } = bookmarksServer([]);
    renderApp(`/chat/conversations/${ID}`);

    const answer = await screen.findByText('비가 오네요.');
    const item = within(answer.closest('li') as HTMLElement);
    await userEvent.click(item.getByRole('button', { name: '책갈피' }));
    expect(await item.findByRole('button', { name: '책갈피 떼기' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(item.getByRole('button', { name: '책갈피 떼기' }));

    expect(await item.findByRole('button', { name: '책갈피' })).toHaveAttribute('aria-pressed', 'false');
    expect(requests(seen, 'PUT', `${BOOKMARKS}/${M(3)}`)[0]?.body).toEqual({ note: '' });
    expect(requests(seen, 'DELETE', `${BOOKMARKS}/${M(3)}`)).toHaveLength(1);
  });

  it('창에서 메모를 고치고 뗀다', async () => {
    const { seen } = bookmarksServer([mark(3, '비가 오네요.')]);
    renderApp(`/chat/conversations/${ID}`);

    const toolbar = within(await screen.findByRole('toolbar', { name: '창과 행동' }));
    await userEvent.click(toolbar.getByRole('button', { name: '책갈피' }));
    const dialog = within(await screen.findByRole('dialog', { name: '책갈피' }));
    const list = within(await dialog.findByRole('list', { name: '책갈피' }));
    expect(list.getByText('비가 오네요.')).toBeInTheDocument();
    expect(dialog.getByText('1/100')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '메모 고치기' }));
    await userEvent.type(list.getByRole('textbox', { name: '메모' }), ' 처음 웃은 날 ');
    await userEvent.click(list.getByRole('button', { name: '저장' }));
    expect(await list.findByText('메모: 처음 웃은 날')).toBeInTheDocument();
    await userEvent.click(list.getByRole('button', { name: '떼기' }));

    expect(await dialog.findByText(/아직 책갈피가 없습니다/)).toBeInTheDocument();
    expect(requests(seen, 'PUT', `${BOOKMARKS}/${M(3)}`)[0]?.body).toEqual({ note: '처음 웃은 날' });
  });

  it('지금 가지에 없는 말의 책갈피로 가면 그 가지로 바꾼다', async () => {
    const other = [message(1, 'assistant', '어서 와요.'), message(2, 'user', '안녕'), message(9, 'assistant', '다른 답이에요.', { alternatives: [M(3), M(9)] })];
    const { seen } = bookmarksServer([mark(9, '다른 답이에요.')], {
      [`PUT ${PATH}/branch`]: () => json(200, detail({ messages: other })),
    });
    renderApp(`/chat/conversations/${ID}`);

    const toolbar = within(await screen.findByRole('toolbar', { name: '창과 행동' }));
    await userEvent.click(toolbar.getByRole('button', { name: '책갈피' }));
    const dialog = within(await screen.findByRole('dialog', { name: '책갈피' }));
    await userEvent.click(await dialog.findByRole('button', { name: '이 자리로' }));

    expect(await screen.findByText('다른 답이에요.')).toBeInTheDocument();
    await waitFor(() => expect(requests(seen, 'PUT', `${PATH}/branch`)[0]?.body).toEqual({ message_id: M(9) }));
  });

  it('지금 가지의 말이면 가지를 바꾸지 않는다', async () => {
    const { seen } = bookmarksServer([mark(3, '비가 오네요.')]);
    renderApp(`/chat/conversations/${ID}`);

    const toolbar = within(await screen.findByRole('toolbar', { name: '창과 행동' }));
    await userEvent.click(toolbar.getByRole('button', { name: '책갈피' }));
    const dialog = within(await screen.findByRole('dialog', { name: '책갈피' }));
    await userEvent.click(await dialog.findByRole('button', { name: '이 자리로' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '책갈피' })).not.toBeInTheDocument());
    expect(requests(seen, 'PUT', `${PATH}/branch`)).toHaveLength(0);
    expect(document.getElementById(messageAnchor(M(3)))).not.toBeNull();
  });

  it('가득 찼다는 답을 알린다', async () => {
    bookmarksServer([], { [`PUT ${BOOKMARKS}/${M(3)}`]: () => json(409, { detail: '가득', code: 'bookmarks_full' }) });
    renderApp(`/chat/conversations/${ID}`);

    const answer = await screen.findByText('비가 오네요.');
    await userEvent.click(within(answer.closest('li') as HTMLElement).getByRole('button', { name: '책갈피' }));

    expect(await screen.findByText(/책갈피가 가득 찼습니다/)).toBeInTheDocument();
  });
});

describe('bookmarksView', () => {
  it('역할과 수, 가지, 까닭', () => {
    expect([bookmarkRoleLabel(mark(1, '')), bookmarkRoleLabel(mark(2, '', { role: 'user' }))]).toEqual(['답', '내 말']);
    expect(bookmarksCountLabel([mark(1, ''), mark(2, '')])).toBe('2/100');
    expect([isOnBranch([M(1), M(2)], M(2)), isOnBranch([M(1)], M(9))]).toEqual([true, false]);
    expect(bookmarkProblemText(new ApiError({ status: 422, detail: 'x' }))).toBe('메모는 100자까지 적습니다.');
    expect(bookmarkProblemText(new Error('x'))).toMatch(/바꾸지 못했습니다/);
  });
});
