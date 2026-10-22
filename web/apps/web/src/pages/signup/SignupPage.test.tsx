// web/apps/web/src/pages/signup/SignupPage.test.tsx
// 가입 세 단계를 화면에서 따라가 본다. 서버는 가짜 fetch 다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const CONSENTS = {
  items: [
    { item: 'terms', version: 1, effective_on: '2026-10-20', required: true },
    { item: 'privacy', version: 1, effective_on: '2026-10-20', required: true },
    { item: 'marketing', version: 1, effective_on: '2026-10-20', required: false },
  ],
};

function routes(complete: (request: SeenRequest) => Response) {
  let consentReads = 0;
  const fake = installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'POST /api/v1/auth/signup': () => json(202, { detail: '보냈다' }),
    'POST /api/v1/auth/signup/verify': () => json(200, { detail: '맞다', signup_ticket: 'st-1' }),
    'GET /api/v1/auth/consents': () => {
      consentReads += 1;
      return json(200, CONSENTS);
    },
    'POST /api/v1/auth/signup/complete': complete,
  });
  return { ...fake, consentReads: () => consentReads };
}

async function reachProfileStep() {
  await userEvent.type(await screen.findByLabelText('이메일'), 'new@example.com');
  await userEvent.click(screen.getByRole('button', { name: '코드 받기' }));
  await userEvent.type(await screen.findByLabelText('인증 코드'), '654321');
  await userEvent.click(screen.getByRole('button', { name: '다음' }));
  await screen.findByLabelText('아이디');
}

async function fillProfile() {
  await userEvent.type(screen.getByLabelText('아이디'), 'new_player');
  await userEvent.type(screen.getByLabelText('닉네임'), '새모험가');
  await userEvent.type(screen.getByLabelText('비밀번호'), 'pw-long-enough-1');
  await userEvent.type(screen.getByLabelText('비밀번호 확인'), 'pw-long-enough-1');
  await userEvent.click(screen.getByLabelText('만 14세 이상입니다'));
}

describe('SignupPage', () => {
  it('세 단계를 마치면 체크한 동의만 보내고 로그인으로 가서 아이디를 채운다', async () => {
    const { seen } = routes(() => json(201, { detail: '가입했다' }));
    renderApp('/signup');

    await reachProfileStep();
    await fillProfile();
    const submit = await screen.findByRole('button', { name: '가입하기' });
    expect(submit).toBeDisabled();

    await userEvent.click(screen.getByLabelText('[필수] 이용약관'));
    await userEvent.click(screen.getByLabelText('[필수] 개인정보 수집·이용'));
    expect(submit).toBeEnabled();
    await userEvent.click(submit);

    expect(await screen.findByText('가입했습니다. 로그인해 주세요.')).toBeInTheDocument();
    expect(screen.getByLabelText('아이디')).toHaveValue('new_player');
    expect(seen.find((request) => request.url === '/api/v1/auth/signup/complete')?.body).toEqual({
      signup_ticket: 'st-1',
      username: 'new_player',
      nickname: '새모험가',
      password: 'pw-long-enough-1',
      age_over_14: true,
      consents: { terms: 1, privacy: 1 },
    });
  });

  it('보기를 누르면 그 판의 문서를 창으로 보인다', async () => {
    routes(() => json(201, { detail: '가입했다' }));
    renderApp('/signup');
    await reachProfileStep();

    const [firstView] = await screen.findAllByRole('button', { name: '보기' });
    await userEvent.click(firstView as HTMLElement);

    const dialog = await screen.findByRole('dialog', { name: '이용약관' });
    expect(await within(dialog).findByRole('heading', { name: '이용약관', level: 1 })).toBeInTheDocument();
    expect(within(dialog).getByText(/검토 중인 초안/)).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('동의의 판이 바뀌었으면 항목을 다시 읽고 체크를 비운다', async () => {
    const fake = routes(() => json(400, { consents: { terms: ['옛 판이다'] } }));
    renderApp('/signup');
    await reachProfileStep();
    await fillProfile();
    await userEvent.click(await screen.findByLabelText('[필수] 이용약관'));
    await userEvent.click(screen.getByLabelText('[필수] 개인정보 수집·이용'));
    await userEvent.click(screen.getByRole('button', { name: '가입하기' }));

    expect(await screen.findByText(/동의 항목이 바뀌었습니다/)).toBeInTheDocument();
    expect(screen.getByLabelText('[필수] 이용약관')).not.toBeChecked();
    expect(fake.consentReads()).toBe(2);
  });

  it('이미 가입을 마친 이메일이면 로그인으로 보낸다', async () => {
    routes(() => json(409, { detail: '있다', code: 'email_registered' }));
    renderApp('/signup');
    await reachProfileStep();
    await fillProfile();
    await userEvent.click(await screen.findByLabelText('[필수] 이용약관'));
    await userEvent.click(screen.getByLabelText('[필수] 개인정보 수집·이용'));
    await userEvent.click(screen.getByRole('button', { name: '가입하기' }));

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
    expect(screen.getByText(/이미 가입을 마친 이메일/)).toBeInTheDocument();
  });

  it('형식이 틀린 아이디는 보내기 전에 알린다', async () => {
    routes(() => json(201, { detail: '가입했다' }));
    renderApp('/signup');
    await reachProfileStep();

    await userEvent.type(screen.getByLabelText('아이디'), 'Bad Name');

    expect(screen.getByText(/영문 소문자, 숫자, 밑줄로 4~20자/)).toBeInTheDocument();
  });
});
