// web/apps/web/src/pages/personas/Personas.test.tsx
// 내 페르소나(C4). 마이페이지에서 가기, 목록(기본이 먼저, 기본 표시), 만들기(이름은 꼭, 상한), 고치기(저장했습니다), 기본으로 두기, 지우기(한 번 더 묻기),
// 상한(persona_limit)과 남의 그림(image_not_owned). 폼의 검사와 본문을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import type { Persona } from '../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { draftOf, draftProblems, EMPTY_PERSONA, personaBody } from './personaForm';
import { describePersonaProblem } from './personaProblem';

const BASE = '/api/v1/asset/personas';
const HARU = '00000000-0000-4000-8000-000000000101';
const NIGHT = '00000000-0000-4000-8000-000000000102';

function persona(id: string, name: string, isDefault: boolean, extra: Partial<Persona> = {}): Persona {
  return { id, name, is_default: isDefault, description: '', image_id: null, age: '', gender: '', form_of_address: '', speech_examples: '', personality: '', revision: 1, created_at: '', updated_at: '', ...extra };
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  let list = [persona(HARU, '하루', true, { form_of_address: '선배', age: '스물일곱' }), persona(NIGHT, '밤', false)];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${BASE}`]: () => json(200, list),
    [`GET ${BASE}/${HARU}`]: () => json(200, list[0]),
    [`PUT ${BASE}/${NIGHT}/default`]: () => {
      list = [{ ...(list[1] as Persona), is_default: true }, { ...(list[0] as Persona), is_default: false }];
      return json(200, list[0]);
    },
    [`DELETE ${BASE}/${NIGHT}`]: () => {
      list = list.filter((entry) => entry.id !== NIGHT);
      return new Response(null, { status: 204 });
    },
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('내 페르소나', () => {
  it('마이페이지에서 가서 기본이 먼저인 목록을 보고, 기본을 바꾸고, 한 번 더 물은 뒤 지운다', async () => {
    const { seen } = signedIn();
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: '내 페르소나' }));
    const list = within(await screen.findByRole('list', { name: '내 페르소나' }));
    expect(await list.findByText('호칭 "선배" · 스물일곱')).toBeInTheDocument();
    expect(list.getAllByRole('link').map((link) => link.textContent)).toEqual(['하루', '밤']);
    expect(list.getByText('기본')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '기본으로 두기' }));
    await vi.waitFor(() => expect(list.getAllByRole('link').map((link) => link.textContent)).toEqual(['밤', '하루']));
    expect(sent(seen, 'PUT', `${BASE}/${NIGHT}/default`)).toHaveLength(1);

    await userEvent.click(list.getByRole('button', { name: '밤 지우기' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: '페르소나 지우기' })).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(list.getAllByRole('link').map((link) => link.textContent)).toEqual(['하루']));
    expect(seen.filter((request) => request.method === 'DELETE')).toHaveLength(1);
  });

  it('이름 없이는 만들지 않고, 만들면 보낸 본문으로 목록에 돌아간다. 상한이면 까닭을 알린다', async () => {
    let full = false;
    const { seen } = signedIn({
      [`POST ${BASE}`]: (request) => (full ? json(409, { detail: 'x', code: 'persona_limit' }) : json(201, { ...persona('n1', '새벽', false), ...(request.body as object) })),
    });
    renderApp('/me/personas/new');

    const form = within(await screen.findByRole('form', { name: '페르소나' }));
    await userEvent.click(form.getByRole('button', { name: '만들기' }));
    expect(form.getByText('이름을 적어 주세요.')).toBeInTheDocument();
    expect(sent(seen, 'POST', BASE)).toHaveLength(0);

    await userEvent.type(form.getByRole('textbox', { name: '이름' }), '  새벽  ');
    await userEvent.type(form.getByRole('textbox', { name: '호칭(상대가 나를 부르는 말)' }), '주인님');
    await userEvent.type(form.getByRole('textbox', { name: '성격' }), '조용하다');
    await userEvent.click(form.getByRole('button', { name: '만들기' }));
    expect(await screen.findByRole('heading', { name: '내 페르소나' })).toBeInTheDocument();
    expect(sent(seen, 'POST', BASE)).toEqual([
      { name: '새벽', form_of_address: '주인님', age: '', gender: '', description: '', personality: '조용하다', speech_examples: '', image_id: null },
    ]);

    full = true;
    await userEvent.click(screen.getByRole('link', { name: '페르소나 만들기' }));
    const again = within(await screen.findByRole('form', { name: '페르소나' }));
    await userEvent.type(again.getByRole('textbox', { name: '이름' }), '하나 더');
    await userEvent.click(again.getByRole('button', { name: '만들기' }));
    expect(await screen.findByText(/50개까지 만듭니다/)).toBeInTheDocument();
  });

  it('고치면 저장했다고 알리고 바뀐 본문을 보낸다', async () => {
    const { seen } = signedIn({ [`PATCH ${BASE}/${HARU}`]: (request) => json(200, { ...persona(HARU, '하루', true), ...(request.body as object), revision: 2 }) });
    renderApp(`/me/personas/${HARU}`);

    const form = within(await screen.findByRole('form', { name: '페르소나' }));
    expect(form.getByRole('textbox', { name: '호칭(상대가 나를 부르는 말)' })).toHaveValue('선배');
    await userEvent.type(form.getByRole('textbox', { name: '말투 예시' }), '"그래요?"');
    await userEvent.click(form.getByRole('button', { name: '저장하기' }));
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `${BASE}/${HARU}`)[0]).toMatchObject({ name: '하루', form_of_address: '선배', age: '스물일곱', speech_examples: '"그래요?"' });
  });
});

describe('페르소나의 순수한 함수', () => {
  it('검사, 본문, 실패의 글', () => {
    expect(draftProblems(EMPTY_PERSONA)).toEqual({ name: '이름을 적어 주세요.' });
    expect(draftProblems({ ...EMPTY_PERSONA, name: '가'.repeat(51), gender: '나'.repeat(21) })).toEqual({ name: '50자까지입니다.', gender: '20자까지입니다.' });
    expect(draftProblems({ ...EMPTY_PERSONA, name: ` ${'가'.repeat(50)} ` })).toEqual({});
    const draft = draftOf(persona(HARU, '하루', true, { image_id: 'img' }));
    expect(personaBody({ ...draft, age: ' 27 ' })).toMatchObject({ name: '하루', age: '27', image_id: 'img' });
    expect(describePersonaProblem(new ApiError({ status: 422, detail: 'x', code: 'image_not_owned' })).fields).toEqual({ imageId: '내가 올린 그림이 아닙니다.' });
    expect(describePersonaProblem(new ApiError({ status: 422, detail: 'x', fields: { form_of_address: ['30자까지'] } })).fields).toEqual({ formOfAddress: '30자까지' });
  });
});
