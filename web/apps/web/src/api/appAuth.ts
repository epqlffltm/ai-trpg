// web/apps/web/src/api/appAuth.ts
// 앱(Capacitor 로 감싼 화면)에서 토큰을 다루는 길(#429, docs/product/app-refresh.md). 빌드할 때 고른다(VITE_AUTH_TRANSPORT).
//
//   - web(기본): refresh 토큰은 httpOnly 쿠키다. 화면이 인증 서버를 직접 부른다(refresh.ts, auth.ts, account.ts)
//   - app: refresh 토큰은 네이티브 플러그인(AppAuth)만 쥔다. 로그인 2단계, 갱신, 로그아웃, 비밀번호 변경을
//     플러그인이 인증 서버의 앱의 길(/api/v1/auth/app/...)로 부르고, 화면에는 access 토큰만 넘긴다.
//     화면의 스크립트가 refresh 토큰을 보지 못하므로 앱 안의 XSS 가 14일짜리 토큰을 가져가지 못한다.
//
// 플러그인의 약속(앱 껍데기가 지킨다)
//   - Capacitor 의 플러그인 이름은 AppAuth 다(globalThis.Capacitor.Plugins.AppAuth)
//   - 메서드마다 { status, body } 를 돌려준다. status 는 인증 서버가 답한 상태 코드, body 는 그 본문이다
//   - 토큰을 주는 답(200)의 body 에서 refresh_token 과 refresh_expires_in 은 빼고 넘긴다. 플러그인이 기기의 안전한 저장소에 둔다
//   - 서버에 닿지 못하면(망이 없다) reject 한다. 화면은 그것을 NetworkError 로 본다
//   - 갱신(refresh)은 저장소에 토큰이 없으면 서버를 부르지 않고 { status: 401 } 이다
//   - 갱신과 로그아웃이 401 이면 저장소의 토큰을 지운다. 한 번에 하나의 갱신만 보낸다(인증 서버의 재사용 탐지)

import { NetworkError, toApiError } from './errors';
import type { LoginResponse } from './types';

/** 플러그인의 답. 인증 서버가 답한 상태 코드와 본문이다 */
export type NativeAnswer = { status: number; body?: unknown };

export type AppAuthPlugin = {
  verifyLogin(options: { loginTicket: string; code: string }): Promise<NativeAnswer>;
  refresh(): Promise<NativeAnswer>;
  logout(): Promise<NativeAnswer>;
  changePassword(options: { accessToken: string; currentPassword: string; newPassword: string }): Promise<NativeAnswer>;
};

type CapacitorGlobal = { Capacitor?: { Plugins?: { AppAuth?: AppAuthPlugin } } };

/** 앱의 길로 빌드했는가. 시험이 바꿀 수 있게 부를 때마다 읽는다 */
export function usesAppAuth(value: string | undefined = import.meta.env.VITE_AUTH_TRANSPORT as string | undefined): boolean {
  if (value === undefined || value === '' || value === 'web') return false;
  if (value === 'app') return true;
  throw new Error(`VITE_AUTH_TRANSPORT 는 web 이나 app 이다: ${value}`);
}

/** 앱 껍데기가 심은 플러그인. 없으면 앱의 길로 빌드한 화면을 브라우저에서 연 것이다 */
export function appAuthPlugin(): AppAuthPlugin {
  const plugin = (globalThis as CapacitorGlobal).Capacitor?.Plugins?.AppAuth;
  if (!plugin) throw new Error('앱의 로그인 플러그인(AppAuth)이 없다. 앱 껍데기에서만 연다');
  return plugin;
}

/** 플러그인의 답을 fetch 의 응답 모양으로. 화면의 나머지(오류 읽기, 상태 코드 다루기)가 웹과 같은 코드를 쓴다 */
export function answerToResponse(answer: NativeAnswer): Response {
  const empty = answer.body === undefined || answer.status === 204;
  return new Response(empty ? null : JSON.stringify(withoutRefreshToken(answer.body)), {
    status: answer.status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** 플러그인이 약속을 어기고 refresh 토큰을 넘겨도 화면에는 남기지 않는다 */
function withoutRefreshToken(body: unknown): unknown {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return body;
  const { refresh_token: _token, refresh_expires_in: _expiresIn, ...rest } = body as Record<string, unknown>;
  return rest;
}

/** 플러그인을 불러 응답 모양으로 받는다. reject 는 서버에 닿지 못한 것이다 */
async function call(work: (plugin: AppAuthPlugin) => Promise<NativeAnswer>): Promise<Response> {
  const plugin = appAuthPlugin();
  try {
    return answerToResponse(await work(plugin));
  } catch (error) {
    throw new NetworkError(error);
  }
}

/** 토큰을 주는 답을 읽는다. 실패면 ApiError 를 던진다 */
async function readTokens(response: Response): Promise<LoginResponse> {
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as LoginResponse;
}

/** 로그인 2단계 */
export async function appVerifyLogin(loginTicket: string, code: string): Promise<LoginResponse> {
  return readTokens(await call((plugin) => plugin.verifyLogin({ loginTicket, code })));
}

/** 갱신. 상태 코드를 다루는 것은 refresh.ts 가 웹과 같이 한다 */
export function appRefresh(): Promise<Response> {
  return call((plugin) => plugin.refresh());
}

/** 로그아웃. 실패면 ApiError 를 던진다(서버에 닿지 못한 것은 NetworkError) */
export async function appLogout(): Promise<void> {
  const response = await call((plugin) => plugin.logout());
  if (!response.ok) throw await toApiError(response);
}

/** 비밀번호 변경. 다른 기기는 로그아웃되고 이 기기는 새 토큰을 받는다 */
export async function appChangePassword(
  accessToken: string,
  currentPassword: string,
  newPassword: string,
): Promise<LoginResponse> {
  return readTokens(await call((plugin) => plugin.changePassword({ accessToken, currentPassword, newPassword })));
}
