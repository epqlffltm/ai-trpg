// web/apps/web/src/pages/wallet/WalletCatchUp.test.tsx
// 늦게 들어오는 돈의 따라잡기. 잔액이 바뀔 때까지 정한 사이마다 다시 읽고, 바뀌면 원장까지 무르고 멈춘다.
// 끝까지 그대로면 정한 횟수만 읽고 멈추고, 화면이 사라지면 읽지 않는다. 전의 잔액이 없으면 지금 것을 읽어 기준으로 삼는다.
// 잔액이 바뀌었는지 보는 순수한 함수.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { installFakeFetch, json } from '../../test/fakeFetch';
import { useWalletCatchUp } from './useWalletCatchUp';
import { walletChanged } from './walletCatchUp';
import { walletEntriesQuery, walletQuery } from './walletQueries';

const OLD = { paid: '0', free: '10', total: '10', next_expiry: null };
const NEW = { paid: '0', free: '15', total: '15', next_expiry: null };

function setup(answers: (typeof OLD)[]) {
  let reads = 0;
  installFakeFetch({
    'GET /api/v1/billing/wallet': () => {
      const answer = answers[Math.min(reads, answers.length - 1)];
      reads += 1;
      return json(200, answer);
    },
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(walletQuery().queryKey, OLD);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  return { queryClient, wrapper, reads: () => reads };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('지갑의 따라잡기', () => {
  it('잔액이 바뀔 때까지 다시 읽고, 바뀌면 원장까지 무르고 멈춘다', async () => {
    const { queryClient, wrapper, reads } = setup([OLD, OLD, NEW]);
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useWalletCatchUp([100, 100, 100, 100]), { wrapper });

    act(() => result.current.start(OLD));
    await act(() => vi.advanceTimersByTimeAsync(1_000));

    expect(reads()).toBe(3);
    expect(queryClient.getQueryData(walletQuery().queryKey)).toEqual(NEW);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: walletEntriesQuery().queryKey.slice(0, 2) });
  });

  it('끝까지 그대로면 정한 횟수만 읽고 멈춘다', async () => {
    const { wrapper, reads } = setup([OLD]);
    const { result } = renderHook(() => useWalletCatchUp([100, 100, 100]), { wrapper });

    act(() => result.current.start(OLD));
    await act(() => vi.advanceTimersByTimeAsync(5_000));

    expect(reads()).toBe(3);
  });

  it('화면이 사라지면 더 읽지 않는다', async () => {
    const { wrapper, reads } = setup([OLD]);
    const { result, unmount } = renderHook(() => useWalletCatchUp([100, 100, 100]), { wrapper });

    act(() => result.current.start(OLD));
    await act(() => vi.advanceTimersByTimeAsync(150));
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(5_000));

    expect(reads()).toBe(1);
  });

  it('읽는 중에 화면이 사라지면 읽은 뒤에도 다음을 잡지 않는다', async () => {
    const { wrapper, reads } = setup([NEW]);
    const { result, unmount } = renderHook(() => useWalletCatchUp([100, 100, 100]), { wrapper });

    // 기준을 읽는 중에 사라진다
    act(() => result.current.startFresh());
    unmount();
    await act(() => vi.advanceTimersByTimeAsync(5_000));

    expect(reads()).toBe(1);
  });

  it('startFresh 는 지금 잔액을 읽어 기준으로 삼는다. 읽어 둔 것이 오래돼도 바로 멈추지 않는다', async () => {
    // 읽어 둔 것(OLD)과 지금 것(NEW)이 다르다. 그다음에 바뀐다
    const NEWER = { ...NEW, free: '14', total: '14' };
    const { queryClient, wrapper, reads } = setup([NEW, NEW, NEWER]);
    const { result } = renderHook(() => useWalletCatchUp([100, 100, 100, 100]), { wrapper });

    act(() => result.current.startFresh());
    await act(() => vi.advanceTimersByTimeAsync(1_000));

    // 기준 읽기 하나, 그대로인 것 하나, 바뀐 것 하나, 바뀌어 무른 뒤 다시 읽기는 지켜보는 화면이 없어 없다
    expect(reads()).toBe(3);
    expect(queryClient.getQueryData(walletQuery().queryKey)).toEqual(NEWER);
  });

  it('잔액이 바뀌었는가: 골드나 실버가 다르면, 전의 잔액을 모르면 바뀐 것', () => {
    expect(walletChanged(OLD, OLD)).toBe(false);
    expect(walletChanged(OLD, NEW)).toBe(true);
    expect(walletChanged(OLD, { ...OLD, paid: '3' })).toBe(true);
    expect(walletChanged(undefined, OLD)).toBe(true);
  });
});
