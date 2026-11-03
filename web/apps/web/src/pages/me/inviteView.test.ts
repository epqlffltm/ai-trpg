// web/apps/web/src/pages/me/inviteView.test.ts
// 초대 코드(#990)의 가입 주소와 받은 보상의 한 줄.

import { describe, expect, it } from 'vitest';
import { inviteLink, rewardLine } from './inviteView';

describe('inviteView', () => {
  it('가입 주소에 초대 코드를 싣는다', () => {
    expect(inviteLink('https://example.com', 'ABCD2345')).toBe('https://example.com/signup?invite=ABCD2345');
  });

  it('받은 보상과 상한을 적는다. 상한이 0 이면 꺼져 있다고 적는다', () => {
    expect(rewardLine(2, 5)).toBe('받은 초대 보상 2 / 5번');
    expect(rewardLine(7, 5)).toBe('받은 초대 보상 5 / 5번');
    expect(rewardLine(0, 0)).toBe('지금은 초대 보상을 주지 않습니다.');
  });
});
