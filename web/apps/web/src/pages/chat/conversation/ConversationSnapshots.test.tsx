// web/apps/web/src/pages/chat/conversation/ConversationSnapshots.test.tsx
// 장면 그림(#983). 상대의 답 아래의 "장면 그림"으로 그리기를 시작하고, 그리는 동안 목록을 다시 읽어 다 그린 그림을 띄운다.
// 그리는 중이면 새로 그리지 못한다. 실패로 남은 것과 시작하지 못한 까닭을 알린다.
// 단추에 한 장의 값을 싣고, 그 서버에서 그릴 수 없으면 단추를 숨긴다.
// 그림 아래에 "AI 가 만든 그림"을 적고, 누르면 크게 보는 창에서 받아 둔 바이트를 저장한다.
// 창에서 한 번 더 확인한 뒤 지우고 목록을 다시 읽는다. 지우지 못한 까닭을 알린다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { Snapshot, SnapshotPrice } from '../../../api/snapshots';
import { AT, ID, M, PATH, signedIn } from '../../../test/chatFixtures';
import { json, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { isSnapshotList } from './useDeleteSnapshot';
import {
  AI_IMAGE_NOTE,
  canOfferSnapshot,
  isDrawing,
  snapshotButtonHint,
  snapshotButtonLabel,
  snapshotFailureText,
  snapshotFileName,
  snapshotDeleteProblemText,
  snapshotProblemText,
  snapshotsOf,
} from './snapshotsView';

const saved = vi.hoisted(() => ({ names: [] as string[] }));
vi.mock('../../../components/saveFile', () => ({
  saveBlob: (_blob: Blob, name: string) => {
    saved.names.push(name);
  },
}));

const SNAPSHOTS = `${PATH}/snapshots`;
const PRICE = '/api/v1/chat/snapshots/price';
const DRAW = `/api/v1/chat/messages/${M(3)}/snapshot`;
const IMAGE = '00000000-0000-4000-8000-00000000a983';
const S = (n: number) => `00000000-0000-4000-8000-0000000b983${n}`;

function shot(n: number, status: string, extra: Partial<Snapshot> = {}): Snapshot {
  return { id: S(n), message_id: M(3), status, image_id: null, code: null, created_at: AT, ...extra } as Snapshot;
}

function snapshotsServer(list: () => Snapshot[], extra: Record<string, (request: SeenRequest) => Response> = {}) {
  return signedIn({
    [`GET ${SNAPSHOTS}`]: () => json(200, list()),
    [`GET /api/v1/asset/images/${IMAGE}`]: () => new Response('png', { status: 200 }),
    ...extra,
  });
}

function answerItem(text: string) {
  return within(screen.getByText(text).closest('li') as HTMLElement);
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('장면 그림', () => {
  it('답 아래의 단추로 그리기를 시작하고, 다 그리면 그림이 보인다', async () => {
    let list: Snapshot[] = [];
    const { seen } = snapshotsServer(() => list, {
      [`POST ${DRAW}`]: () => {
        list = [shot(1, 'drawing')];
        return json(202, list[0]);
      },
    });
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');
    await userEvent.click(answerItem('비가 오네요.').getByRole('button', { name: '장면 그림' }));
    expect(await answerItem('비가 오네요.').findByText('장면 그림을 그리는 중…')).toBeInTheDocument();
    expect(answerItem('어서 와요.').getByRole('button', { name: '장면 그림' })).toBeDisabled();
    list = [shot(1, 'ready', { image_id: IMAGE })];

    await waitFor(() => expect(answerItem('비가 오네요.').getByAltText('장면 그림')).toHaveAttribute('src', 'blob:image'), { timeout: 5000 });
    expect(answerItem('어서 와요.').getByRole('button', { name: '장면 그림' })).toBeEnabled();
    expect(seen.filter((request) => request.method === 'POST' && request.url === DRAW)).toHaveLength(1);
  });

  it('그림 아래에 AI 표시가 있고, 크게 보는 창에서 저장한다', async () => {
    saved.names.length = 0;
    snapshotsServer(() => [shot(1, 'ready', { image_id: IMAGE })]);
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');
    const answer = answerItem('비가 오네요.');
    const open = await answer.findByRole('button', { name: '장면 그림 크게 보기' });
    expect(answer.getByText(AI_IMAGE_NOTE)).toBeInTheDocument();
    await userEvent.click(open);
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));
    await userEvent.click(dialog.getByRole('button', { name: '이 기기에 저장' }));

    expect(dialog.getByText(AI_IMAGE_NOTE)).toBeInTheDocument();
    expect(dialog.getByAltText('장면 그림(크게)')).toHaveAttribute('src', 'blob:image');
    expect(saved.names).toEqual([snapshotFileName(IMAGE, '')]);
  });

  it('크게 보는 창에서 한 번 더 확인한 뒤 지우고 목록을 다시 읽는다', async () => {
    let list = [shot(1, 'ready', { image_id: IMAGE })];
    const { seen } = snapshotsServer(() => list, {
      [`DELETE /api/v1/chat/snapshots/${S(1)}`]: () => {
        list = [];
        return new Response(null, { status: 204 });
      },
    });
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');
    await userEvent.click(await answerItem('비가 오네요.').findByRole('button', { name: '장면 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    expect(dialog.getByText(/돌려받지 못하고/)).toBeInTheDocument();
    expect(seen.some((request) => request.method === 'DELETE')).toBe(false);
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '장면 그림' })).not.toBeInTheDocument());
    await waitFor(() => expect(answerItem('비가 오네요.').queryByAltText('장면 그림')).not.toBeInTheDocument());
    expect(seen.filter((request) => request.method === 'DELETE').map((request) => request.url)).toEqual([`/api/v1/chat/snapshots/${S(1)}`]);
  });

  it('지우지 못하면 창에 까닭을 알리고 그만둘 수 있다', async () => {
    snapshotsServer(() => [shot(1, 'ready', { image_id: IMAGE })], {
      [`DELETE /api/v1/chat/snapshots/${S(1)}`]: () => json(409, { detail: '정리 중', code: 'snapshot_settling' }),
    });
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');
    await userEvent.click(await answerItem('비가 오네요.').findByRole('button', { name: '장면 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '장면 그림' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    await userEvent.click(dialog.getByRole('button', { name: '지우기 확인' }));

    expect(await dialog.findByText(/청구를 정리하는 중입니다/)).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '그만두기' }));
    expect(dialog.getByRole('button', { name: '지우기' })).toBeInTheDocument();
  });

  it('단추에 한 장의 값을 싣는다', async () => {
    snapshotsServer(() => [], { [`GET ${PRICE}`]: () => json(200, { available: true, credits: '160', tier: 'standard', promo: false }) });
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');

    const button = await answerItem('비가 오네요.').findByRole('button', { name: '장면 그림 · 160' });
    expect(button).toHaveAttribute('title', '160 크레딧을 씁니다. 그리지 못하면 돌려받습니다.');
  });

  it('그 서버에서 그릴 수 없으면 단추를 숨긴다', async () => {
    const { seen } = snapshotsServer(() => [], { [`GET ${PRICE}`]: () => json(200, { available: false, credits: null, tier: null, promo: false }) });
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');
    await waitFor(() => expect(seen.some((request) => request.url === PRICE)).toBe(true));

    await waitFor(() => expect(answerItem('비가 오네요.').queryByRole('button', { name: /장면 그림/ })).not.toBeInTheDocument());
  });

  it('내 말에는 단추가 없다', async () => {
    snapshotsServer(() => []);
    renderApp(`/chat/conversations/${ID}`);

    await screen.findByText('비가 오네요.');

    expect(answerItem('안녕').queryByRole('button', { name: '장면 그림' })).not.toBeInTheDocument();
  });

  it('실패로 남은 것과 시작하지 못한 까닭을 알린다', async () => {
    snapshotsServer(() => [shot(1, 'failed', { code: 'refused' })], {
      [`POST ${DRAW}`]: () => json(409, { detail: '그리는 중', code: 'snapshot_in_progress' }),
    });
    renderApp(`/chat/conversations/${ID}`);

    expect(await screen.findByText(/안전 규칙에 걸려/)).toBeInTheDocument();
    await userEvent.click(answerItem('비가 오네요.').getByRole('button', { name: '장면 그림' }));

    expect(await screen.findByText(/다른 그림을 그리는 중입니다/)).toBeInTheDocument();
  });
});

