// web/apps/web/src/pages/operator/ReportsPage.tsx
// 신고 처리(E4, /operator/reports, #678). 운영자만 열린다(RequireOperator). 캐릭터의 신고(asset)와 대화 속 답의 신고(chat)다.
// 시나리오와 게시판 글의 신고는 아직 없다(받는 서버가 정해지면 더한다).
// 조치와 대화의 글을 보는 것은 사유와 함께 감사 기록에 남는다. 당사자에게는 처리했다는 것만 간다.

import { CharacterReportSection } from './CharacterReportSection';
import { MessageReportSection } from './MessageReportSection';

export function ReportsPage() {
  return (
    <main className="page page--medium">
      <h1>신고 처리</h1>
      <p className="hint">
        조치와 대화의 글을 보는 일은 사유와 함께 감사 기록에 남습니다. 신고한 사람에게는 처리했다는 것만, 캐릭터의 주인에게는
        숨김이 바뀐 것만 알립니다.
      </p>
      <CharacterReportSection />
      <MessageReportSection />
    </main>
  );
}
