// web/apps/web/src/pages/identity/identityProvider.ts
// 본인확인 업체의 갈래. 인증 서버에 꽂힌 업체(IDENTITY_PROVIDER)에 맞춰 빌드할 때 고른다(VITE_IDENTITY_PROVIDER). 순수한 함수다.
//
//   - fake(기본): 인증 서버의 가짜 업체에 맞춘 시험용 창. 글자는 fake:<사람 식별값>:<생일 YYYY-MM-DD> 이다
//     (auth-server/accounts/identity_providers.py). 로컬과 CI 의 인증 서버가 가짜다. 운영의 인증 서버는 가짜를 쓰지 않는다
//   - none: 창을 띄우지 않고 지금은 본인인증을 할 수 없다고 알린다(실제 업체가 붙기 전의 운영)
// 실제 업체(NICE, KCB 같은 곳)는 계약한 뒤 더한다. 그때 이 갈래에 하나가 늘고, 글자를 내는 흐름(useVerifyIdentity)은 그대로다.

export type ProviderKind = 'fake' | 'none';

export function providerKind(value: string | undefined = import.meta.env.VITE_IDENTITY_PROVIDER as string | undefined): ProviderKind {
  if (value === undefined || value === '' || value === 'fake') return 'fake';
  return 'none';
}

/** 사람 식별값에 쓸 수 없는 글자(서버의 FAKE_TOKEN 은 영문, 숫자, + / = _ - 로 1~128 자) */
const DI_CHARS = /[^A-Za-z0-9+/=_-]/g;
const DI_INVALID = /[^A-Za-z0-9+/=_-]/;
export const DI_MAX = 128;

/** 계정마다의 기본 식별값. 같은 계정이면 늘 같아 한 사람 한 계정을 시험할 수 있다 */
export function defaultFakeDi(publicId: string): string {
  return `dev-${publicId}`.replace(DI_CHARS, '').slice(0, DI_MAX);
}

/** 식별값의 문제. 없으면 null */
export function diHint(di: string): string | null {
  if (di === '') return '사람 식별값을 적어 주세요.';
  if (di.length > DI_MAX) return `${DI_MAX}자까지입니다.`;
  return DI_INVALID.test(di) ? '영문, 숫자, + / = _ - 만 씁니다.' : null;
}

/** 가짜 업체의 글자 */
export function fakeIdentityToken(di: string, birthDate: string): string {
  return `fake:${di}:${birthDate}`;
}

/** 오늘(today, YYYY-MM-DD)에 만 age 세가 되는 생일. 시험의 빠른 고르기에 쓴다 */
export function birthDateForAge(today: string, age: number): string {
  const [year, month, day] = today.split('-');
  return `${String(Number(year) - age).padStart(4, '0')}-${month}-${day === '29' && month === '02' ? '28' : day}`;
}

/** 한국 날짜(YYYY-MM-DD). 인증 서버가 나이를 한국 날짜로 센다 */
export function koreanToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
}
