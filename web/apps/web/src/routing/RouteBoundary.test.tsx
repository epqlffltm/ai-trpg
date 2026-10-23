// web/apps/web/src/routing/RouteBoundary.test.tsx
// 코드 분할(2026-10-23)의 실패 처리. 조각을 받지 못한 오류를 가려내고, 화면 자리에만 안내와 새로 고치기 단추를 보이며,
// 다른 경로로 가면 안내를 거두는지, 처음 갈 때 받는 화면이 받은 뒤에 그려지는지 본다.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { isChunkLoadError } from './chunkError';
import { lazyPage } from './lazyPage';
import { RouteBoundary } from './RouteBoundary';

function Broken({ error }: { error: Error }): never {
  throw error;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('조각을 받지 못한 오류', () => {
  it('브라우저마다의 글을 알아보고, 다른 오류는 아니다', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/a.js'))).toBe(true);
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isChunkLoadError(new TypeError('error loading dynamically imported module: https://x/assets/a.js'))).toBe(true);
    expect(isChunkLoadError(new Error('Unable to preload CSS for /assets/a.css'))).toBe(true);
    expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe('경로의 화면이 깨지면', () => {
  it('조각을 받지 못했으면 새 버전을 알리고, 단추로 새로 고친다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const onReload = vi.fn();
    render(
      <RouteBoundary resetKey="/trpg" onReload={onReload}>
        <Broken error={new TypeError('Failed to fetch dynamically imported module: /assets/a.js')} />
      </RouteBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('새 버전이 나왔을 수 있습니다');
    await userEvent.click(screen.getByRole('button', { name: '새로 고치기' }));
    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it('다른 오류는 그리지 못했다고만 알리고, 다른 경로로 가면 거두고 다시 그린다', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const { rerender } = render(
      <RouteBoundary resetKey="/a">
        <Broken error={new Error('x')} />
      </RouteBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('화면을 그리지 못했습니다');

    rerender(
      <RouteBoundary resetKey="/a">
        <p>같은 경로</p>
      </RouteBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();

    rerender(
      <RouteBoundary resetKey="/b">
        <p>다른 화면</p>
      </RouteBoundary>,
    );
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('다른 화면')).toBeInTheDocument();
  });
});

describe('처음 갈 때 받는 화면', () => {
  it('모듈의 이름 붙은 화면을 받은 뒤에 그린다', async () => {
    const Page = lazyPage(async () => ({ HelloPage: () => <p>안녕</p> }), 'HelloPage');
    render(
      <Suspense fallback={<p>불러오는 중</p>}>
        <Page />
      </Suspense>,
    );
    expect(screen.getByText('불러오는 중')).toBeInTheDocument();
    expect(await screen.findByText('안녕')).toBeInTheDocument();
  });
});
