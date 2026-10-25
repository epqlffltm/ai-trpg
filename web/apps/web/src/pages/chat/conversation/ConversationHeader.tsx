// web/apps/web/src/pages/chat/conversation/ConversationHeader.tsx
// 대화(C3)의 머리. 캐릭터 이름(소개 C2 로 가는 길), 호감도(제작자가 고른 방식), 지금 장소와 시각, 모델과 "바꾸기".
// 모델이 없거나 쓸 수 없게 됐으면 몰래 바꾸지 않고 알린다. 고르는 것은 사람이다.

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { ConversationDetail } from '../../../api/types';
import { retireText } from '../../trpg/models/modelChoice';
import { affectionView, clockLabel, placeName } from './conversationView';

type Props = { detail: ConversationDetail; busy: boolean; onChooseModel: () => void };

export function ConversationHeader({ detail, busy, onChooseModel }: Props) {
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
        <Button variant="secondary" disabled={busy} onClick={onChooseModel}>
          {detail.model ? '모델 바꾸기' : '모델 고르기'}
        </Button>
      </div>
    </header>
  );
}
