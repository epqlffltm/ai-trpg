// web/apps/web/src/pages/story/StoryChoices.tsx
// 열린 이벤트의 선택지(D2). 제작자가 적은 글 그대로다. 고르면 행동 말이 되고 엔진이 효과를 반영한 뒤 반응을 받는다.
// 고르지 않고 말을 이어도 된다(선택지는 사라지고 효과는 없다). 받는 중에는 보이지 않는다(답이 끝난 뒤에 보인다).
// 그림 창 위에 겹쳐 띄운다(StagePicture 의 overlay, Stitch 22번). 선택지마다 번호가 붙은 줄이다(번호는 꾸밈).

import type { StoryAction } from '../../api/story';
import type { PendingChoices } from './storyActions';

type Props = { pending: PendingChoices; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

export function StoryChoices({ pending, disabled, onAct }: Props) {
  return (
    <section className="story-choices" aria-label="선택지">
      {pending.eventName ? <p className="story-choices__event">{pending.eventName}</p> : null}
      <ol className="plain-list story-choices__list">
        {pending.choices.map((choice, index) => (
          <li key={choice.id}>
            <button type="button" className="story-choice" disabled={disabled} onClick={() => void onAct({ kind: 'choose', choice: choice.id })}>
              <span className="story-choice__number" aria-hidden="true">
                {index + 1}
              </span>
              <span className="story-choice__text">{choice.text}</span>
            </button>
          </li>
        ))}
      </ol>
      <p className="hint">고르지 않고 말을 이으면 선택지는 사라집니다.</p>
    </section>
  );
}
