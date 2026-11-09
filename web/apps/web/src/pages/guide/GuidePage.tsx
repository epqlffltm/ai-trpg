// web/apps/web/src/pages/guide/GuidePage.tsx
// 이용 가이드(/guide). 왼쪽 메뉴 열 맨 아래의 "이용 가이드"에서 온다(Stitch 설계서의 [모든 화면의 틀]). 로그인하지 않아도 열린다.
// 위에 묶음의 목차, 아래에 묶음마다 물음을 접어 둔다(펼치면 답). 글은 guideContent.ts 에 있다. 맨 아래에 고객센터로 가는 길.
// 시안에 이 화면은 따로 없어 다른 계정 화면(page-section)의 틀을 쓴다.

import { Link } from 'react-router';
import { GUIDE, type GuideSection } from './guideContent';

export function GuidePage() {
  return (
    <main className="page page--medium guide-page">
      <h1>이용 가이드</h1>
      <nav aria-label="가이드 목차">
        <ul className="plain-list guide-page__toc">
          {GUIDE.map((section) => (
            <li key={section.id}>
              <a href={`#guide-${section.id}`}>{section.title}</a>
            </li>
          ))}
        </ul>
      </nav>
      {GUIDE.map((section) => (
        <GuideBlock key={section.id} section={section} />
      ))}
      <p className="hint">
        찾는 답이 없으면 <Link to="/support">고객센터</Link>로 문의해 주세요.
      </p>
    </main>
  );
}

function GuideBlock({ section }: { section: GuideSection }) {
  const headingId = `guide-${section.id}`;
  return (
    <section className="page-section" aria-labelledby={headingId}>
      <h2 id={headingId}>{section.title}</h2>
      <div className="guide-page__items">
        {section.items.map((item) => (
          <details key={item.question} className="guide-item">
            <summary>{item.question}</summary>
            {item.answer.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </details>
        ))}
      </div>
    </section>
  );
}
