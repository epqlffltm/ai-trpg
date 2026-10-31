// web/apps/web/src/pages/operator/ScenarioSanction.test.tsx
// 시나리오 소개(B2)의 운영자 칸(E4, #392). 운영자가 아니면 칸이 없다. 운영자는 사유를 적어 판을 제재하고(사유가 없으면 보내지 않음),
// 제작자의 공개를 금지하고 푼다. 서버의 409(공개 중이 아님, 이미 금지, 금지 중이 아님)를 알린다. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { describeSanctionProblem } from './sanctionProblem';
import { banNotice, sanctionNotice } from './sanctionView';

const ADMIN = '/api/v1/game/admin';
const CREATOR = '00000000-0000-4000-8000-0000000000c1';
const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

const DETAIL = {
  scenario_id: SCENARIO_ID,
  creator_id: CREATOR,
  title: '잿빛 수도원',
  tagline: '',
  description: '',
  genre: null,
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 3,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
  openings: [],
  character_modes: ['custom'],
  pregens: [],
  abilities: [],
  recommended_narration_model: null,
  references_allowed: true,
};

const BAN = { user_id: CREATOR, banned: true, banned_at: '2026-10-26T00:00:00Z', banned_by: '00000000-0000-4000-8000-0000000000e1', lifted_at: null };

function signedInAs(roles: string[], routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
    'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] }),
    'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
    ...routes,
  });
}

function bodies(seen: SeenRequest[], path: string): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === `${ADMIN}${path}`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('시나리오의 운영자 칸', () => {
  it('운영자가 아니면 칸이 없다', async () => {
    signedInAs([]);
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);
    expect(await screen.findByRole('heading', { name: '잿빛 수도원' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '운영자' })).toBeNull();
    expect(screen.queryByRole('button', { name: '이 판 제재하기' })).toBeNull();
  });

  it('사유를 적어야 제재를 보내고, 제재하면 결과와 제작자의 공개 금지를 알린다', async () => {
    const { seen } = signedInAs(['operator'], {
      [`POST ${ADMIN}/scenarios/${SCENARIO_ID}/sanction`]: () => json(201, { scenario_id: SCENARIO_ID, version_number: 3, owner_id: CREATOR, publishing_banned: true }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '이 판 제재하기' }));
    const dialog = within(screen.getByRole('dialog', { name: '3판 제재' }));
    await userEvent.click(dialog.getByRole('button', { name: '제재하기' }));
    expect(dialog.getByText('사유를 적어 주세요. 감사 기록에 남습니다.')).toBeInTheDocument();
    expect(bodies(seen, `/scenarios/${SCENARIO_ID}/sanction`)).toEqual([]);

    await userEvent.type(dialog.getByLabelText('사유'), '  신고 #7  ');
    await userEvent.click(dialog.getByRole('button', { name: '제재하기' }));
    expect(await screen.findByText('3판을 제재했습니다. 공개가 내려갔고 이 판은 다시 공개하지 못합니다. 제작자는 지금 공개 금지 중입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '3판 제재' })).toBeNull();
    expect(bodies(seen, `/scenarios/${SCENARIO_ID}/sanction`)).toEqual([{ reason: '신고 #7' }]);
  });

  it('제작자의 공개를 금지하고, 이미 금지 중이면 서버의 까닭을 알리며, 풀면 결과를 알린다', async () => {
    let bans = 0;
    const { seen } = signedInAs(['operator'], {
      [`POST ${ADMIN}/users/${CREATOR}/publishing-ban`]: () => {
        bans += 1;
        return bans === 1 ? json(200, BAN) : json(409, { detail: '지금 상태에서는 할 수 없습니다.', reason: 'already_banned' });
      },
      [`POST ${ADMIN}/users/${CREATOR}/publishing-ban/lift`]: () => json(200, { ...BAN, banned: false, lifted_at: '2026-10-26T01:00:00Z' }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '제작자 공개 금지' }));
    let dialog = within(await screen.findByRole('dialog', { name: '이야기꾼의 공개 금지' }));
    await userEvent.type(dialog.getByLabelText('사유'), '반복된 위반');
    await userEvent.click(dialog.getByRole('button', { name: '공개 금지' }));
    expect(await screen.findByText('이야기꾼의 공개를 금지했습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '제작자 공개 금지' }));
    dialog = within(screen.getByRole('dialog', { name: '이야기꾼의 공개 금지' }));
    await userEvent.type(dialog.getByLabelText('사유'), '한 번 더');
    await userEvent.click(dialog.getByRole('button', { name: '공개 금지' }));
    expect(await dialog.findByText('이미 공개 금지 중인 사람입니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '닫기' }));

    await userEvent.click(screen.getByRole('button', { name: '공개 금지 풀기' }));
    dialog = within(screen.getByRole('dialog', { name: '이야기꾼의 공개 금지 풀기' }));
    await userEvent.type(dialog.getByLabelText('사유'), '이의 신청 받음');
    await userEvent.click(dialog.getByRole('button', { name: '풀기' }));
    expect(await screen.findByText('이야기꾼의 공개 금지를 풀었습니다.')).toBeInTheDocument();
    expect(bodies(seen, `/users/${CREATOR}/publishing-ban`)).toEqual([{ reason: '반복된 위반' }, { reason: '한 번 더' }]);
    expect(bodies(seen, `/users/${CREATOR}/publishing-ban/lift`)).toEqual([{ reason: '이의 신청 받음' }]);
  });

  it('순수한 함수', () => {
    expect(sanctionNotice({ scenario_id: SCENARIO_ID, version_number: 2, owner_id: CREATOR, publishing_banned: false })).toBe('2판을 제재했습니다. 공개가 내려갔고 이 판은 다시 공개하지 못합니다.');
    expect(banNotice({ ...BAN, banned: false }, '제작자')).toBe('제작자의 공개 금지를 풀었습니다.');
    expect(describeSanctionProblem(new ApiError({ status: 409, detail: 'x', code: 'not_published' })).message).toBe('공개 중인 판이 없어 제재할 것이 없습니다. 이미 내려갔을 수 있습니다.');
    expect(describeSanctionProblem(new ApiError({ status: 409, detail: 'x', code: 'not_banned' })).message).toBe('공개 금지 중이 아닌 사람입니다.');
    expect(describeSanctionProblem(new ApiError({ status: 409, detail: 'x' })).message).toBe('지금 상태에서는 할 수 없습니다.');
    expect(describeSanctionProblem(new ApiError({ status: 404, detail: 'x' })).message).toBe('찾을 수 없습니다. 지워졌거나 운영자 권한이 없습니다.');
  });
});
