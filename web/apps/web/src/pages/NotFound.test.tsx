// web/apps/web/src/pages/NotFound.test.tsx
// 찾을 수 없음(Stitch 8번). 없는 주소로 오면 사이트의 틀 안에 큰 404, 제목, 한 줄, 첫 화면으로 가는 단추를 보인다.

import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('찾을 수 없음', () => {
  it('없는 주소면 404 와 제목, 첫 화면으로 가는 단추를 사이트의 틀 안에 보인다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp('/no-such-place');

    expect(await screen.findByRole('heading', { level: 1, name: '찾을 수 없습니다' })).toBeInTheDocument();
    expect(screen.getByText('404')).toBeInTheDocument();
    expect(screen.getByText('주소가 바뀌었거나 없는 화면입니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '첫 화면으로' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: '게시판' })).toBeInTheDocument();
  });
});
