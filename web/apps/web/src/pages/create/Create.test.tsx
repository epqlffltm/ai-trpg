// web/apps/web/src/pages/create/Create.test.tsx
// 만들기의 입구(Stitch 19번의 맨 앞 칸): TRPG 의 "만들 것", story 의 "JSON 으로 세계관 넣기"(운영자만), 다 고르기 전에 꺼진 "다음",
// 그리고 고른 것을 새로 만드는 화면으로 가는 길을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { TRPG_KINDS, createPath } from './createTargets';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

function signedIn(roles: string[] = []) {
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: 'u1' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
  });
}

async function openForm() {
  renderApp('/create');
  return within(await screen.findByRole('form', { name: '만들 것 고르기' }));
}

describe('만들기의 입구', () => {
  it('TRPG 를 고르면 만들 것이 나오고, 그것까지 골라야 다음이 켜져 새로 만드는 화면으로 간다', async () => {
    signedIn();
    const form = await openForm();
    expect(form.queryByRole('combobox', { name: '만들 것' })).toBeNull();

    await userEvent.selectOptions(form.getByRole('combobox', { name: '무엇을 만들까요' }), 'trpg');
    const kinds = form.getByRole('combobox', { name: '만들 것' });
    expect(within(kinds).getAllByRole('option').map((option) => option.textContent)).toEqual(['고르세요', ...TRPG_KINDS.map((one) => one.label)]);
    expect(form.getByRole('button', { name: '다음' })).toBeDisabled();

    await userEvent.selectOptions(kinds, 'bestiaries');
    await userEvent.click(form.getByRole('button', { name: '다음' }));

    expect(await screen.findByRole('heading', { name: '새 몬스터 모음 만들기' })).toBeInTheDocument();
  });

  it('story 를 고르면 운영자에게만 JSON 으로 세계관 넣기가 보인다', async () => {
    signedIn(['operator']);
    const form = await openForm();
    await userEvent.selectOptions(form.getByRole('combobox', { name: '무엇을 만들까요' }), 'story');

    expect(form.getByRole('link', { name: 'JSON 으로 세계관 넣기' })).toHaveAttribute('href', '/story/worlds/import');
    expect(form.queryByRole('combobox', { name: '만들 것' })).toBeNull();
    expect(form.getByRole('button', { name: '다음' })).toBeEnabled();
  });

  it('운영자가 아니면 story 를 골라도 JSON 으로 넣기는 없다', async () => {
    signedIn();
    const form = await openForm();
    await userEvent.selectOptions(form.getByRole('combobox', { name: '무엇을 만들까요' }), 'story');

    expect(form.queryByRole('link', { name: 'JSON 으로 세계관 넣기' })).toBeNull();
  });

  it('갈 곳: 고르지 않았거나 TRPG 의 만들 것이 비면 없다', () => {
    expect(createPath('', '')).toBeNull();
    expect(createPath('trpg', '')).toBeNull();
    expect(createPath('trpg', 'campaigns')).toBe('/trpg/studio/campaigns/new');
    expect(createPath('chat', '')).toBe('/chat/studio/characters/new');
    expect(createPath('story', '')).toBe('/story/studio/worlds/new');
  });
});
