// web/e2e/works.spec.ts
// chat 의 대화 한 번과 story 의 세션 한 턴(P2-4 의 둘째 흐름). 서버를 모두 띄운 스택에서 화면으로만 따라간다.
//
// 새 사람이 가입하고 본인인증과 충전을 한 뒤, 견본 계정이 게시한 캐릭터(chat)와 세계관(story)으로 한 번씩 말을 건다.
// 두 서버 모두 언어 모델(가짜 모델, tools/e2e/stub_llm.py)로 답한다. 말 한 번의 값은 결제 서버의 가격표에서 온다.
// 가입과 충전은 한 번만 한다(beforeAll). 메일 코드에 계정마다 1분의 간격과 1시간에 5번의 한도가 있고, 충전이 느리다.
// 한 테스트가 떨어져도 다른 것은 돈다(Playwright 가 워커를 다시 띄워 beforeAll 을 다시 한다).

import { expect, type Page, test } from '@playwright/test';

import { chargeThousand, logIn, newAccount, signUp, verifyAdult } from './support/accounts';
import { CHARACTER_NAME, pickModelAndResend, send, startChat, startStory } from './support/works';

// 가짜 모델의 답(tools/e2e/stub_llm.py 의 CHAT_REPLY, STORY_REPLY)
const CHAT_REPLY = '[e2e] 세라가 조용히 웃는다. 비가 그칠 때까지 여기 있어도 돼.';
const STORY_NARRATION = '[e2e] 학교의 종이 길게 울린다.';
const STORY_LINE = '[e2e] 늦었네. 기다렸어.';

let page: Page;

test.beforeAll(async ({ browser }) => {
  const account = newAccount();
  page = await browser.newPage();
  await signUp(page, account);
  await logIn(page, account);
  await verifyAdult(page);
  await chargeThousand(page, account.nickname);
});

test.afterAll(async () => {
  await page?.close();
});

test('캐릭터와 대화를 시작해 말을 걸면 답이 온다', async () => {
  await startChat(page);
  const said = '안녕, 비가 많이 오네.';
  await send(page, said);
  await pickModelAndResend(page, 'E2E 대화');

  const lines = page.getByRole('region', { name: '대화' }).getByRole('list', { name: '말' });
  await expect(lines).toContainText(said);
  await expect(lines.getByText(CHAT_REPLY)).toBeVisible();
});

test('세계관의 세션을 열어 말을 걸면 서술과 인물의 말이 나뉘어 온다', async () => {
  await startStory(page);
  const said = '안녕, 세라.';
  await send(page, said);
  await pickModelAndResend(page, 'E2E 이야기');

  const lines = page.getByRole('region', { name: '이야기' }).getByRole('list', { name: '말' });
  await expect(lines).toContainText(said);
  // 서술과 인물(@sera)의 말은 따로 그려진다. 인물의 말 위에는 그 인물의 이름이 붙는다
  await expect(lines.getByText(STORY_NARRATION, { exact: true })).toBeVisible();
  await expect(lines.getByText(CHARACTER_NAME, { exact: true })).toBeVisible();
  await expect(lines.getByText(STORY_LINE, { exact: true })).toBeVisible();
});
