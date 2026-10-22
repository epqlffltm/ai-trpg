// web/apps/web/src/pages/trpg/room/character/CharacterPanel.test.tsx
// 대기실의 "내 캐릭터"(B5). 프리젠 고르기, 점수제의 총점, 주사위를 굴리고 놓기, 바꾸기, 그 사이 남이 가져간 프리젠을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME, member, OTHER, roll, roomRoutes, tableDetail } from '../../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000b5';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function open(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    ...roomRoutes(TABLE_ID, routes),
  });
}

/** 내 자리를 바꾼 테이블 */
function withMe(extra: Record<string, unknown>, tableExtra: Record<string, unknown> = {}) {
  return tableDetail(TABLE_ID, { members: [member(ME, { is_host: true, ...extra }), member(OTHER)], ...tableExtra });
}

function puts(seen: SeenRequest[]): SeenRequest[] {
  return seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/character`);
}

async function form() {
  return within(await screen.findByRole('form', { name: '캐릭터 정하기' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('CharacterPanel', () => {
  it('프리젠을 고른다. 남이 가져간 것과 죽은 것은 막는다. 정하면 요약이 보인다', async () => {
    const chosen = { character: { name: '렌', description: '렌의 설명' }, character_mode: 'pregen', pregen_index: 0 };
    const { seen } = open({ [`PUT ${BASE}/character`]: () => json(200, withMe(chosen)) });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await form();
    expect(panel.getByRole('radio', { name: '미아' })).toBeDisabled();
    expect(panel.getByRole('radio', { name: '조' })).toBeDisabled();
    expect(panel.getByRole('radio', { name: '렌' })).toBeChecked();
    await userEvent.click(panel.getByRole('button', { name: '이 캐릭터로 정하기' }));

    expect(await screen.findByRole('button', { name: '바꾸기' })).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toEqual({ mode: 'pregen', pregen_index: 0 });
    expect(screen.getByText(/시작하면 이 숫자로 시트를 받습니다/)).toBeInTheDocument();
  });

  it('점수제는 쓴 값을 보이고, 총점을 넘으면 정하기를 막는다', async () => {
    const { seen } = open({
      [`PUT ${BASE}/character`]: (request) =>
        json(200, withMe({ character: { name: '렌', description: '' }, character_mode: 'point_buy', abilities: (request.body as { abilities: unknown }).abilities })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await form();
    await userEvent.click(panel.getByRole('radio', { name: '점수로 능력치 사기' }));
    await userEvent.type(panel.getByLabelText('이름'), '렌');
    await userEvent.selectOptions(panel.getByLabelText('근력'), '14');
    await userEvent.selectOptions(panel.getByLabelText('민첩'), '12');

    expect(panel.getByText('총점 10을 넘었습니다(11).')).toBeInTheDocument();
    expect(panel.getByRole('button', { name: '이 캐릭터로 정하기' })).toBeDisabled();

    await userEvent.selectOptions(panel.getByLabelText('민첩'), '10');
    expect(panel.getByText(/남은 값 1/)).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '이 캐릭터로 정하기' }));

    expect(await screen.findByRole('button', { name: '바꾸기' })).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toEqual({
      mode: 'point_buy',
      name: '렌',
      description: '',
      abilities: { str: 14, dex: 10, con: 8 },
    });
  });

  it('주사위를 굴리고, 굴린 점수를 하나씩 놓는다. 다시 굴리려면 방장의 허락이 필요하다', async () => {
    const rolled = withMe({ roll: roll([15, 12, 9]) });
    const { seen } = open({
      [`POST ${BASE}/character/roll`]: () => json(200, rolled),
      [`PUT ${BASE}/character`]: () => json(200, withMe({ character: { name: '렌', description: '' }, character_mode: 'rolled' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await form();
    await userEvent.click(panel.getByRole('radio', { name: '주사위로 굴린 점수 놓기' }));
    await userEvent.type(panel.getByLabelText('이름'), '렌');
    expect(panel.getByText('먼저 주사위를 굴려 주세요.')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '주사위 굴리기' }));

    expect(await panel.findByRole('list', { name: '굴린 점수' })).toBeInTheDocument();
    expect(panel.getByText('다시 굴리려면 방장이 "한 번 더"를 줘야 합니다.')).toBeInTheDocument();
    await userEvent.selectOptions(panel.getByLabelText('근력'), '1번 · 15');
    expect(within(panel.getByLabelText('민첩')).getByRole('option', { name: '1번 · 15' })).toBeDisabled();
    await userEvent.selectOptions(panel.getByLabelText('민첩'), '3번 · 9');
    await userEvent.selectOptions(panel.getByLabelText('건강'), '2번 · 12');
    await userEvent.click(panel.getByRole('button', { name: '이 캐릭터로 정하기' }));

    expect(await screen.findByRole('button', { name: '바꾸기' })).toBeInTheDocument();
    expect(puts(seen)[0]?.body).toMatchObject({ mode: 'rolled', abilities: { str: 15, dex: 9, con: 12 } });
  });

  it('바꾸기는 정해 둔 것으로 채우고, 그대로 두면 요약으로 돌아간다', async () => {
    open({
      [`GET ${BASE}`]: () =>
        json(200, withMe({ character: { name: '카이', description: '떠돌이' }, character_mode: 'custom' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '바꾸기' }));
    const panel = await form();
    expect(panel.getByRole('radio', { name: '이름과 설명만 쓰기' })).toBeChecked();
    expect(panel.getByLabelText('이름')).toHaveValue('카이');
    expect(panel.getByRole('button', { name: '이 캐릭터로 바꾸기' })).toBeEnabled();
    await userEvent.click(panel.getByRole('button', { name: '그대로 두기' }));

    expect(await screen.findByRole('button', { name: '바꾸기' })).toBeInTheDocument();
  });

  it('그 사이 남이 프리젠을 가져갔으면 알리고 테이블을 다시 읽는다', async () => {
    let reads = 0;
    open({
      [`GET ${BASE}`]: () => {
        reads += 1;
        const pregens = reads > 1 ? { pregens: [{ ...firstPregen(), taken_by: OTHER }, ...restPregens()] } : {};
        return json(200, tableDetail(TABLE_ID, pregens));
      },
      [`PUT ${BASE}/character`]: () => json(409, { detail: '이미 가져갔다', reason: 'pregen_taken' }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const panel = await form();
    await userEvent.click(panel.getByRole('button', { name: '이 캐릭터로 정하기' }));

    expect(await panel.findByText(/다른 사람이 가져간 프리젠입니다/)).toBeInTheDocument();
    await vi.waitFor(() => expect(panel.getByRole('radio', { name: '렌' })).toBeDisabled());
  });
});

function firstPregen() {
  return (tableDetail(TABLE_ID).pregens as Record<string, unknown>[])[0];
}

function restPregens() {
  return (tableDetail(TABLE_ID).pregens as Record<string, unknown>[]).slice(1);
}
