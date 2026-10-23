// web/apps/web/src/pages/chat/studio/characters/keys.ts
// 장소와 물건의 id 를 화면이 붙인다. 순수한 함수다(무작위는 넘겨받는다).
// 서버가 받는 글자(영문, 숫자, -, _)와 길이(40)에 맞춘다. 이미 있는 것은 id 를 바꾸지 않아 판이 바뀌어도 같은 것으로 남는다.

/** 무작위 글자 8개. 시험은 정해 둔 것을 넘긴다 */
export function randomSuffix(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 8);
}

/** prefix-xxxxxxxx 꼴의 새 id. 겹치면 다시 뽑는다 */
export function newKey(prefix: string, taken: Iterable<string>, random: () => string = randomSuffix): string {
  const used = new Set(taken);
  let key = `${prefix}-${random()}`;
  while (used.has(key)) key = `${prefix}-${random()}`;
  return key;
}
