// web/apps/web/src/layout/sidebarRoutes.ts
// 사이트의 왼쪽 메뉴 열을 처음에 접어 둘 화면. 순수한 함수다.
// 플레이 화면(TRPG 테이블 방, chat 대화, story 장면)은 이야기 칸이 넓어야 해서 접어 둔다(☰ 로 연다, Stitch 설계서의 [모든 화면의 틀]).

const PLAY_PATHS = [/^\/trpg\/tables\/(?!new$|past(?:\/|$))[^/]+$/, /^\/chat\/conversations\/[^/]+$/, /^\/story\/sessions\/[^/]+$/];

/** 플레이 화면인지. 그 화면에서는 왼쪽 메뉴 열을 접은 채로 시작한다 */
export function isPlayPath(pathname: string): boolean {
  return PLAY_PATHS.some((pattern) => pattern.test(pathname));
}
