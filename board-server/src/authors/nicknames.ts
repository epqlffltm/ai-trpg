// board-server/src/authors/nicknames.ts

/**
 * 사용자 번호로 닉네임을 찾는 표. 순수한 함수들이다. DB 를 모른다.
 */

/** DB 가 돌려주는 한 줄. */
export interface NicknameRow {
  userId: string;
  nickname: string;
}

/** 사용자 번호로 닉네임을 찾는 표. 이름을 모르는 사람은 들어 있지 않다. */
export type Nicknames = ReadonlyMap<string, string>;

/** 비어 있는 표. 이름을 찾을 사람이 없을 때 쓴다. */
export const NO_NICKNAMES: Nicknames = new Map();

/** DB 가 돌려준 줄들을 표로 바꾼다. */
export function nicknamesFrom(rows: readonly NicknameRow[]): Nicknames {
  return new Map(rows.map((row) => [row.userId, row.nickname]));
}

/** 이 사람의 닉네임. 모르는 사람이면 null 이다. 화면은 "알 수 없음"으로 그린다. */
export function nicknameOf(
  nicknames: Nicknames,
  userId: string,
): string | null {
  return nicknames.get(userId) ?? null;
}
