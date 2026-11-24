// web/apps/web/src/pages/story/StoryPersonaPanel.tsx
// 장면(D2)의 왼쪽 열 "페르소나·모델" 창(Stitch 22번, chat 의 같은 창과 같은 모양).
// 지금의 페르소나와 "페르소나 바꾸기"(StoryPersonaButton 의 창), 지금의 모델(끝나는 날)과 "모델 바꾸기"(고르는 창은 StoryRoom 이 연다).
// 세계관이 허용하면 참고 자료 쓰기도 여기에 둔다(#1338).
// 모델이 쓸 수 없게 됐으면 몰래 바꾸지 않고 알린다. 받는 중에는 바꾸기를 막는다.

import { Button } from '@ai-trpg/ui';
import { chooseStoryReferences, type StorySession } from '../../api/story';
import { ReferencesToggle } from '../../components/ReferencesToggle';
import { useReferencesChoice } from '../../components/useReferencesChoice';
import { retireText } from '../trpg/models/modelChoice';
import { StoryPersonaButton } from './StoryPersonaButton';
import { personaLabel } from './storyPersonaView';
import { storySessionKey } from './storyQueries';

type Props = { session: StorySession; disabled: boolean; onChooseModel: () => void };

export function StoryPersonaPanel({ session, disabled, onChooseModel }: Props) {
  const model = session.model;
  const references = useReferencesChoice<StorySession>(storySessionKey(session.id), (enabled) => chooseStoryReferences(session.id, enabled));
  return (
    <div className="chat-persona">
      <dl>
        <div>
          <dt>나(페르소나)</dt>
          <dd>{personaLabel(session.persona)}</dd>
        </div>
        <div>
          <dt>모델</dt>
          <dd>
            {model ? model.display_name : '고르지 않음'}
            {model?.retires_on ? <span className="hint"> · {retireText(model.retires_on)}</span> : null}
          </dd>
        </div>
      </dl>
      {model && !model.usable ? <p className="ui-field__error">지금 쓸 수 없는 모델입니다. 다른 모델을 골라 주세요.</p> : null}
      <div className="actions">
        <Button variant="secondary" disabled={disabled} onClick={onChooseModel}>
          {model ? '모델 바꾸기' : '모델 고르기'}
        </Button>
        <StoryPersonaButton session={session} disabled={disabled} />
      </div>
      <ReferencesToggle
        allowed={session.references_allowed}
        enabled={session.references_enabled}
        disabled={disabled || references.isPending}
        error={references.error}
        onChange={(enabled) => references.mutate(enabled)}
      />
    </div>
  );
}
