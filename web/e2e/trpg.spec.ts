// web/e2e/trpg.spec.ts
// 가입부터 TRPG 한 라운드까지(P2-4 의 첫 흐름). 서버를 모두 띄운 스택에서 화면으로만 따라간다.
//
// 새 사람이 가입하고 로그인해 본인인증과 충전을 한다. 견본 시나리오로 2명 테이블을 열고, 견본의 손님(seed_guest)이
// 다른 브라우저에서 초대 코드로 들어온다. 둘이 캐릭터를 정하고 시작해 선언하면 라운드가 닫힌다.
// 게임 서버는 언어 모델(가짜 모델, tools/e2e/stub_llm.py)로 서술한다. 쓰는 동안 두 화면 모두에 미리 보기가 보이고,
// 다 쓰면 다음 라운드의 첫머리에 서술이 남는다. 서술의 글은 가짜 모델의 것이라 게임 서버의 가짜 서술자가 아니다.

import { expect, type Page, test } from '@playwright/test';

import { chargeThousand, logIn, newAccount, SEED_GUEST, signUp, verifyAdult } from './support/accounts';
import { joinByInvite, openTable, pickPreset } from './support/trpg';

// 가짜 모델의 서술(tools/e2e/stub_llm.py 의 NARRATION)의 처음과 끝
const NARRATION_START = '등잔불이 흔들리고';
const NARRATION_END = '[e2e] 서술이 끝까지 왔다.';

async function declare(page: Page, text: string): Promise<void> {
  const form = page.getByRole('form', { name: '선언' });
  await form.getByLabel('무엇을 하나요').fill(text);
  await form.getByRole('button', { name: '선언 보내기' }).click();
}

/** 라운드 1 이 닫히는 동안의 미리 보기와, 라운드 2 의 첫머리에 남은 서술. */
async function expectNarration(page: Page): Promise<void> {
  await expect(page.getByText('결과를 서술하는 중입니다.', { exact: false })).toBeVisible();
  const next = page.getByRole('article', { name: /^라운드 2/ });
  await expect(next).toContainText(NARRATION_START);
  await expect(next).toContainText(NARRATION_END);
}

test('가입하고 충전한 사람이 손님과 TRPG 한 라운드를 한다', async ({ page: host, browser }) => {
  const account = newAccount();

  await test.step('가입하고 로그인한다', async () => {
    await signUp(host, account);
    await logIn(host, account);
  });

  await test.step('본인인증을 하고 충전한다', async () => {
    await verifyAdult(host);
    await chargeThousand(host);
  });

  const guestContext = await browser.newContext();
  const guest = await guestContext.newPage();

  await test.step('테이블을 열고 손님이 초대 코드로 들어온다', async () => {
    const code = await openTable(host);
    await pickPreset(host, '수도사 렌');
    await logIn(guest, SEED_GUEST);
    await joinByInvite(guest, code);
    await pickPreset(guest, '사냥꾼 미라');
    await host.getByRole('button', { name: '시작하기' }).click();
    await expect(host.getByRole('article', { name: /^라운드 1/ })).toBeVisible();
    await expect(guest.getByRole('article', { name: /^라운드 1/ })).toBeVisible();
  });

  await test.step('둘이 선언하면 라운드가 닫히고 서술이 두 화면에 흐른다', async () => {
    await declare(host, '문지기에게 등불을 빌려 달라고 한다.');
    await declare(guest, '행상의 젖은 짐을 살핀다.');
    await Promise.all([expectNarration(host), expectNarration(guest)]);
  });

  await guestContext.close();
});
