// web/apps/web/src/pages/chat/conversation/ConversationHeader.tsx
// 대화(C3)의 머리(Stitch 21번의 대화 줄). 캐릭터 이름(소개 C2 로 가는 길), 호감도(제작자가 고른 방식), 지금 장소와 시각, 모델.
// 모델을 바꾸는 단추는 왼쪽 열의 "페르소나·모델" 창에 있다(ChatTools).
// 모델이 없거나 쓸 수 없게 됐으면 몰래 바꾸지 않고 알린다. 고르는 것은 사람이다.

import { Link } from 'react-router';
import type { ConversationDetail } from '../../../api/types';
import { retireText } from '../../trpg/models/modelChoice';
import { affectionView, clockLabel, placeName } from './conversationView';

type Props = { detail: ConversationDetail };

export function ConversationHeader({ detail }: Props) {
  const document = detail.character.document;
  const affection = affectionView(detail.state.affection);
  const where = [detail.state.place ? placeName(document, detail.state.place) : null, clockLabel(detail.state.clock)].filter(Boolean).join(' · ');
  return (
    <header className="conversation__head">
      <div className="conversation__who">
        <h1>
          <Link to={`/chat/characters/${detail.character.id}`}>{document.name}</Link>
        </h1>
        <p className="hint">{where}</p>
        {affection ? (
          <div className="conversation__affection">
            <span>{affection.label}</span>
            <progress max={100} value={affection.percent} aria-label="호감도" />
          </div>
        ) : null}
      </div>
      <div className="conversation__model">
        <p className="hint">
          모델: {detail.model ? detail.model.display_name : '고르지 않음'}
          {detail.model?.retires_on ? ` · ${retireText(detail.model.retires_on)}` : null}
        </p>
        {detail.model && !detail.model.usable ? <p className="ui-field__error">지금 쓸 수 없는 모델입니다. 다른 모델을 골라 주세요.</p> : null}
      </div>
    </header>
  );
}
