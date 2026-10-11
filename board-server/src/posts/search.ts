// board-server/src/posts/search.ts

/**
 * 글 검색의 규칙과 셈. DB 도 Nest 도 모르는 순수한 함수들이다.
 *
 * 검색어를 낱말로 나누고, 낱말마다 "제목이나 본문에 이 글자들이 들어 있는가"를 본다. 모든 낱말이 들어 있는 글이 나온다.
 * 낱말의 어디에 있든 찾는다(부분 일치). 한국어는 낱말에 조사가 붙어서, 낱말이 통째로 같을 때만 찾으면
 * "공지"로 "공지를"을 찾지 못한다.
 */

import { TransformFnParams } from 'class-transformer';

/** 검색어 전체의 최대 길이(글자) */
export const MAX_QUERY_LENGTH = 50;
/** 낱말 하나의 최소 길이(글자). 한 글자로 찾으면 거의 모든 글이 걸린다 */
export const MIN_TERM_LENGTH = 2;
/** 검색어에 적을 수 있는 낱말의 수. 낱말마다 조건이 하나씩 는다 */
export const MAX_TERMS = 5;

/** 낱말마다 MIN_TERM_LENGTH 자 이상이다. 빈칸 하나로 나뉜 검색어(normalizeQuery 를 거친 것)에 쓴다 */
export const TERMS_LONG_ENOUGH = new RegExp(
  `^\\S{${MIN_TERM_LENGTH},}( \\S{${MIN_TERM_LENGTH},})*$`,
);
/** 낱말이 MAX_TERMS 개 이하다 */
export const NOT_TOO_MANY_TERMS = new RegExp(
  `^\\S+( \\S+){0,${MAX_TERMS - 1}}$`,
);

/** LIKE 에서 뜻이 있는 글자들. 역빗금은 이 글자들의 뜻을 없애는 글자라 함께 다룬다 */
const LIKE_SPECIAL = /[\\%_]/g;

/**
 * 검색어를 다듬는다. 앞뒤 빈칸을 떼고, 이어진 빈칸(줄바꿈과 탭도)을 빈칸 하나로 줄인다.
 * 글자가 아니면 그대로 둔다. 그것은 뒤의 검사가 거부한다.
 */
export function normalizeQuery({ value }: TransformFnParams): unknown {
  return typeof value === 'string' ? termsOf(value).join(' ') : value;
}

/** 검색어를 낱말들로 나눈다. 빈칸에서 나눈다. 같은 낱말은 한 번만 남긴다. */
export function termsOf(query: string): string[] {
  const terms = query.split(/\s+/).filter((term) => term !== '');
  return [...new Set(terms)];
}

/**
 * 낱말에서 LIKE 가 기호로 읽는 글자(%, _)와 역빗금 앞에 역빗금을 붙인다.
 * "100%"를 찾는 사람은 글자 % 를 찾는 것이다. 그대로 넘기면 "100 뒤에 아무 글자나"가 된다.
 */
export function escapeLike(term: string): string {
  return term.replace(LIKE_SPECIAL, (special) => `\\${special}`);
}

/** 이 낱말이 어디에든 들어 있는 글을 고르는 LIKE 의 모양. */
export function containsPattern(term: string): string {
  return `%${escapeLike(term)}%`;
}
