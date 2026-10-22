// web/apps/web/src/auth/safeReturnPath.ts
// 로그인이 끝나면 돌아갈 화면의 주소. 이 앱 안의 경로만 받는다.
// "//evil.example" 이나 "https://..." 를 받으면 로그인 뒤에 다른 사이트로 보내게 된다(열린 리다이렉트).

const HOME = '/';
// 로그인한 뒤에 돌아갈 까닭이 없는 화면(로그인, 가입, 비밀번호). 그곳에서 왔으면 첫 화면으로 간다
const AUTH_PATHS = ['/login', '/signup', '/password', '/reset-password'];

export function safeReturnPath(candidate: unknown): string {
  if (typeof candidate !== 'string') return HOME;
  if (!candidate.startsWith('/') || candidate.startsWith('//') || candidate.startsWith('/\\')) return HOME;
  const pathname = candidate.split(/[?#]/)[0] ?? '';
  if (AUTH_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))) return HOME;
  return candidate;
}
