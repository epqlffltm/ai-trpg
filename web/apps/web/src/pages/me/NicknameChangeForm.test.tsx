// web/apps/web/src/pages/me/NicknameChangeForm.test.tsx
// 마이페이지의 "닉네임 바꾸기". 바꾸면 내 정보와 머리의 이름이 바뀌고 갱신을 한 번 하는지,
// 서버가 거절하면 그 칸에 글을 보이는지, 30일 안이면 언제부터인지만 보이는지 본다.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { formatDateTime } from '../../format/dateTime';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { nicknameHint } from './NicknameChangeForm';

const NEXT_CHANGE = '2026-12-07T03:00:00Z';

const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: false, legal_adult: false, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
  nickname_change_available_at: null,
};

function signedIn(me: Record<string, unknown>, extra: Record<string, (request: SeenRequest) => Response> = {}) {
  let refreshed = 0;
  const fake = installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => {
      refreshed += 1;
      return json(200, tokens(`a${refreshed}`));
    },
    'GET /api/v1/auth/me': () => json(200, me),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 0, limit: 5 }),
    ...extra,
  });
  return { ...fake, refreshCount: () => refreshed };
}

async function fillAndSend(nickname: string, password: string) {
  await userEvent.type(await screen.findByLabelText('새 닉네임'), nickname);
  await userEvent.type(screen.getByLabelText('비밀번호 확인'), password);
  await userEvent.click(screen.getByRole('button', { name: '닉네임 바꾸기' }));
}

describe('NicknameChangeForm', () => {
  it('바꾸면 새 이름을 보이고, 갱신해 새 이름이 실린 토큰을 받는다', async () => {
    const { seen, refreshCount } = signedIn(ME, {
      'POST /api/v1/auth/me/nickname': () =>
        json(200, { nickname: '새모험가', nickname_change_available_at: NEXT_CHANGE }),
    });
    renderApp('/me');

    await fillAndSend('새모험가', 'my-pass-1234');

    expect(await screen.findByText('닉네임을 바꿨습니다. 새 닉네임은 새모험가입니다.')).toBeInTheDocument();
    expect(screen.getByText(`${formatDateTime(NEXT_CHANGE)}부터 다시 바꿀 수 있습니다.`)).toBeInTheDocument();
    expect(screen.queryByLabelText('새 닉네임')).not.toBeInTheDocument();
    expect(seen.find((request) => request.url === '/api/v1/auth/me/nickname')?.body).toEqual({
      nickname: '새모험가',
      password: 'my-pass-1234',
    });
    // 처음 열 때 한 번, 바꾼 뒤에 한 번
    expect(refreshCount()).toBe(2);
    expect(getSession()?.accessToken).toBe('a2');
  });

  it('비밀번호가 틀리면 그 칸에 서버의 글을 보이고 갱신하지 않는다', async () => {
    const { refreshCount } = signedIn(ME, {
      'POST /api/v1/auth/me/nickname': () =>
        json(400, { detail: '입력이 올바르지 않습니다.', errors: { password: ['비밀번호가 올바르지 않습니다.'] } }),
    });
    renderApp('/me');

    await fillAndSend('새모험가', 'wrong');

    expect(await screen.findByText('비밀번호가 올바르지 않습니다.')).toBeInTheDocument();
    expect(refreshCount()).toBe(1);
  });

  it('쓰이고 있는 이름이면 이름 칸에 서버의 글을 보인다', async () => {
    signedIn(ME, {
      'POST /api/v1/auth/me/nickname': () =>
        json(400, { detail: '입력이 올바르지 않습니다.', errors: { nickname: ['이미 사용 중인 닉네임입니다.'] } }),
    });
    renderApp('/me');

    await fillAndSend('남의이름', 'my-pass-1234');

    expect(await screen.findByText('이미 사용 중인 닉네임입니다.')).toBeInTheDocument();
  });

  it('30일 안이면 언제부터 바꿀 수 있는지만 보인다', async () => {
    signedIn({ ...ME, nickname_change_available_at: NEXT_CHANGE });
    renderApp('/me');

    expect(await screen.findByText(`${formatDateTime(NEXT_CHANGE)}부터 다시 바꿀 수 있습니다.`)).toBeInTheDocument();
    expect(screen.queryByLabelText('새 닉네임')).not.toBeInTheDocument();
  });

  it('규칙에 어긋나거나 지금과 같으면 보내기 전에 알린다', async () => {
    signedIn(ME);
    renderApp('/me');

    await userEvent.type(await screen.findByLabelText('새 닉네임'), '새 이름');
    await userEvent.type(screen.getByLabelText('비밀번호 확인'), 'my-pass-1234');

    expect(screen.getByText(/띄어 쓸 수 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '닉네임 바꾸기' })).toBeDisabled();
  });
});

describe('nicknameHint', () => {
  it('비었으면 말하지 않고, 규칙과 지금의 이름을 본다', () => {
    expect(nicknameHint('', '모험가')).toBeUndefined();
    expect(nicknameHint('가', '모험가')).toMatch(/2~20자/);
    expect(nicknameHint('모험가', '모험가')).toBe('지금의 닉네임과 같습니다.');
    expect(nicknameHint('새모험가', '모험가')).toBeUndefined();
  });
});
