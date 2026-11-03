// web/apps/web/src/pages/me/inviteView.ts
// 초대 코드(#990)를 보이고 나누는 데 쓰는 순수한 함수들. 화면을 그리지 않는다.

/** 가입 화면의 주소에서 초대 코드를 읽는 칸의 이름(/signup?invite=코드) */
export const INVITE_PARAM = 'invite';

/** 친구에게 보낼 가입 주소. origin 은 이 사이트의 주소(location.origin)다 */
export function inviteLink(origin: string, code: string): string {
  return `${origin}/signup?${new URLSearchParams({ [INVITE_PARAM]: code }).toString()}`;
}

/** 받은 보상의 한 줄. 상한이 0 이면 초대 보상이 꺼져 있다 */
export function rewardLine(rewarded: number, limit: number): string {
  if (limit === 0) return '지금은 초대 보상을 주지 않습니다.';
  return `받은 초대 보상 ${Math.min(rewarded, limit)} / ${limit}번`;
}
