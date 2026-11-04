// web/apps/web/src/pages/chat/conversation/ConversationSnapshots.test.tsx
// 장면 그림(#983). 상대의 답 아래의 "장면 그림"으로 그리기를 시작하고, 그리는 동안 목록을 다시 읽어 다 그린 그림을 띄운다.
// 그리는 중이면 새로 그리지 못한다. 실패로 남은 것과 시작하지 못한 까닭을 알린다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import type { Snapshot } from '../../../api/snapshots';
import { AT, ID, M, PATH, signedIn } from '../../../test/chatFixtures';
import { json, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { isDrawing, snapshotFailureText, snapshotProblemText, snapshotsOf } from './snapshotsView';

const SNAPSHOTS = `${PATH}/snapshots`;
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
