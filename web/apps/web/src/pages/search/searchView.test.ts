// web/apps/web/src/pages/search/searchView.test.ts
// 작품 검색(#984)의 검색어 규칙: 공백과 "#" 하나뿐인 것은 막고, 길이 상한을 지키고, 주소에 앞뒤 공백을 지운 검색어를 싣는다.

import { describe, expect, it } from 'vitest';
import { SEARCH_MAX_LENGTH, isSearchable, searchPath, searchProblem, searchTag } from './searchView';

describe('searchView', () => {
  it('"#"로 시작하면 태그다', () => {
    expect(searchTag('#판타지')).toBe('판타지');
    expect(searchTag('  # 판타지 ')).toBe('판타지');
    expect(searchTag('판타지')).toBeNull();
  });

  it('빈 검색어는 문제가 아니라 아직 찾지 않은 것이다', () => {
    expect(searchProblem('   ')).toBeNull();
    expect(isSearchable('   ')).toBe(false);
  });

  it('"#" 뒤가 비었거나 또 "#"이면 막는다', () => {
    for (const q of ['#', '# ', '##']) {
      expect(searchProblem(q)).toBe('# 뒤에 태그를 적어 주세요.');
      expect(isSearchable(q)).toBe(false);
    }
  });

  it('상한을 넘으면 막는다', () => {
    expect(searchProblem('가'.repeat(SEARCH_MAX_LENGTH))).toBeNull();
    expect(searchProblem('가'.repeat(SEARCH_MAX_LENGTH + 1))).toBe(`검색어는 ${SEARCH_MAX_LENGTH}자까지입니다.`);
  });

  it('주소에는 앞뒤 공백을 지운 검색어를 싣는다', () => {
    expect(searchPath('  #판타지 ')).toBe('/search?q=%23%ED%8C%90%ED%83%80%EC%A7%80');
    expect(isSearchable('은하')).toBe(true);
  });
});
