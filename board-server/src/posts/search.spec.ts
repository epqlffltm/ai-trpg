// board-server/src/posts/search.spec.ts

/**
 * 글 검색의 규칙과 셈(search.ts)을 검증한다.
 */

import {
  containsPattern,
  escapeLike,
  MAX_TERMS,
  normalizeQuery,
  NOT_TOO_MANY_TERMS,
  TERMS_LONG_ENOUGH,
  termsOf,
} from './search.js';

/** normalizeQuery 는 class-transformer 가 부르는 모양으로 받는다. 값만 넣어 부른다. */
function normalized(value: unknown): unknown {
  return normalizeQuery({ value } as Parameters<typeof normalizeQuery>[0]);
}

describe('termsOf', () => {
  it('빈칸에서 낱말로 나눈다', () => {
    expect(termsOf('고정 버그')).toEqual(['고정', '버그']);
  });

  it('이어진 빈칸, 줄바꿈, 탭도 빈칸이다', () => {
    expect(termsOf('  고정\t\n버그   후기 ')).toEqual(['고정', '버그', '후기']);
  });

  it('같은 낱말은 한 번만 남긴다', () => {
    expect(termsOf('고정 버그 고정')).toEqual(['고정', '버그']);
  });

  it('빈칸뿐이면 낱말이 없다', () => {
    expect(termsOf('   ')).toEqual([]);
    expect(termsOf('')).toEqual([]);
  });
});

describe('normalizeQuery', () => {
  it('앞뒤 빈칸을 떼고 이어진 빈칸을 하나로 줄인다', () => {
    expect(normalized('  고정 \n  버그 ')).toBe('고정 버그');
  });

  it('글자가 아니면 그대로 둔다', () => {
    expect(normalized(['고정', '버그'])).toEqual(['고정', '버그']);
    expect(normalized(undefined)).toBeUndefined();
  });
});

describe('TERMS_LONG_ENOUGH', () => {
  it.each(['공지', '고정 버그', 'ab', '100%'])('%j 는 통과한다', (query) => {
    expect(TERMS_LONG_ENOUGH.test(query)).toBe(true);
  });

  it.each(['', '가', 'a', '고정 가', '가 고정'])(
    '%j 는 걸린다. 한 글자인 낱말이 있다',
    (query) => {
      expect(TERMS_LONG_ENOUGH.test(query)).toBe(false);
    },
  );
});

describe('NOT_TOO_MANY_TERMS', () => {
  it('정해 둔 수까지 받는다', () => {
    const terms = Array.from({ length: MAX_TERMS }, (_, i) => `낱말${i}`);

    expect(NOT_TOO_MANY_TERMS.test(terms.join(' '))).toBe(true);
    expect(NOT_TOO_MANY_TERMS.test([...terms, '하나더'].join(' '))).toBe(false);
  });
});

describe('escapeLike', () => {
  it('LIKE 가 기호로 읽는 글자 앞에 역빗금을 붙인다', () => {
    expect(escapeLike('100%')).toBe('100\\%');
    expect(escapeLike('snake_case')).toBe('snake\\_case');
    expect(escapeLike('C:\\temp')).toBe('C:\\\\temp');
  });

  it('다른 글자는 그대로 둔다', () => {
    expect(escapeLike("고정 '버그' <b>")).toBe("고정 '버그' <b>");
  });
});

describe('containsPattern', () => {
  it('앞뒤에 "아무 글자나"를 붙인다', () => {
    expect(containsPattern('공지')).toBe('%공지%');
  });

  it('낱말 안의 % 는 글자로 찾는다', () => {
    expect(containsPattern('50%')).toBe('%50\\%%');
  });
});