describe('장면 그림의 글과 고르기', () => {
  it('그 말의 그림만 고르고, 지난 실패는 숨긴다', () => {
    const list = [shot(1, 'failed', { code: 'refused' }), shot(2, 'ready', { image_id: IMAGE }), shot(3, 'ready', { message_id: M(1) })];
    expect(snapshotsOf(list, M(3)).map((item) => item.id)).toEqual([S(2)]);
    expect(snapshotsOf([...list, shot(4, 'failed')], M(3)).map((item) => item.id)).toEqual([S(2), S(4)]);
  });

  it('값과 판매 상태로 단추의 글과 설명을 만든다', () => {
    const price = (extra: Partial<SnapshotPrice>) => ({ available: true, credits: '160', tier: 'standard', promo: false, ...extra }) as SnapshotPrice;
    expect(snapshotButtonLabel(undefined)).toBe('장면 그림');
    expect(snapshotButtonLabel(price({ credits: null }))).toBe('장면 그림');
    expect(snapshotButtonLabel(price({}))).toBe('장면 그림 · 160');
    expect(snapshotButtonHint(price({ tier: 'premium', promo: true }))).toBe('160 크레딧을 씁니다 · 골드로만 · 행사가. 그리지 못하면 돌려받습니다.');
    expect(snapshotButtonHint(undefined)).toBe('크레딧을 씁니다. 그리지 못하면 돌려받습니다.');
    expect([canOfferSnapshot(undefined), canOfferSnapshot(price({})), canOfferSnapshot(price({ available: false }))]).toEqual([true, true, false]);
  });

  it('저장할 파일의 이름은 형식을 따른다', () => {
    expect(snapshotFileName(IMAGE, 'image/webp')).toBe('장면그림-00000000.webp');
    expect(snapshotFileName(IMAGE, 'image/jpeg')).toBe('장면그림-00000000.jpg');
    expect(snapshotFileName(IMAGE, 'text/plain')).toBe('장면그림-00000000.png');
  });

  it('지우지 못한 까닭과 다시 읽을 목록', () => {
    expect(snapshotDeleteProblemText(new ApiError({ status: 404, detail: '', code: 'snapshot_not_found' }))).toMatch(/이미 지웠거나/);
    expect(snapshotDeleteProblemText(new ApiError({ status: 409, detail: '', code: 'snapshot_in_progress' }))).toMatch(/그리는 중/);
    expect(snapshotDeleteProblemText(new Error('x'))).toMatch(/지우지 못했습니다/);
    expect(isSnapshotList('chat', { queryKey: ['chat', 'conversation', 'c1', 'snapshots'] })).toBe(true);
    expect(isSnapshotList('chat', { queryKey: ['chat', 'snapshots', 'kept'] })).toBe(true);
    expect(isSnapshotList('chat', { queryKey: ['chat', 'snapshots', 'price'] })).toBe(false);
    expect(isSnapshotList('chat', { queryKey: ['story', 'snapshots', 'kept'] })).toBe(false);
    expect(isSnapshotList('chat', { queryKey: ['chat', 'conversation', 'c1', 'bookmarks'] })).toBe(false);
  });

  it('그리는 중인 것이 있는가', () => {
    expect(isDrawing([shot(1, 'ready'), shot(2, 'drawing')])).toBe(true);
    expect(isDrawing([shot(1, 'failed')])).toBe(false);
  });

  it('까닭마다 글이 다르다', () => {
    expect(snapshotFailureText('credit_short')).toMatch(/크레딧이 모자라/);
    expect(snapshotFailureText('asset_unavailable')).toMatch(/돌려드렸습니다/);
    expect(snapshotProblemText(new ApiError({ status: 402, detail: '', code: 'credit_short' }))).toMatch(/충전/);
    expect(snapshotProblemText(new ApiError({ status: 503, detail: '', code: 'snapshot_unavailable' }))).toMatch(/만들 수 없습니다/);
    expect(snapshotProblemText(new ApiError({ status: 422, detail: '', code: 'not_drawable' }))).toMatch(/캐릭터의 답만/);
    expect(snapshotProblemText(new Error('x'))).toMatch(/시작하지 못했습니다/);
  });
});
