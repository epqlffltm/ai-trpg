// web/apps/web/src/pages/trpg/trpgPure.test.ts
// 탐색과 소개의 순수한 함수. 주소의 조건 읽기, 다음 쪽, 이름 묻기의 ID, 능력치의 이름, 인원의 글.

import { describe, expect, it } from 'vitest';
import { uniqueIds } from '../../hooks/usePublicNames';
import { hasFilters, parseFilters, tagSearchPath, toSearchParams } from './browse/filters';
import { playersLabel } from './labels';
import { nextOffset, PAGE_SIZE } from './queries';
import { abilityRows } from './scenario/PregenList';

describe('filters', () => {
  it('주소의 조건을 읽고 다시 쓴다', () => {
    const filters = parseFilters(new URLSearchParams('genre=horror&tag=%EC%A2%80%EB%B9%84&players=3'));
    expect(filters).toEqual({ genre: 'horror', tag: '좀비', players: 3 });
    expect(toSearchParams(filters).toString()).toBe('genre=horror&tag=%EC%A2%80%EB%B9%84&players=3');
    expect(hasFilters(filters)).toBe(true);
  });

  it('모르는 장르, 1~4 밖의 인원, 긴 태그는 버린다(서버는 422)', () => {
    const filters = parseFilters(new URLSearchParams(`genre=western&players=5&tag=${'가'.repeat(21)}`));
    expect(filters).toEqual({ genre: undefined, tag: undefined, players: undefined });
    expect(hasFilters(filters)).toBe(false);
    expect(toSearchParams(filters).toString()).toBe('');
  });

  it('태그의 탐색 주소를 만든다', () => {
    expect(tagSearchPath('던전 탐험')).toBe('/trpg?tag=%EB%8D%98%EC%A0%84+%ED%83%90%ED%97%98');
  });
});

describe('nextOffset', () => {
  it('다 읽기 전까지 다음 쪽의 offset 을 준다', () => {
    expect(nextOffset(PAGE_SIZE + 1, 1)).toBe(PAGE_SIZE);
    expect(nextOffset(PAGE_SIZE, 1)).toBeUndefined();
    expect(nextOffset(0, 1)).toBeUndefined();
  });
});

describe('uniqueIds', () => {
  it('겹친 것을 빼고 정렬해 같은 사람들이면 같은 열쇠가 된다', () => {
    expect(uniqueIds(['b', 'a', 'b'])).toEqual(['a', 'b']);
  });
});

describe('abilityRows', () => {
  it('시나리오의 능력치 차례와 이름으로 읽고, 이름이 없는 열쇠는 뒤에 그대로 둔다', () => {
    const abilities = [
      { key: 'str', name: '근력' },
      { key: 'dex', name: '민첩' },
    ];
    expect(abilityRows({ dex: 14, luck: 3, str: 12 }, abilities)).toEqual([
      ['근력', 12],
      ['민첩', 14],
      ['luck', 3],
    ]);
  });
});

describe('playersLabel', () => {
  it('최소와 최대가 같으면 한 수만 보인다', () => {
    expect(playersLabel({ min: 2, max: 4 })).toBe('2~4명');
    expect(playersLabel({ min: 1, max: 1 })).toBe('1명');
  });
});
