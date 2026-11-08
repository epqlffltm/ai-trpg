// web/apps/web/src/pages/conversations/ConversationsPage.tsx
// 최근 대화(/conversations). 좁은 화면의 맨 아래 탭 바 "대화"가 여는 화면이다(Stitch 설계서의 [모든 화면의 틀]: "대화(최근 대화)").
// 로그인해야 열린다(RequireSession). 왼쪽 메뉴 열의 최근 대화와 같은 묶음 셋(TRPG 테이블, chat 대화, story 세션)을 줄을 늘려 보인다.
// 서비스끼리 섞어 정렬하지 않고, 묶음마다 "전체 보기"로 그 서비스에 간다.

import { RecentGroups } from '../../layout/SidebarRecent';
import { RECENT_PAGE_ROWS } from '../../layout/sidebarRecentView';

export function ConversationsPage() {
  return (
    <main className="page page--medium">
      <h1>최근 대화</h1>
      <section className="sidebar-recent" aria-label="최근 대화 묶음">
        <RecentGroups rowCount={RECENT_PAGE_ROWS} />
      </section>
    </main>
  );
}
