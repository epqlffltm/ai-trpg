// web/apps/web/src/layout/accountMenuView.ts
// 위쪽 줄 프로필 메뉴(Stitch 설계서의 [모든 화면의 틀])의 길과 "다음 출석까지"의 글. 순수한 함수다.
// 마이페이지의 칸으로 가는 길은 그 칸의 제목 id 를 #로 단다. 마이페이지와 설정이 그 칸까지 내려 준다(useHashScroll).

export type MenuLink = { to: string; label: string };

/** 맞춤 설정: 성향 필터(설정의 목록 거르기), 차단 관리(마이페이지 설정 탭의 차단) */
export const TUNE_LINKS: MenuLink[] = [
  { to: '/settings#listing-filter-heading', label: '성향 필터' },
  { to: '/me?tab=settings#my-blocks-heading', label: '차단 관리' },
];

/** MY 묶음의 길. 설계서의 차례에 이 창에 있던 설정을 맨 끝에 둔다 */
export const MY_LINKS: MenuLink[] = [
  { to: '/me', label: '마이페이지' },
  { to: '/me?tab=creator', label: '내 작품' },
  { to: '/me/hearts', label: '관심 작품' },
  { to: '/me?tab=settings#my-following-heading', label: '팔로잉 제작자' },
  { to: '/me/personas', label: '페르소나' },
  { to: '/gallery', label: '갤러리' },
  { to: '/me?tab=settings#my-invite-heading', label: '내 초대 코드' },
  { to: '/me?tab=settings#my-badges-heading', label: '활동 배지' },
  { to: '/settings', label: '설정' },
];

/** 제작자 대시보드(마이페이지의 제작자 탭) */
export const CREATOR_LINK: MenuLink = { to: '/me?tab=creator', label: '제작자 대시보드' };

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/**
 * 다음 출석까지 남은 때("04:54:18"). 출석의 날짜는 한국 날짜라 서버가 준 오늘(YYYY-MM-DD)의 다음 날 0시(+09:00)까지다.
 * 날짜를 읽지 못하거나 이미 지났으면 null
 */
export function untilNextAttendance(today: string, now: number): string | null {
  const midnight = Date.parse(`${today}T00:00:00+09:00`);
  if (Number.isNaN(midnight)) return null;
  const left = midnight + DAY - now;
  if (left <= 0) return null;
  const hours = Math.floor(left / HOUR);
  const minutes = Math.floor((left % HOUR) / MINUTE);
  const seconds = Math.floor((left % MINUTE) / SECOND);
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, '0')).join(':');
}
