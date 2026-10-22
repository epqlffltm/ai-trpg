// web/apps/web/src/auth/safeReturnPath.ts
// 로그인이 끝나면 돌아갈 화면의 주소. 이 앱 안의 경로만 받는다.
// "//evil.example" 이나 "https://..." 를 받으면 로그인 뒤에 다른 사이트로 보내게 된다(열린 리다이렉트).

const HOME = '/';

export function safeReturnPath(candidate: unknown): string {
  if (typeof candidate !== 'string') return HOME;
  if (!candidate.startsWith('/') || candidate.startsWith('//') || candidate.startsWith('/\\')) return HOME;
  if (candidate === '/login' || candidate.startsWith('/login?')) return HOME;
  return candidate;
}
