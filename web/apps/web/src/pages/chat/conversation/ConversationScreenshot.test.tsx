// web/apps/web/src/pages/chat/conversation/ConversationScreenshot.test.tsx
// 그림으로 저장(#982). 처음과 끝을 고르면 그 사이의 말만 들어가고, 이름·장르·성인 표시와 사이트 이름을 담아 그린다.
// 그리기(canvas)는 시험 환경에 없어 가짜로 바꾸고 무엇을 넘겼는지 본다. 줄 나누기와 자리 정하기는 순수한 함수로 본다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detail, ID, signedIn } from '../../../test/chatFixtures';
import { renderApp } from '../../../test/renderApp';
import { storyShotItems } from '../../story/storyShot';
import { storyView, castOut } from '../../../test/storyFixtures';
import type { StoryMessage } from '../../../api/story';
import { contiguousRange, layoutShot, shotFileName, shotSubtitle, SITE_NAME, wrapText, type ShotItem } from './screenshotView';

const drawn = vi.hoisted(() => ({ calls: [] as unknown[][], downloads: [] as string[] }));

vi.mock('./drawShot', () => ({
  drawShot: async (...args: unknown[]) => {
    drawn.calls.push(args);
    return new Blob(['png']);
  },
  downloadBlob: (_blob: Blob, name: string) => {
    drawn.downloads.push(name);
  },
}));

afterEach(() => {
  drawn.calls.length = 0;
  drawn.downloads.length = 0;
  vi.restoreAllMocks();
});

function item(id: string, text: string): ShotItem {
  return { id, label: text, lines: [{ speaker: '루나', text }] };
}

describe('그림으로 저장', () => {
  it('고른 구간의 말만 넣고 이름과 성인 표시를 담아 그린 뒤 내려받는다', async () => {
    signedIn({}, () => detail({ character: { ...detail().character, rating: 'adult', document: { ...detail().character.document, genre: 'romance', image_id: null } } }));
    renderApp(`/chat/conversations/${ID}`);

    const toolbar = within(await screen.findByRole('toolbar', { name: '창과 행동' }));
    await userEvent.click(toolbar.getByRole('button', { name: '그림으로 저장' }));
    const dialog = within(await screen.findByRole('dialog', { name: '그림으로 저장' }));
    const list = within(dialog.getByRole('list', { name: '넣을 말' }));
    // 처음에는 끝의 두 말이 골라져 있다. 첫 말도 고르면 셋이 다 들어간다
    expect(dialog.getByText('2개의 말이 들어갑니다.')).toBeInTheDocument();
    await userEvent.click(list.getByRole('checkbox', { name: /어서 와요/ }));
    expect(dialog.getByText('3개의 말이 들어갑니다.')).toBeInTheDocument();
    // 가운데를 빼도 사이라서 들어간다
    await userEvent.click(list.getByRole('checkbox', { name: /안녕/ }));
    expect(dialog.getByText('3개의 말이 들어갑니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '그림 만들기' }));

    await waitFor(() => expect(drawn.downloads).toEqual(['루나.png']));
    const [title, subtitle, items] = drawn.calls[0] as [string, string, ShotItem[]];
    expect([title, subtitle]).toEqual(['루나', '로맨스 · 성인']);
    expect(items.map((entry) => entry.lines[0]?.text)).toEqual(['어서 와요.', '안녕', '비가 오네요.']);
  });

  it('아무것도 고르지 않으면 만들지 않는다', async () => {
    signedIn();
    renderApp(`/chat/conversations/${ID}`);

    const toolbar = within(await screen.findByRole('toolbar', { name: '창과 행동' }));
    await userEvent.click(toolbar.getByRole('button', { name: '그림으로 저장' }));
    const dialog = within(await screen.findByRole('dialog', { name: '그림으로 저장' }));
    for (const box of dialog.getAllByRole('checkbox', { checked: true })) await userEvent.click(box);

    expect(dialog.getByRole('button', { name: '그림 만들기' })).toBeDisabled();
  });
});

describe('screenshotView', () => {
  it('고른 것의 처음부터 끝까지가 구간이다', () => {
    const items = ['a', 'b', 'c', 'd'].map((id) => item(id, id));
    expect(contiguousRange(items, new Set(['b', 'd'])).map((entry) => entry.id)).toEqual(['b', 'c', 'd']);
    expect(contiguousRange(items, new Set())).toEqual([]);
  });

  it('폭에 맞춰 띄어쓰기에서, 긴 낱말은 글자에서 나누고 줄바꿈은 지킨다', () => {
    const measure = (text: string) => text.length * 10;
    expect(wrapText('하나 둘 셋 넷', 50, measure)).toEqual(['하나 둘', '셋 넷']);
    expect(wrapText('가나다라마바사', 30, measure)).toEqual(['가나다', '라마바', '사']);
    expect(wrapText('첫 줄\n둘째', 100, measure)).toEqual(['첫 줄', '둘째']);
  });

  it('제목, 부제, 말한 이와 글, 아래에 사이트 이름', () => {
    const layout = layoutShot('루나', '로맨스', [item('a', '비가 오네요.')], (text) => text.length * 10);
    expect(layout.rows.map((row) => [row.kind, row.text])).toEqual([
      ['title', '루나'],
      ['subtitle', '로맨스'],
      ['speaker', '루나'],
      ['text', '비가 오네요.'],
      ['footer', SITE_NAME],
    ]);
    expect(layout.height).toBeGreaterThan(layout.rows.at(-1)?.y ?? 0);
  });

  it('부제와 파일 이름', () => {
    expect([shotSubtitle('호러', false), shotSubtitle(null, true), shotSubtitle(null, false)]).toEqual(['호러', '성인', '']);
    expect([shotFileName('여름: 학교?'), shotFileName('  ')]).toEqual(['여름 학교.png', '대화.png']);
  });

  it('story 의 답은 조각마다 한 줄, 내 말은 "나", 행동은 말한 이가 없다', () => {
    const view = storyView({ cast: [castOut('mina', '미나')] });
    const base = { parent_id: null, status: 'complete', cast: [], created_at: '', edited: false, alternatives: [] };
    const messages = [
      { ...base, id: '1', role: 'user', content: '안녕?', segments: [] },
      { ...base, id: '2', role: 'action', content: '[행동] 공원으로 갔다.', segments: [] },
      { ...base, id: '3', role: 'assistant', content: '', segments: [{ speaker: null, text: '비가 온다.' }, { speaker: 'mina', text: '우산 있어?' }] },
    ] as unknown as StoryMessage[];

    expect(storyShotItems(messages, view).map((entry) => entry.lines)).toEqual([
      [{ speaker: '나', text: '안녕?' }],
      [{ speaker: null, text: '[행동] 공원으로 갔다.' }],
      [
        { speaker: null, text: '비가 온다.' },
        { speaker: '미나', text: '우산 있어?' },
      ],
    ]);
  });
});
