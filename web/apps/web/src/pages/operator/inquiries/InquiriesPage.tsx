// web/apps/web/src/pages/operator/inquiries/InquiriesPage.tsx
// 운영자의 문의함(/operator/inquiries). 운영자만 열린다(RequireOperator). 메일함처럼 본다.
//   - 위: 상자 탭(모두, 답 기다림, 답함과 수, 지운 기록)과 안 읽은 수
//   - 도구 줄: 보이는 줄 모두 고르기, 고른 것 지우기, 이 상자 비우기(둘 다 한 번 더 묻는다)
//   - 목록: 줄마다 고르기, 보낸 사람, 종류, 제목, 보낸 때. 안 읽은 줄은 굵다. 누르면 아래에 그 문의가 열린다(?id=)
//   - 열린 문의: 내용, 누가 열었는지, 답(누가 답했는지와 답 메일), 답하지 않았으면 답 쓰기, 지우기
// 상자는 ?box=, 열린 문의는 ?id= 로 주소에 둔다(새로 고쳐도, 링크로도 같은 곳). 시안에는 이 화면이 없어 알림 화면(Stitch 9번)의 목록 틀을 쓴다.

import { useInfiniteQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';
import { InquiryActions } from './InquiryActions';
import { InquiryBox } from './InquiryBox';
import { adminInquiriesQuery } from './inquiryBoxQueries';
import { BOXES, boxLabel, boxOf, type Box } from './inquiryBoxView';

export function InquiriesPage() {
  const [params, setParams] = useSearchParams();
  const box = boxOf(params.get('box'));
  // 상자마다의 수는 어느 목록의 답에나 실려 온다. 답 기다림의 목록을 늘 읽어 탭의 수로 쓴다
  const counts = useInfiniteQuery(adminInquiriesQuery('open')).data?.pages[0]?.counts;
  const openId = params.get('id');

  function go(next: { box?: Box; id?: string | null }) {
    const query: Record<string, string> = { box: next.box ?? box };
    const id = next.id === undefined ? openId : next.id;
    if (id) query.id = id;
    setParams(query);
  }

  return (
    <main className="page operator-page inquiry-box-page">
      <div className="page-head">
        <h1>문의함</h1>
        {counts ? <p className="hint">안 읽은 문의 {counts.unread}개</p> : null}
      </div>
      <p className="hint">문의는 보낸 지 1년이 지나면 지워집니다. 지운 일은 누가 했는지와 함께 "지운 기록"에 남습니다.</p>
      <nav className="inquiry-box__tabs" aria-label="상자">
        {BOXES.map((item) => (
          <button
            key={item.value}
            type="button"
            className="inquiry-box__tab"
            aria-current={item.value === box ? 'page' : undefined}
            onClick={() => go({ box: item.value, id: null })}
          >
            {boxLabel(item.value, counts)}
          </button>
        ))}
      </nav>
      {box === 'actions' ? <InquiryActions /> : <InquiryBox key={box} box={box} openId={openId} onOpen={(id) => go({ id })} />}
    </main>
  );
}
