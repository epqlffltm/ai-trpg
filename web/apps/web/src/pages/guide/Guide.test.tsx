// web/apps/web/src/pages/guide/Guide.test.tsx
// 이용 가이드(/guide). 로그인하지 않아도 열리고, 묶음의 목차와 접어 둔 물음(펼치면 답), 고객센터로 가는 길이 있다.
// 왼쪽 메뉴 열 맨 아래의 차례(공지, 이용 가이드, 고객센터).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { GUIDE } from './guideContent';

function signedOut() {
  installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
}

describe('이용 가이드', () => {
  it('묶음의 목차가 묶음의 제목으로 가고, 물음을 펼치면 답이 보인다', async () => {
    signedOut();
    renderApp('/guide');

    expect(await screen.findByRole('heading', { level: 1, name: '이용 가이드' })).toBeInTheDocument();
    const toc = within(screen.getByRole('navigation', { name: '가이드 목차' }));
    expect(toc.getAllByRole('link').map((link) => link.getAttribute('href'))).toEqual(GUIDE.map((section) => `#guide-${section.id}`));
    for (const section of GUIDE) expect(document.getElementById(`guide-${section.id}`)).toHaveTextContent(section.title);

    const credits = within(screen.getByRole('region', { name: '골드와 실버' }));
    const answer = credits.getByText(/골드는 산 크레딧, 실버는 무료로 받은 크레딧입니다/);
    expect(answer).not.toBeVisible();
    await userEvent.click(credits.getByText('골드와 실버는 무엇인가요?'));
    expect(answer).toBeVisible();
    expect(within(screen.getByRole('main')).getByRole('link', { name: '고객센터' })).toHaveAttribute('href', '/support');
  });

  it('왼쪽 메뉴 열 맨 아래는 공지, 이용 가이드, 고객센터의 차례다', async () => {
    signedOut();
    renderApp('/guide');

    const footer = within(await screen.findByRole('navigation', { name: '안내' }));
    expect(footer.getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['공지', '/board/notice'],
      ['이용 가이드', '/guide'],
      ['고객센터', '/support'],
    ]);
  });
});
