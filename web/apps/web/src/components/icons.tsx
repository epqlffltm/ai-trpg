// web/apps/web/src/components/icons.tsx
// 화면 곳곳의 작은 선 그림(디자인 시스템의 아이콘). 글자 크기를 따라가고(1em) 색은 글자색이다(currentColor).
// 모두 장식이라 읽는 프로그램에는 숨긴다. 이름은 단추의 aria-label 이 맡는다.

import type { ReactNode } from 'react';

function Icon({ children, filled = false }: { children: ReactNode; filled?: boolean }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** 메뉴 열을 펴고 접는 세 줄 */
export function MenuIcon() {
  return (
    <Icon>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </Icon>
  );
}

/** 밝기: 기기 설정을 따름(반쯤 찬 원) */
export function SystemThemeIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" />
    </Icon>
  );
}

/** 밝기: 라이트(해) */
export function SunIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Icon>
  );
}

/** 밝기: 다크(달) */
export function MoonIcon() {
  return (
    <Icon>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
    </Icon>
  );
}

/** 관심. filled 면 둔 것(찬 하트), 아니면 빈 하트 */
export function HeartIcon({ filled = false }: { filled?: boolean }) {
  return (
    <Icon filled={filled}>
      <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" />
    </Icon>
  );
}

/** 받음(체크) */
export function CheckIcon() {
  return (
    <Icon>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </Icon>
  );
}

/** 보물 상자 */
export function ChestIcon() {
  return (
    <Icon>
      <path d="M4 10h16v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1Z" />
      <path d="M4 10V8a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v2" />
      <path d="M10 10v3h4v-3" />
    </Icon>
  );
}

/** 아직 열리지 않음(자물쇠) */
export function LockIcon() {
  return (
    <Icon>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Icon>
  );
}

/** 오늘(별) */
export function StarIcon() {
  return (
    <Icon>
      <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9Z" />
    </Icon>
  );
}

/** 본인 확인(방패) */
export function ShieldIcon() {
  return (
    <Icon>
      <path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6Z" />
      <path d="M9 12l2 2 4-4" />
    </Icon>
  );
}
