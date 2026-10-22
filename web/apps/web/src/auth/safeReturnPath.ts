// web/apps/web/src/auth/safeReturnPath.ts
// 로그인이 끝나면 돌아갈 화면의 주소. 이 앱 안의 경로만 받는다.
// "//evil.example" 이나 "https://..." 를 받으면 로그인 뒤에 다른 사이트로 보내게 된다(열린 리다이렉트).

const HOME = '/';
// 로그인한 뒤에 돌아갈 까닭이 없는 화면(로그인, 가입, 비밀번호). 그곳에서 왔으면 첫 화면으로 간다.
// 다시 동의하거나 탈퇴를 기다리는 중에도 이 화면들은 막지 않는다(재설정 메일의 링크를 여는 것 같은 때, AppLayout)
const AUTH_PATHS = ['/login', '/signup', '/password', '/reset-password'];

/** 로그인, 가입, 비밀번호의 화면인가 */
export function isAuthPath(pathname: string): boolean {
  return AUTH_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function safeReturnPath(candidate: unknown): string {
  if (typeof candidate !== 'string') return HOME;
  if (!candidate.startsWith('/') || candidate.startsWith('//') || candidate.startsWith('/\\')) return HOME;
  const pathname = candidate.split(/[?#]/)[0] ?? '';
  if (isAuthPath(pathname)) return HOME;
  return candidate;
}
