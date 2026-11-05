// web/apps/web/src/pages/chat/conversation/ChatTools.test.tsx
// 대화(C3)의 왼쪽 열 창 넷(Stitch 21번). 맨 앞의 창(지도가 있으면 지도·이동)이 펼쳐져 있는 것,
// 창이 하나만 펼쳐지고 다시 누르면 접히는 것, 페르소나·모델의 보기와 "모델 바꾸기"가 고르는 창을 여는 것을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detail, signedIn, ID } from '../../../test/chatFixtures';
import { renderApp } from '../../../test/renderApp';
import { chatTools } from './ChatTools';

afterEach(() => {
  vi.restoreAllMocks();
});

async function tools() {
  return within(await screen.findByRole('region', { name: '창' }));
}

describe('대화의 창 넷', () => {
  it('맨 앞의 지도·이동이 펼쳐져 있다. 하나만 펼치고 다시 누르면 접는다', async () => {
    signedIn();
    renderApp(`/chat/conversations/${ID}`);

    const column = await tools();
    const toggles = column.getAllByRole('button').filter((button) => button.hasAttribute('aria-expanded'));
    expect(toggles.map((button) => button.textContent)).toEqual(['지도·이동', '소지품·건네기', '상대의 차림·기억', '페르소나·모델']);
    expect(column.getByRole('button', { name: '지도·이동' })).toHaveAttribute('aria-expanded', 'true');
    expect(column.getByText('지금 있는 곳: 카페')).toBeInTheDocument();

    await userEvent.click(column.getByRole('button', { name: '페르소나·모델' }));
    expect(column.getByRole('button', { name: '지도·이동' })).toHaveAttribute('aria-expanded', 'false');
    expect(column.queryByText('지금 있는 곳: 카페')).toBeNull();

    await userEvent.click(column.getByRole('button', { name: '페르소나·모델' }));
    expect(column.getByRole('button', { name: '페르소나·모델' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('페르소나·모델은 지금의 페르소나와 모델을 보이고, 모델 바꾸기가 고르는 창을 연다', async () => {
    signedIn({ 'GET /api/v1/chat/models': () => new Response(JSON.stringify({ free: false, items: [] }), { headers: { 'Content-Type': 'application/json' } }) }, () =>
      detail({ persona: { name: '여행자' } as ReturnType<typeof detail>['persona'] }),
    );
    renderApp(`/chat/conversations/${ID}`);

    const column = await tools();
    await userEvent.click(column.getByRole('button', { name: '페르소나·모델' }));
    const panel = within(column.getByRole('region', { name: '페르소나·모델' }));
    expect(panel.getByText('여행자')).toBeInTheDocument();
    expect(panel.getByText('GLM')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '모델 바꾸기' }));

    expect(await screen.findByRole('dialog', { name: '모델 고르기' })).toBeInTheDocument();
  });
});

describe('chatTools', () => {
  it('지도가 있으면 지도·이동이 맨 앞이고, 없으면 지도·이동이 없다', () => {
    expect(chatTools(true)).toEqual(['map', 'items', 'partner', 'persona']);
    expect(chatTools(false)).toEqual(['items', 'partner', 'persona']);
  });
});
