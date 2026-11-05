// web/apps/web/src/api/origin.ts
// API 를 부를 주소의 앞부분(출처). 빌드할 때 고른다(VITE_API_ORIGIN, #429).
//
//   - 비우면(기본) 지금처럼 화면과 같은 출처의 상대 주소(/api/v1/...)로 부른다. 웹은 늘 이것이다
//   - 앱(Capacitor 로 감싼 화면)은 페이지의 출처가 우리 사이트와 달라(https://localhost) 우리 사이트의 출처를 적는다.
//     예: https://play.example.com. 프록시가 앱의 출처에만 CORS 를 연다(루트 README 의 "프록시는 앱의 출처에만 CORS 를 연다")
// 출처만 적는다(https://host[:port]). 경로나 물음표가 붙으면 빌드한 화면이 뜨지 않게 멈춘다. 끝의 / 는 떼어 준다.
// 쿠키는 다른 출처로 실리지 않는다(credentials: 'same-origin'). 앱의 갱신은 쿠키가 아니라 본문의 토큰이다(auth-server 의 "앱의 토큰").

const ORIGIN_PATTERN = /^https?:\/\/[A-Za-z0-9.-]+(?::\d{1,5})?$/;

/** 적힌 값을 출처로 바꾼다. 비었으면 빈 글자(같은 출처), 모양이 틀리면 오류다 */
export function apiOrigin(value: string | undefined = import.meta.env.VITE_API_ORIGIN as string | undefined): string {
  const trimmed = (value ?? '').trim().replace(/\/$/, '');
  if (trimmed === '') return '';
  if (!ORIGIN_PATTERN.test(trimmed)) {
    throw new Error(`VITE_API_ORIGIN 은 https://example.com 처럼 출처만 적는다: ${value}`);
  }
  return trimmed;
}

const API_ORIGIN = apiOrigin();

/** API 의 경로(/api/v1/...)를 부를 주소로 바꾼다 */
export function apiUrl(path: string, origin: string = API_ORIGIN): string {
  return `${origin}${path}`;
}
