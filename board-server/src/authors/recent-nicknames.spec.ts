// board-server/src/authors/recent-nicknames.spec.ts

/**
 * 최근에 적은 닉네임의 기억(recent-nicknames.ts)을 검증한다.
 */

import { RecentNicknames } from './recent-nicknames.js';

describe('RecentNicknames', () => {
  it('적은 이름을 기억한다', () => {
    const recent = new RecentNicknames(10);

    recent.remember('a', '모험가');

    expect(recent.has('a', '모험가')).toBe(true);
  });

  it('이름이 달라지면 기억하지 않은 것이다. 다시 적어야 한다', () => {
    const recent = new RecentNicknames(10);
    recent.remember('a', '모험가');

    expect(recent.has('a', '새이름')).toBe(false);
  });

  it('새 이름을 적으면 그것을 기억한다', () => {
    const recent = new RecentNicknames(10);
    recent.remember('a', '모험가');

    recent.remember('a', '새이름');

    expect(recent.has('a', '새이름')).toBe(true);
    expect(recent.size).toBe(1);
  });

  it('끝에 닿으면 통째로 비우고 새로 기억한다', () => {
    const recent = new RecentNicknames(2);
    recent.remember('a', '하나');
    recent.remember('b', '둘');

    recent.remember('c', '셋');

    expect(recent.size).toBe(1);
    expect(recent.has('a', '하나')).toBe(false);
    expect(recent.has('c', '셋')).toBe(true);
  });

  it('이미 아는 사람의 이름을 바꿀 때는 비우지 않는다', () => {
    const recent = new RecentNicknames(2);
    recent.remember('a', '하나');
    recent.remember('b', '둘');

    recent.remember('b', '둘째');

    expect(recent.size).toBe(2);
    expect(recent.has('a', '하나')).toBe(true);
  });

  it('모두 잊을 수 있다', () => {
    const recent = new RecentNicknames(10);
    recent.remember('a', '하나');

    recent.clear();

    expect(recent.has('a', '하나')).toBe(false);
  });
});
