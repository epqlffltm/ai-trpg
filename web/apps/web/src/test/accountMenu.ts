// web/apps/web/src/test/accountMenu.ts
// 위쪽 줄의 프로필 단추를 눌러 내 메뉴(잔액, 출석·충전, MY, 운영, 로그아웃)를 펼친다. 펼친 창 안을 찾는 것을 돌려준다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

export async function openAccountMenu() {
  await userEvent.click(await screen.findByRole('button', { name: /^내 메뉴:/ }));
  return within(await screen.findByRole('navigation', { name: '내 메뉴' }));
}
