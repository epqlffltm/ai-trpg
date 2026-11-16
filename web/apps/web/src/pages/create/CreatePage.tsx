// web/apps/web/src/pages/create/CreatePage.tsx
// 만들기의 입구(Stitch 12번). 왼쪽 메뉴 열의 "만들기"와 아래 탭 바의 "만들기"가 여기로 온다.
// 위에 작품의 카드 넷(TRPG 시나리오, TRPG 캠페인, 캐릭터, 스토리 세계), 그 아래 TRPG 의 재료 카드 넷(룰북, 세계관, 로어북, 몬스터 모음).
// 카드를 누르면 그것을 새로 만드는 화면으로 간다. 스토리 세계에는 "JSON 으로 세계관 넣기"가 붙는다(지금은 운영자만 연다).
// 내가 만든 것은 마이페이지의 제작자 탭(내 작품)에 있다. 서비스를 섞은 "내 작품" 목록은 서버에 없어 길만 둔다.

import { Link } from 'react-router';
import { isOperator } from '../../auth/roles';
import { useSession } from '../../auth/useSession';
import { myTabPath } from '../me/myTabs';
import { MATERIAL_CARDS, WORK_CARDS, WORLD_IMPORT_PATH, type CreateCard } from './createTargets';

export function CreatePage() {
  const operator = isOperator(useSession());
  return (
    <main className="page create-page">
      <div className="create-page__head">
        <h1>만들기</h1>
        <Link className="ui-button ui-button--secondary" to={myTabPath('creator')}>
          내 작품 보기
        </Link>
      </div>
      <section aria-labelledby="create-works">
        <h2 id="create-works" className="create-page__title">
          새로 만들기
        </h2>
        <ul className="create-cards" aria-label="새로 만들 작품">
          {WORK_CARDS.map((card) => (
            <CreateCardItem key={card.key} card={card} extra={card.service === 'story' && operator ? <Link to={WORLD_IMPORT_PATH}>JSON 으로 세계관 넣기</Link> : null} />
          ))}
        </ul>
      </section>
      <section aria-labelledby="create-materials">
        <h2 id="create-materials" className="create-page__title">
          시나리오의 재료
        </h2>
        <ul className="create-cards" aria-label="새로 만들 재료">
          {MATERIAL_CARDS.map((card) => (
            <CreateCardItem key={card.key} card={card} />
          ))}
        </ul>
      </section>
    </main>
  );
}

function CreateCardItem({ card, extra = null }: { card: CreateCard; extra?: React.ReactNode }) {
  return (
    <li className={`create-card create-card--${card.service}`}>
      <Link to={card.to} className="create-card__link">
        <span className="create-card__mark" aria-hidden="true">
          {card.title.slice(0, 1)}
        </span>
        <span className="create-card__tag" aria-hidden="true">
          {card.tag}
        </span>
        <span className="create-card__title">{card.title}</span>
        <span className="create-card__line">{card.line}</span>
      </Link>
      {extra ? <p className="create-card__extra">{extra}</p> : null}
    </li>
  );
}
