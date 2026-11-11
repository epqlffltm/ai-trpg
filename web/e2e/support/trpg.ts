// web/e2e/support/trpg.ts
// TRPG 의 한 판을 화면으로 따라간다. 견본 시나리오(tools/dev_seed.py 의 "[견본] 잿빛 수도원")로 테이블을 열고,
// 손님이 초대 코드로 들어와 둘이 캐릭터를 정한 뒤 시작한다.

import { expect, type Page } from '@playwright/test';

// tools/dev_seed.py 의 SEED_TITLE
export const SEED_SCENARIO = '[견본] 잿빛 수도원';

/** 둘러보기에서 견본 시나리오를 찾아 2명 테이블을 만든다. 테이블의 초대 코드를 돌려준다. */
export async function openTable(page: Page): Promise<string> {
  await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('link', { name: 'TRPG' }).click();
  await page.getByRole('link', { name: SEED_SCENARIO }).first().click();
  await page.getByRole('link', { name: '테이블 만들기' }).click();
  await page.getByRole('button', { name: '2명' }).click();
  await page.getByRole('complementary', { name: '요약' }).getByRole('button', { name: '만들기' }).click();
  const invite = page.getByRole('region', { name: '모집 중' }).locator('code');
  await expect(invite).toBeVisible();
  return (await invite.textContent())?.trim() ?? '';
}

/** 로비의 초대 코드로 테이블에 들어간다. */
export async function joinByInvite(page: Page, code: string): Promise<void> {
  await page.goto('/trpg/lobby');
  await page.getByLabel('초대 코드로 들어가기').fill(code);
  await page.getByRole('button', { name: '들어가기' }).click();
  await expect(page.getByRole('region', { name: '모집 중' })).toBeVisible();
}

/** 준비된 캐릭터(프리젠) 하나로 정한다. */
export async function pickPreset(page: Page, name: string): Promise<void> {
  const form = page.getByRole('form', { name: '캐릭터 정하기' });
  await form.getByRole('radio', { name }).check();
  await form.getByRole('button', { name: '이 캐릭터로 정하기' }).click();
  await expect(page.getByRole('region', { name: '앉은 사람' })).toContainText(name);
}
