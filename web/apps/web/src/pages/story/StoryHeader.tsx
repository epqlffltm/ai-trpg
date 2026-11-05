// web/apps/web/src/pages/story/StoryHeader.tsx
// 장면(D2)의 머리(Stitch 22번의 장면 줄). 세계관 이름, "2장: 축제 · 3일째 · 저녁 · 학교 · D-97"(장이 없는 판은 장을 쓰지 않는다.
// 엔딩을 봤으면 엔딩의 이름, 후일담이면 "후일담"), 모델의 이름. 상태는 서버의 값이다.
// 모델과 페르소나를 바꾸는 것은 왼쪽 열의 페르소나·모델 창(StoryPersonaPanel)이다. 모델을 쓸 수 없게 됐으면 여기서도 알린다(창을 접어 두어도 보이게).

import { Link } from 'react-router';
import type { StorySession, StoryState } from '../../api/story';
import { retireText } from '../trpg/models/modelChoice';
import { hasEpilogue, stateLine } from './storyWorld';

type Props = { session: StorySession; state: StoryState };

export function StoryHeader({ session, state }: Props) {
  const epilogue = state.ending !== null && hasEpilogue(session.view);
  return (
    <header className="conversation__head">
      <div className="conversation__who">
        <p className="hint">
          <Link to="/story">내 이야기</Link>
        </p>
        <h1>{session.world.name}</h1>
        <p className="hint">
          {stateLine(session.view, state)}
          {epilogue ? ' · 후일담' : ''}
        </p>
      </div>
      <div className="conversation__model">
        <p className="hint">
          모델: {session.model ? session.model.display_name : '고르지 않음'}
          {session.model?.retires_on ? ` · ${retireText(session.model.retires_on)}` : null}
        </p>
        {session.model && !session.model.usable ? <p className="ui-field__error">지금 쓸 수 없는 모델입니다. 페르소나·모델 창에서 다른 모델을 골라 주세요.</p> : null}
      </div>
    </header>
  );
}
