// web/apps/web/src/pages/chat/conversation/ConversationNotes.test.tsx
// 기억 창(C5). 받아들인 메모와 요약이 제안한 메모를 나눠 보이고, 더하기·고치기·지우기·받아들이기·버리기를 보낸다.
// 가득 차면 더하기를 막고, 서버가 가득 찼다고 하면 까닭을 알린다. 앞의 줄거리(요약)는 읽기만. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { MemoryNote } from '../../../api/chatNotes';
import { ApiError } from '../../../api/errors';
import { ID, PATH, signedIn } from '../../../test/chatFixtures';
import { json, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { noteHint, noteProblemText, notesCountLabel, notesFull, splitNotes } from './notesView';

const NOTES = `${PATH}/notes`;
const N = (n: number) => `00000000-0000-4000-8000-00000000f40${n}`;

function note(n: number, text: string, extra: Partial<MemoryNote> = {}): MemoryNote {
  return { id: N(n), text, source: 'user', pending: false, accepted_at: null, created_at: '', updated_at: '', ...extra };
}

function notesServer(initial: MemoryNote[], extra: Record<string, (request: SeenRequest) => Response> = {}) {
  let notes = initial;
  return signedIn({
    [`GET ${NOTES}`]: () => json(200, notes),
    [`GET ${PATH}/summary`]: () => json(200, { text: '둘은 비 오는 날 카페에서 처음 만났다.', covered_up_to: N(9), created_at: '' }),
    [`POST ${NOTES}`]: (request) => {
      const added = note(8, (request.body as { text: string }).text);
      notes = [...notes, added];
      return json(201, added);
    },
    [`PATCH ${NOTES}/${N(1)}`]: (request) => {
      notes = notes.map((entry) => (entry.id === N(1) ? { ...entry, text: (request.body as { text: string }).text } : entry));
      return json(200, notes[0]);
    },
    [`DELETE ${NOTES}/${N(1)}`]: () => {
      notes = notes.filter((entry) => entry.id !== N(1));
      return new Response(null, { status: 204 });
    },
    [`POST ${NOTES}/${N(2)}/accept`]: () => {
      notes = notes.map((entry) => (entry.id === N(2) ? { ...entry, pending: false, accepted_at: 'x' } : entry));
      return json(200, notes[1]);
    },
    [`DELETE ${NOTES}/${N(3)}`]: () => {
      notes = notes.filter((entry) => entry.id !== N(3));
      return new Response(null, { status: 204 });
    },
    ...extra,
  });
}

function bodies(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body ?? null);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('기억 창', () => {
  it('메모와 제안을 나눠 보이고, 더하고 고치고 받아들이고 버리고 지운다. 줄거리는 읽기만', async () => {
    const { seen } = notesServer([
      note(1, '우산을 빌려줬다'),
      note(2, '홍차를 좋아한다', { source: 'summary', pending: true }),
      note(3, '고양이를 키운다', { source: 'summary', pending: true }),
    ]);
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '기억' }));
    const dialog = within(await screen.findByRole('dialog', { name: '기억' }));
    const kept = within(await dialog.findByRole('list', { name: '기억 메모' }));
    expect(kept.getByText('우산을 빌려줬다')).toBeInTheDocument();
    expect(dialog.getByText('1 / 20')).toBeInTheDocument();
    expect(within(dialog.getByRole('list', { name: '요약이 제안한 메모' })).getAllByText('요약이 제안')).toHaveLength(2);
    expect(dialog.getByText('둘은 비 오는 날 카페에서 처음 만났다.')).toBeInTheDocument();

    await userEvent.type(dialog.getByRole('textbox', { name: '새 메모' }), '  비를 싫어한다 ');
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));
    expect(await kept.findByText('비를 싫어한다')).toBeInTheDocument();
    expect(dialog.getByRole('textbox', { name: '새 메모' })).toHaveValue('');

    await userEvent.click(kept.getByRole('button', { name: '고치기: 우산을 빌려줬다' }));
    const box = kept.getByRole('textbox', { name: '고칠 메모' });
    await userEvent.clear(box);
    await userEvent.type(box, '우산을 두 번 빌려줬다');
    await userEvent.click(kept.getByRole('button', { name: '저장' }));
    expect(await kept.findByText('우산을 두 번 빌려줬다')).toBeInTheDocument();

    await userEvent.click(dialog.getAllByRole('button', { name: '받아들이기' })[0] as HTMLElement);
    await vi.waitFor(() => expect(kept.getByText('홍차를 좋아한다')).toBeInTheDocument());
    await userEvent.click(dialog.getByRole('button', { name: '버리기: 고양이를 키운다' }));
    await vi.waitFor(() => expect(dialog.queryByRole('list', { name: '요약이 제안한 메모' })).toBeNull());
    await userEvent.click(kept.getByRole('button', { name: '지우기: 우산을 두 번 빌려줬다' }));
    await vi.waitFor(() => expect(kept.queryByText('우산을 두 번 빌려줬다')).toBeNull());

    expect(bodies(seen, 'POST', NOTES)).toEqual([{ text: '비를 싫어한다' }]);
    expect(bodies(seen, 'PATCH', `${NOTES}/${N(1)}`)).toEqual([{ text: '우산을 두 번 빌려줬다' }]);
    expect(bodies(seen, 'POST', `${NOTES}/${N(2)}/accept`)).toHaveLength(1);
  });

  it('스물이면 더하기를 막고, 서버가 가득 찼다고 하면 까닭을 알린다', async () => {
    const twenty = Array.from({ length: 20 }, (_, index) => note(index + 10, `메모 ${index}`));
    notesServer([...twenty, note(2, '제안', { source: 'summary', pending: true })], {
      [`POST ${NOTES}/${N(2)}/accept`]: () => json(409, { detail: 'x', code: 'notes_full' }),
    });
    renderApp(`/chat/conversations/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '기억' }));
    const dialog = within(await screen.findByRole('dialog', { name: '기억' }));
    expect(await dialog.findByText('메모가 가득 찼습니다. 지운 뒤에 더합니다.')).toBeInTheDocument();
    expect(dialog.queryByRole('textbox', { name: '새 메모' })).toBeNull();
    expect(dialog.getByRole('button', { name: '받아들이기' })).toBeDisabled();
  });
});

describe('기억의 순수한 함수', () => {
  it('나누기, 수, 검사, 실패의 글', () => {
    const notes = [note(1, '가'), note(2, '나', { pending: true, source: 'summary' })];
    expect(splitNotes(notes).kept.map((entry) => entry.text)).toEqual(['가']);
    expect(splitNotes(notes).suggested.map((entry) => entry.text)).toEqual(['나']);
    expect(notesCountLabel([note(1, '가')])).toBe('1 / 20');
    expect(notesFull(Array.from({ length: 20 }, (_, index) => note(index, 'x')))).toBe(true);
    expect(noteHint(' ')).toBe('메모를 적어 주세요.');
    expect(noteHint('가'.repeat(301))).toBe('300자까지입니다.');
    expect(noteHint('가')).toBeUndefined();
    expect(noteProblemText(new ApiError({ status: 409, detail: 'x', code: 'notes_full' }))).toContain('20개까지');
    expect(noteProblemText(new ApiError({ status: 429, detail: 'x', code: 'too_many_attempts', retryAfter: 7 }))).toContain('7초 뒤에');
  });
});
