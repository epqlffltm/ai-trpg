// web/apps/web/src/queryClient.test.ts
// 바꾸는 요청의 답 넣기(putQueryData). 먼저 떠난 읽기가 나중에 닿아도 넣은 것이 남고, 그 읽기를 멈췄으면 다시 읽는다.
// 답이 전체이면(whole) 다시 읽지 않는다(#975).
// @vitest-environment node

import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { putQueryData } from './queryClient';

const KEY = ['probe'];

/** 답을 손으로 주는 읽기. 몇 번 불렀는지 센다 */
function slowRead(queryClient: QueryClient) {
  const calls: ((value: string) => void)[] = [];
  const read = () => new Promise<string>((resolve) => calls.push(resolve));
  queryClient.setQueryDefaults(KEY, { queryFn: read, retry: false });
  return calls;
}

describe('putQueryData', () => {
  it('바꾸기 전에 떠난 읽기가 나중에 닿아도 넣은 것이 남고, 멈춘 읽기는 다시 읽는다', async () => {
    const queryClient = new QueryClient();
    const calls = slowRead(queryClient);
    // 화면이 보고 있는 읽기다(보는 것이 없으면 다시 읽지 않는다)
    const stop = new QueryObserver(queryClient, { queryKey: KEY }).subscribe(() => undefined);
    await Promise.resolve();

    await putQueryData<string>(queryClient, KEY, 'new');
    calls[0]?.('old');
    await new Promise((resolve) => setTimeout(resolve, 0));
    stop();

    expect(queryClient.getQueryData(KEY)).toBe('new');
    // 멈춘 읽기를 대신하는 새 읽기가 떠났다(답이 일부만 고칠 때 다른 새것을 잃지 않게)
    expect(calls).toHaveLength(2);
  });

  it('답이 전체이면 멈춘 읽기를 다시 하지 않는다. 넣은 것은 남는다', async () => {
    const queryClient = new QueryClient();
    const calls = slowRead(queryClient);
    const stop = new QueryObserver(queryClient, { queryKey: KEY }).subscribe(() => undefined);
    await Promise.resolve();

    await putQueryData<string>(queryClient, KEY, 'new', { whole: true });
    calls[0]?.('old');
    await new Promise((resolve) => setTimeout(resolve, 0));
    stop();

    expect(queryClient.getQueryData(KEY)).toBe('new');
    expect(calls).toHaveLength(1);
  });

  it('보는 화면이 없는 읽기도 멈춰서, 나중에 닿은 바뀌기 전의 것이 넣은 것을 덮지 않는다', async () => {
    const queryClient = new QueryClient();
    const calls = slowRead(queryClient);
    const reading = queryClient.fetchQuery({ queryKey: KEY }).catch(() => null);

    await putQueryData<string>(queryClient, KEY, 'new');
    calls[0]?.('old');
    await reading;

    expect(queryClient.getQueryData(KEY)).toBe('new');
  });

  it('하던 읽기가 없으면 넣기만 한다. 고치는 함수는 지금 값을 받는다', async () => {
    const queryClient = new QueryClient();
    const calls = slowRead(queryClient);
    queryClient.setQueryData(KEY, 'a');

    await putQueryData<string>(queryClient, KEY, (current) => `${current ?? ''}b`);

    expect(queryClient.getQueryData(KEY)).toBe('ab');
    expect(calls).toHaveLength(0);
  });

  it('하던 읽기가 없으면 화면이 보고 있어도 다시 읽지 않는다', async () => {
    const queryClient = new QueryClient();
    const calls = slowRead(queryClient);
    queryClient.setQueryData(KEY, 'a');
    const stop = new QueryObserver(queryClient, { queryKey: KEY, staleTime: Infinity }).subscribe(() => undefined);

    await putQueryData<string>(queryClient, KEY, 'b');
    await new Promise((resolve) => setTimeout(resolve, 0));
    stop();

    expect(queryClient.getQueryData(KEY)).toBe('b');
    expect(calls).toHaveLength(0);
  });
});
