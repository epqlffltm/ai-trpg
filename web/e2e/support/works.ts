// web/e2e/support/works.ts
// chat 과 story 의 흐름이 화면에서 하는 일. 작품은 e2e.sh 의 seed 가 채운다(tools/e2e/seed_works.py, 이름이 같다).
// 둘 다 처음 보내는 말에서 모델을 고르게 한다. 고르고 나면 같은 말을 한 번 더 보낸다(고르기는 보내지 않고 닫힌다).

import { expect, type Locator, type Page } from '@playwright/test';

// tools/e2e/seed_works.py 의 CHARACTER_NAME, WORLD_NAME
export const CHARACTER_NAME = '[e2e] 세라';
export const WORLD_NAME = '[e2e] 여름 학원';

/** 그 곳(chat, story)의 첫 화면으로 간다. 대화나 세션의 화면은 주 메뉴를 접어 두므로 주소로 간다. */
export async function openSection(page: Page, name: 'chat' | 'story'): Promise<void> {
  await page.goto(`/${name}`);
}

/** 보낼 말의 칸이 있는 폼. 화면에 보내기 단추가 둘(다른 하나는 다른 곳의 것)이라 폼으로 좁힌다. */
function composer(page: Page): Locator {
  return page.locator('form', { has: page.getByLabel('보낼 말') });
}

/** 말을 적어 보낸다. */
export async function send(page: Page, text: string): Promise<void> {
  await page.getByLabel('보낼 말').fill(text);
  await composer(page).getByRole('button', { name: '보내기', exact: true }).click();
}

/** 처음 보낸 말에 열리는 모델 고르기에서 그 모델을 고르고, 적어 둔 말을 다시 보낸다. */
export async function pickModelAndResend(page: Page, model: string): Promise<void> {
  const picker = page.getByRole('dialog', { name: '모델 고르기' });
  await picker.getByRole('radio', { name: model }).check();
  await picker.getByRole('button', { name: '이 모델로 하기' }).click();
  await expect(picker).toBeHidden();
  await composer(page).getByRole('button', { name: '보내기', exact: true }).click();
}

/** chat 에서 그 캐릭터의 공개 페이지로 가 대화를 시작한다. */
export async function startChat(page: Page): Promise<void> {
  await openSection(page, 'chat');
  await page.getByRole('link', { name: CHARACTER_NAME }).first().click();
  await page.getByRole('button', { name: '대화 시작' }).click();
  await expect(page.getByLabel('보낼 말')).toBeVisible();
}

/** story 에서 그 세계관으로 가 새 세션을 연다. */
export async function startStory(page: Page): Promise<void> {
  await openSection(page, 'story');
  await page.getByRole('link', { name: WORLD_NAME }).first().click();
  await page.getByRole('button', { name: '새로 시작' }).click();
  await expect(page.getByLabel('보낼 말')).toBeVisible();
}
