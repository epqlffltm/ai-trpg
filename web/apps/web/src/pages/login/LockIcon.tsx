// web/apps/web/src/pages/login/LockIcon.tsx
// 로그인 카드 위의 자물쇠 그림(장식). 글자 크기를 따라가고 색은 강조색이다.

export function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
      <circle cx="12" cy="16" r="1" />
    </svg>
  );
}
