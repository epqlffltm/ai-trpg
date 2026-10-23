// web/apps/web/src/pages/trpg/studio/collection/Collections.test.tsx
// 묶음 재료(B9). 로어북: 만들고 항목을 창에서 더하기(인물의 지목할 이름), 종류로 거르기, 고치기, 지우기, 가득 찼을 때(409).
// 몬스터 모음: 몬스터를 더하는 본문(네임드). 입력의 순수한 함수(쉼표로 나누기, 겹침, 인물이 아니면 이름을 보내지 않음).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME } from '../../../../test/tableFixtures';
import { entryHints, newEntryDraft, toEntryBody } from '../lorebooks/entryForm';
import { splitWords, wordsHint } from './collectionForm';
import { itemsOfKind, kindCounts, preview } from './itemsView';

const LORE = '/api/v1/game/lorebooks';
const BEAST = '/api/v1/game/bestiaries';
const ID = '00000000-0000-4000-8000-0000000000c3';

function summary(title: string) {
  return { id: ID, title, description: '', visibility: 'private', created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z' };
}

function entry(id: string, name: string, kind: string, extra: Record<string, unknown> = {}) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z', ...extra };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, url: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === url);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('로어북', () => {
  it('만들면 그 로어북으로 가고, 창에서 인물 항목을 더하면 목록에 나온다', async () => {
    let entries: unknown[] = [];
    const { seen } = signedIn({
      [`POST ${LORE}`]: () => json(201, summary('수도원')),
      [`GET ${LORE}/${ID}`]: () => json(200, summary('수도원')),
      [`GET ${LORE}/${ID}/entries`]: () => json(200, entries),
      [`POST ${LORE}/${ID}/entries`]: (request) => {
        const body = request.body as Record<string, unknown>;
        entries = [entry('e1', body.name as string, body.kind as string, body)];
        return json(201, entries[0]);
      },
    });
    renderApp('/trpg/studio/lorebooks/new');

    const form = within(await screen.findByRole('form', { name: '로어북' }));
    await userEvent.type(form.getByLabelText('제목'), '수도원');
    await userEvent.click(form.getByRole('button', { name: '만들기' }));
    expect(await screen.findByRole('heading', { name: '수도원' })).toBeInTheDocument();
    expect(await screen.findByText('아직 담긴 것이 없습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '항목 더하기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.type(dialog.getByLabelText('이름'), '늙은 문지기');
    await userEvent.selectOptions(dialog.getByLabelText('종류'), '인물');
    await userEvent.type(dialog.getByLabelText(/키워드/), '문지기, 수도원 문');
    await userEvent.type(dialog.getByLabelText(/지목할 때 맞는 이름/), '하랄트');
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));

    const list = within(await screen.findByRole('list', { name: '항목' }));
    expect(await list.findByText('늙은 문지기')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(sent(seen, 'POST', `${LORE}/${ID}/entries`)[0]?.body).toEqual({
      name: '늙은 문지기',
      kind: 'person',
      keywords: ['문지기', '수도원 문'],
      content: '',
      true_names: ['하랄트'],
    });
  });

  it('종류로 거르고, 고치기와 지우기를 보낸다. 가득 찼으면 서버의 글을 알린다', async () => {
    const { seen } = signedIn({
      [`GET ${LORE}/${ID}`]: () => json(200, summary('수도원')),
      [`GET ${LORE}/${ID}/entries`]: () =>
        json(200, [entry('e1', '늙은 문지기', 'person'), entry('e2', '수도원 문', 'place'), entry('e3', '종탑', 'place')]),
      [`PATCH ${LORE}/${ID}/entries/e3`]: () => json(200, entry('e3', '무너진 종탑', 'place')),
      [`DELETE ${LORE}/${ID}/entries/e1`]: () => new Response(null, { status: 204 }),
      [`POST ${LORE}/${ID}/entries`]: () => json(409, { detail: '로어북 하나에 항목은 100개까지 넣을 수 있습니다.' }),
    });
    renderApp(`/trpg/studio/lorebooks/${ID}`);

    const list = within(await screen.findByRole('list', { name: '항목' }));
    await userEvent.click(screen.getByRole('button', { name: '장소 2' }));
    expect(list.queryByText('늙은 문지기')).toBeNull();
    expect(list.getByText('종탑')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '종탑 고치기' }));
    const editing = within(await screen.findByRole('dialog'));
    expect(editing.getByLabelText('이름')).toHaveValue('종탑');
    await userEvent.clear(editing.getByLabelText('이름'));
    await userEvent.type(editing.getByLabelText('이름'), '무너진 종탑');
    await userEvent.click(editing.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(sent(seen, 'PATCH', `${LORE}/${ID}/entries/e3`)[0]?.body).toMatchObject({ name: '무너진 종탑' }));

    await userEvent.click(screen.getByRole('button', { name: '장소 2' }));
    await userEvent.click(within(screen.getByRole('list', { name: '항목' })).getByRole('button', { name: '늙은 문지기 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(sent(seen, 'DELETE', `${LORE}/${ID}/entries/e1`)).toHaveLength(1));

    await userEvent.click(screen.getByRole('button', { name: '항목 더하기' }));
    const adding = within(await screen.findByRole('dialog'));
    await userEvent.type(adding.getByLabelText('이름'), '촛대');
    await userEvent.click(adding.getByRole('button', { name: '더하기' }));
    expect(await adding.findByText('로어북 하나에 항목은 100개까지 넣을 수 있습니다.')).toBeInTheDocument();
  });
});

describe('몬스터 모음', () => {
  it('몬스터를 더하는 본문에 종류와 네임드가 있다', async () => {
    const { seen } = signedIn({
      [`GET ${BEAST}/${ID}`]: () => json(200, summary('수로의 것들')),
      [`GET ${BEAST}/${ID}/monsters`]: () => json(200, []),
      [`POST ${BEAST}/${ID}/monsters`]: () =>
        json(201, { id: 'm1', name: '수로 왕쥐', kind: 'beast', content: '', unique: true, created_at: '2026-10-23T00:00:00Z', updated_at: '2026-10-23T00:00:00Z' }),
    });
    renderApp(`/trpg/studio/bestiaries/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '몬스터 더하기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.type(dialog.getByLabelText('이름'), '수로 왕쥐');
    await userEvent.selectOptions(dialog.getByLabelText('종류'), '짐승');
    await userEvent.click(dialog.getByRole('checkbox', { name: /네임드/ }));
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));

    await vi.waitFor(() =>
      expect(sent(seen, 'POST', `${BEAST}/${ID}/monsters`)[0]?.body).toEqual({ name: '수로 왕쥐', kind: 'beast', content: '', unique: true }),
    );
  });
});

describe('입력의 순수한 함수', () => {
  it('쉼표로 나누고, 개수와 길이와 대소문자만 다른 겹침을 알린다', () => {
    expect(splitWords(' 문, ,종탑 ,')).toEqual(['문', '종탑']);
    expect(wordsHint(['a', 'b'], 1, 30, '키워드')).toContain('1개까지');
    expect(wordsHint(['x'.repeat(31)], 5, 30, '키워드')).toContain('30자까지');
    expect(wordsHint(['Gate', 'gate'], 5, 30, '키워드')).toContain('두 번');
    expect(wordsHint(['문'], 5, 30, '키워드')).toBeNull();
  });

  it('인물이 아니면 지목할 이름을 보내지 않고 검사하지도 않는다', () => {
    const draft = { ...newEntryDraft(), name: ' 종탑 ', kind: 'place' as const, trueNames: 'a, a' };
    expect(entryHints(draft)).toEqual({});
    expect(toEntryBody(draft)).toMatchObject({ name: '종탑', true_names: [] });
    expect(Object.keys(entryHints({ ...draft, kind: 'person' }))).toEqual(['true_names']);
  });

  it('종류마다의 개수와 거르기, 글의 앞부분', () => {
    const items = [{ kind: 'place' }, { kind: 'person' }, { kind: 'place' }];
    expect(kindCounts(items, { person: '인물', place: '장소', item: '물건' })).toEqual([
      { kind: 'person', label: '인물', count: 1 },
      { kind: 'place', label: '장소', count: 2 },
    ]);
    expect(itemsOfKind(items, 'place')).toHaveLength(2);
    expect(itemsOfKind(items, undefined)).toHaveLength(3);
    expect(preview('가 '.repeat(50), 10)).toBe('가 가 가 가 가…');
  });
});
