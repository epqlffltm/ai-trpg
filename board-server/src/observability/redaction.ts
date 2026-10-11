// board-server/src/observability/redaction.ts

/**
 * 로그에 적히기 직전에 민감한 값을 가리는 마지막 방어선. 다른 것을 모르는 순수한 함수들이다.
 *
 * 로그를 남기는 코드가 민감한 값을 넘기지 않는 것이 먼저다. 여기는 실수로 넘어온 것을 막는다.
 * 막는 길은 셋이다.
 *   1. 칸의 이름을 본다. password, token 같은 이름의 칸은 값을 보지 않고 가린다.
 *   2. 값의 글을 본다. 토큰, Authorization 머리말의 값, 주소에 든 계정과 비밀번호, 이메일 주소의 모양을 가린다.
 *   3. 값의 종류를 본다. 글자, 숫자, 참거짓만 싣는다. 묶음(객체, 배열)은 풀어 적지 않고 종류의 이름만 적는다.
 *      묶음을 통째로 적으면 그 안의 무엇이 로그에 남는지 아무도 알 수 없다.
 *
 * 무엇을 로그에 적으면 안 되는지는 저장소 루트의 docs/observability.md 의 "민감정보"에 있다.
 * 다른 서버들(파이썬, Go)도 같은 규칙을 제 언어로 갖고 있다.
 */

/** 가린 자리에 적는 말 */
export const REDACTED = '[REDACTED]';
/** 칸 하나에 싣는 글의 최대 길이. 넘으면 자른다. 본문 같은 긴 글이 통째로 실리는 것을 막는다 */
export const MAX_VALUE_LENGTH = 500;
/** 메시지의 최대 길이 */
export const MAX_MESSAGE_LENGTH = 2000;
/** 예외의 기록(stack trace)의 최대 길이 */
export const MAX_STACK_LENGTH = 16000;
/** 자른 자리에 붙이는 표시 */
const TRUNCATED = '…';

/** 이름에 이 낱말이 들어 있는 칸은 가린다. 이름은 낱말로 쪼개서 본다(accessToken -> access, token) */
const SENSITIVE_WORDS = new Set([
  'password',
  'passwd',
  'secret',
  'token',
  'jwt',
  'authorization',
  'cookie',
  'credential',
  'credentials',
  'otp',
  'dsn',
  'email',
  'prompt',
  'card',
  'cvc',
  'cvv',
  'code',
  'signature',
]);
/** 이름에 이 낱말들이 잇달아 들어 있는 칸은 가린다 */
const SENSITIVE_PHRASES = [
  'api_key',
  'private_key',
  'access_key',
  'payment_key',
  'database_url',
  'redis_url',
  'set_cookie',
];
/** 이 이름의 칸은 가린다. 글의 원문이 담기는 이름들이다 */
const SENSITIVE_NAMES = new Set([
  'body',
  'content',
  'text',
  'title',
  'declaration',
  'memo',
  'note',
  'notes',
  'lore',
  'completion',
  'response',
  'headers',
  'request_body',
  'response_body',
]);
/** 이름이 이 낱말로 끝나면 가리지 않는다. 원문이 아니라 그것을 가리키거나 센 값이다(email_hash) */
const SAFE_LAST_WORDS = new Set([
  'hash',
  'masked',
  'count',
  'length',
  'version',
  'id',
  'ms',
  'seconds',
  'type',
]);
/** code 로 끝나지만 가리지 않는 이름. 인증 코드가 아니라 결과의 종류다 */
const SAFE_NAMES = new Set(['error_code', 'status_code', 'exit_code']);

/** 이름을 낱말로 쪼갤 때 쓰는 모양. 밑줄, 점, 붙임표, 빈칸에서 끊고 대문자 앞에서도 끊는다(accessToken) */
const WORD_BREAK = /[_.\-\s]+|(?<=[a-z0-9])(?=[A-Z])/;

/** JWT 의 모양. 점으로 이은 세 마디고 첫 마디가 eyJ 로 시작한다 */
const JWT = /eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*/g;
/** Authorization 머리말의 값 */
const AUTH_SCHEME = /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi;
/** 주소에 든 계정과 비밀번호(postgresql://계정:비밀번호@호스트) */
const URL_USERINFO = /:\/\/[^/\s:@]+:[^@\s/]+@/g;
/** 이메일 주소 */
const EMAIL =
  /([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})/g;

/** 칸의 이름을 소문자 낱말들로 쪼갠다. */
export function wordsOf(name: string): string[] {
  return name
    .split(WORD_BREAK)
    .filter((word) => word !== '')
    .map((word) => word.toLowerCase());
}

/** 이 이름의 칸은 값을 가려야 하는가. */
export function isSensitiveName(name: string): boolean {
  const words = wordsOf(name);
  const normalized = words.join('_');
  const last = words.at(-1);
  if (
    last === undefined ||
    SAFE_NAMES.has(normalized) ||
    SAFE_LAST_WORDS.has(last)
  ) {
    return false;
  }
  if (
    SENSITIVE_NAMES.has(normalized) ||
    SENSITIVE_PHRASES.some((phrase) => normalized.includes(phrase))
  ) {
    return true;
  }
  return words.some((word) => SENSITIVE_WORDS.has(word));
}

/** limit 자를 넘으면 자르고 표시를 붙인다. */
export function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : text.slice(0, limit) + TRUNCATED;
}

/** 글에서 민감한 모양을 가리고, 너무 길면 자른다. 자르기를 먼저 한다. 긴 글 전체를 훑지 않는다. */
export function scrubText(text: string, limit = MAX_VALUE_LENGTH): string {
  return truncate(text, limit)
    .replace(JWT, '[REDACTED_JWT]')
    .replace(AUTH_SCHEME, (_match, scheme: string) => `${scheme} ${REDACTED}`)
    .replace(URL_USERINFO, `://${REDACTED}@`)
    .replace(
      EMAIL,
      (_match, first: string, domain: string) => `${first}***@${domain}`,
    );
}

/** 값의 종류의 이름. 묶음을 풀어 적는 대신 이것을 적는다. */
function kindOf(value: object): string {
  return Array.isArray(value) ? 'Array' : (value.constructor?.name ?? 'Object');
}

/**
 * 칸 하나의 값을 로그에 실어도 되는 값으로 바꾼다.
 *
 * 이름이 민감하면 가린다. 글자는 민감한 모양을 가린다. 숫자와 참거짓과 null 은 그대로다.
 * 그 밖의 것(객체, 배열, 함수)은 풀어 적지 않고 종류의 이름만 적는다. 값이 없는 것(undefined)은 싣지 않는다.
 */
export function safeValue(
  name: string,
  value: unknown,
): string | number | boolean | null | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (isSensitiveName(name)) {
    return REDACTED;
  }
  if (value === null || typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    // JSON 에는 무한대와 NaN 이 없다
    return Number.isFinite(value) ? value : String(value);
  }
  if (typeof value === 'string') {
    return scrubText(value);
  }
  if (typeof value === 'bigint') {
    return value.toString();
  }
  return typeof value === 'object' ? `[${kindOf(value)}]` : `[${typeof value}]`;
}
