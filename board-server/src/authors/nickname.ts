// board-server/src/authors/nickname.ts

/**
 * 토큰에 실려 온 닉네임을 받아들일지 정한다. 순수한 함수다.
 *
 * 닉네임은 인증 서버가 서명한 토큰에 실려 온다. 꾸며 낼 수는 없지만, 화면에 그대로 나갈 값이라 한 번 더 본다.
 * 받아들일 수 없는 값이면 적지 않고 넘긴다. 토큰은 그대로 받는다. 이름이 이상하다고 로그인을 막을 까닭은 없다.
 *
 * 인증 서버의 닉네임은 한글, 영문, 숫자, 밑줄로 20자까지다(auth-server/accounts/validators.py).
 * 여기서는 그보다 넓게 받는다. 인증 서버가 규칙을 넓혔는데 여기만 그대로면 새 이름이 조용히 버려진다.
 * 막는 것은 화면을 망가뜨릴 수 있는 것(제어 문자, 보이지 않는 글자, 지나치게 긴 이름)이다.
 */

/** 받아들이는 닉네임의 최대 길이(글자). 인증 서버의 20자보다 넉넉하다 */
export const NICKNAME_MAX_LENGTH = 50;

/** 제어 문자와 보이지 않는 서식 문자(줄바꿈, NUL, 방향을 뒤집는 글자 등) */
const INVISIBLE = /\p{C}/u;
/** 빈칸이 아닌 글자 */
const VISIBLE = /\S/;

/** 토큰의 nickname 값을 받아들일 수 있으면 그 이름을, 아니면 undefined 를 돌려준다. */
export function readNickname(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  if (!VISIBLE.test(value) || INVISIBLE.test(value)) {
    return undefined;
  }
  // 그림 글자 하나를 한 자로 센다
  if ([...value].length > NICKNAME_MAX_LENGTH) {
    return undefined;
  }
  return value;
}
