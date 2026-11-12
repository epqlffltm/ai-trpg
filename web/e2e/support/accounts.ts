// web/e2e/support/accounts.ts
// 계정을 화면으로 만들고 로그인한다. 메일 코드는 Mailpit 에서 읽는다(mailpit.ts).
// 실행마다 새 계정이다(시각으로 이름을 짓는다). 같은 스택에서 다시 돌려도 부딪치지 않는다.

import { expect, type Locator, type Page } from '@playwright/test';

import { codeSentAfter, mailMark } from './mailpit';

export type Account = { email: string; username: string; nickname: string; password: string };

// 견본의 손님(tools/dev_seed.py 의 seed_guest). e2e.sh 의 seed 가 만든다
export const SEED_GUEST: Account = {
  email: 'seed-guest@example.com',
  username: 'seed_guest',
  nickname: '견본손님',
  password: process.env.E2E_SEED_PASSWORD ?? 'seed-pass-2026',
};

/** 이번 실행의 새 계정. 아이디는 인증 서버의 규칙(영문 소문자·숫자·밑줄 4~20자)에 맞고 메일의 @ 앞과 다르다. */
export function newAccount(): Account {
  const stamp = Date.now().toString(36);
  return {
    email: `e2e-${stamp}@example.com`,
    username: `e2e_${stamp}`,
    nickname: `모험가${stamp.slice(-4)}`,
    // 아이디와 비슷하면 인증 서버가 받지 않는다. 따로 지은 값이다
    password: `Lantern-${Math.random().toString(36).slice(2, 10)}-Gate`,
  };
}

/** 가입한다. 메일 코드, 프로필, 필수 동의를 거쳐 "로그인해 주세요"까지. */
export async function signUp(page: Page, account: Account): Promise<void> {
  await page.goto('/signup');
  await page.getByLabel('이메일').fill(account.email);
  const mark = await mailMark(account.email);
  await page.getByRole('button', { name: '코드 받기' }).click();
  await page.getByLabel('인증 코드').fill(await codeSentAfter(mark));
  await page.getByRole('button', { name: '다음' }).click();

  await page.getByLabel('아이디').fill(account.username);
  await page.getByLabel('닉네임').fill(account.nickname);
  await page.getByLabel('비밀번호', { exact: true }).fill(account.password);
  await page.getByLabel('비밀번호 확인').fill(account.password);
  await page.getByLabel('만 14세 이상입니다').check();
  await page.getByLabel('[필수] 이용약관').check();
  await page.getByLabel('[필수] 개인정보 수집·이용').check();
  await page.getByRole('button', { name: '가입하기' }).click();
  await expect(page.getByText('가입했습니다. 로그인해 주세요.')).toBeVisible();
}

/** 로그인한다. 아이디와 비밀번호, 그다음 메일 코드. 머리의 내 메뉴에 닉네임이 보일 때까지. */
export async function logIn(page: Page, account: Account): Promise<void> {
  if (!page.url().includes('/login')) await page.goto('/login');
  await page.getByLabel('아이디').fill(account.username);
  await page.getByLabel('비밀번호', { exact: true }).fill(account.password);
  const mark = await mailMark(account.email);
  await page.getByRole('button', { name: '다음' }).click();
  await page.getByLabel('인증 코드').fill(await codeSentAfter(mark));
  await page.getByRole('main').getByRole('button', { name: '로그인' }).click();
  await expect(page.getByRole('button', { name: `내 메뉴: ${account.nickname}` })).toBeVisible();
}

/**
 * 시험용 본인확인(가짜 업체)으로 성인 인증을 한다. 충전과 환영 실버가 열린다.
 * 인증하면 화면이 토큰을 새로 받는다(refresh). 그 답이 오기 전에 화면을 다시 읽으면 바뀌기 전의 refresh 쿠키를
 * 다시 보내 세션이 끊긴다. 그래서 새 토큰을 받을 때까지 기다린다.
 */
export async function verifyAdult(page: Page): Promise<void> {
  await page.goto('/me/identity');
  await page.getByRole('button', { name: '성인(만 30세)' }).click();
  const refreshed = page.waitForResponse((response) => response.url().endsWith('/api/v1/auth/refresh') && response.ok());
  await page.getByRole('button', { name: '이 사람으로 인증하기' }).click();
  await expect(page.getByRole('heading', { name: '본인인증을 마쳤습니다' })).toBeVisible();
  await refreshed;
}

/**
 * 시험용 결제창(가짜 대행사)으로 골드 1,000 을 충전한다. 본인인증을 마친 계정이어야 한다.
 * 충전으로 가는 길과 잔액은 머리의 내 메뉴 안에 있다(layout/AccountMenu.tsx 의 HeaderBalance).
 * 충전한 뒤 내 메뉴의 잔액(지갑: 골드 … · 실버 …)이 골드 1000 인지 본다. 결제 서버가 넣은 것을 다시 읽은 값이다.
 */
export async function chargeThousand(page: Page, nickname: string): Promise<void> {
  await openMyMenu(page, nickname).then((menu) => menu.getByRole('link', { name: '충전', exact: true }).click());
  const checkout = page.getByRole('region', { name: '시험용 결제창' });
  // 본인인증을 결제 서버에 알리는 것은 인증 서버의 워커(5초마다)다. 그 전에 주문하면 403 이고 화면은 상품 고르기로
  // 돌아간다(본인인증을 마친 계정만 충전할 수 있습니다). 결제창이 열릴 때까지 다시 고른다
  await expect(async () => {
    await page.getByRole('list', { name: '충전할 상품' }).getByRole('button', { name: /골드 1,000/ }).click();
    await expect(checkout).toBeVisible({ timeout: 3_000 });
  }).toPass({ timeout: 30_000, intervals: [2_000] });
  await checkout.getByRole('button', { name: '결제 성공' }).click();
  await expect(page.getByText('충전을 마쳤습니다: 골드 1,000')).toBeVisible();
  const menu = await openMyMenu(page, nickname);
  await expect(menu.getByRole('link', { name: /^지갑: 골드 1000 / })).toBeVisible();
  // 같은 단추를 한 번 더 눌러 메뉴를 닫는다
  await page.getByRole('button', { name: `내 메뉴: ${nickname}` }).click();
  await expect(menu).toBeHidden();
}

/** 머리의 내 메뉴를 연다. 열린 메뉴(nav)를 돌려준다. */
async function openMyMenu(page: Page, nickname: string): Promise<Locator> {
  const menu = page.getByRole('navigation', { name: '내 메뉴' });
  if (!(await menu.isVisible())) await page.getByRole('button', { name: `내 메뉴: ${nickname}` }).click();
  await expect(menu).toBeVisible();
  return menu;
}
