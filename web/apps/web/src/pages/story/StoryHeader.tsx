// web/apps/web/src/pages/story/StoryHeader.tsx
// 장면(D2)의 머리. 세계관 이름, "3일째 · 저녁 · 학교 · D-97"(엔딩을 봤으면 엔딩의 이름, 후일담이면 "후일담"), 모델과 "바꾸기".
// 상태는 서버의 값이다. 모델이 없거나 쓸 수 없게 됐으면 몰래 바꾸지 않고 알린다.

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { StorySession, StoryState } from '../../api/story';
import { retireText } from '../trpg/models/modelChoice';
import { hasEpilogue, stateLine } from './storyWorld';

type Props = { session: StorySession; state: StoryState; busy: boolean; onChooseModel: () => void };

export function StoryHeader({ session, state, busy, onChooseModel }: Props) {
  const epilogue = state.ending !== null && hasEpilogue(session.world.document);
  return (
    <header className="conversation__head">
      <div className="conversation__who">
        <p className="hint">
          <Link to="/story">내 이야기</Link>
        </p>
        <h1>{session.world.name}</h1>
        <p className="hint">
          {stateLine(session.world.document, state)}
          {epilogue ? ' · 후일담' : ''}
        </p>
      </div>
      <div className="conversation__model">
        <p className="hint">
          모델: {session.model ? session.model.display_name : '고르지 않음'}
          {session.model?.retires_on ? ` · ${retireText(session.model.retires_on)}` : null}
        </p>
        {session.model && !session.model.usable ? <p className="ui-field__error">지금 쓸 수 없는 모델입니다. 다른 모델을 골라 주세요.</p> : null}
        <Button variant="secondary" disabled={busy} onClick={onChooseModel}>
          {session.model ? '모델 바꾸기' : '모델 고르기'}
        </Button>
      </div>
    </header>
  );
}
