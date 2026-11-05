// web/apps/web/src/pages/chat/conversation/ChatDock.test.tsx
// 좁은 화면의 chat 대화 아래 단추 줄(Stitch 21번의 모바일). 왼쪽 열과 같은 창을 펼쳐 시트로 여는 것, 다시 누르거나 "시트 닫기"로 닫는 것을 본다.
// 숨기고 띄우는 것은 CSS 라 여기서는 상태(aria-expanded, data-sheet)만 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ID, signedIn } from '../../../test/chatFixtures';
import { renderApp } from '../../../test/renderApp';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('대화의 아래 단추 줄', () => {
  it('창 단추는 왼쪽 열과 같은 창을 펼쳐 시트로 열고, 다시 누르거나 시트 닫기로 닫는다', async () => {
    signedIn();
    renderApp(`/chat/conversations/${ID}`);

    const bar = within(await screen.findByRole('navigation', { name: '대화의 단추 줄' }));
    expect(bar.getAllByRole('button').map((button) => button.textContent)).toEqual(['지도·이동', '소지품·건네기', '상대의 차림·기억', '페르소나·모델']);
    await userEvent.click(bar.getByRole('button', { name: '소지품·건네기' }));

    expect(bar.getByRole('button', { name: '소지품·건네기' })).toHaveAttribute('aria-expanded', 'true');
    const tools = within(screen.getByRole('region', { name: '창' }));
    expect(tools.getByRole('button', { name: '소지품·건네기' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('main')).toHaveAttribute('data-sheet', 'tools');

    await userEvent.click(bar.getByRole('button', { name: '소지품·건네기' }));
    expect(screen.getByRole('main')).not.toHaveAttribute('data-sheet');

    await userEvent.click(bar.getByRole('button', { name: '페르소나·모델' }));
    await userEvent.click(screen.getByRole('button', { name: '시트 닫기' }));
    expect(screen.getByRole('main')).not.toHaveAttribute('data-sheet');
    expect(tools.getByRole('button', { name: '페르소나·모델' })).toHaveAttribute('aria-expanded', 'true');
  });
});
