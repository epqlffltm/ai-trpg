// web/apps/web/src/components/revealProblem.ts
// 폼을 보낸 뒤 실패를 사용자 눈앞에 데려온다. 휴대폰에서는 보내기 버튼이 맨 아래에 있어, 위쪽의 칸 밑이나 폼 머리에 뜬 글이
// 화면 밖에 남아 "눌러도 반응이 없다"로 보였다(가입 3단계, 2026-11-07).
//
//   - 그 폼에 틀린 칸(aria-invalid)이 있으면 첫 칸으로 스크롤하고 커서를 둔다. 칸 밑에 서버의 글이 있다
//   - 없으면(칸을 가르지 않는 실패, 체크 상자의 오류) 실패의 한 줄로 스크롤하고 거기에 초점을 둔다. 화면 읽기가 그 글을 읽는다

/** notice 는 실패의 한 줄(ProblemNotice). 그것이 든 폼에서 틀린 첫 칸을 찾는다 */
export function revealProblem(notice: HTMLElement): void {
  const field = notice.closest('form')?.querySelector<HTMLElement>('[aria-invalid="true"]');
  const target = field ?? notice;
  // jsdom 처럼 scrollIntoView 가 없는 곳에서는 초점만 둔다
  target.scrollIntoView?.({ block: 'center' });
  target.focus({ preventScroll: true });
}
