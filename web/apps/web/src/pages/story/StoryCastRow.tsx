// web/apps/web/src/pages/story/StoryCastRow.tsx
// 장면의 인물 줄(그림과 이름)과 인물 창(D2 의 인물 메뉴, D5). 인물을 누르면 창이 열린다.
// 창의 위는 인물 창(D5): 소개, 나이·성별, 호감도(숫자나 단계), 고백 대기, 건넨 선물, 함께 본 이벤트. 제작자가 고른 항목만 서버가 보낸다.
// 아래는 행동: 건네기(가진 물건 하나), 고백(고백할 수 있는 인물에게만, 엔딩 전에만, 한 번 더 묻는다. 대기 중이면 막고 그때를 알린다).
// 인물의 그림은 끝의 답에서 그 인물이 마지막으로 지은 표정의 스프라이트다(없으면 기본 표정). 실루엣 인물은 "???" 와 검은 칸이다. 받는 중이거나 끝난 세션이면 행동을 막는다.

import { Button, Dialog, Radio } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { StoryAction, StoryState, StoryView, StoryViewCast } from '../../api/story';
import { useImageUrl } from '../../hooks/useImageUrl';
import { IntroHtml } from '../chat/character/IntroHtml';
import { canConfess, heldItems } from './storyActions';
import { affectionText, coolingText, eventNames, giftNames, portraitOf, profileLine } from './storyCastView';
import { castName, castOf } from './storyWorld';

type Props = { view: StoryView; state: StoryState; cast: string[]; expressions: Record<string, string | null>; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

export function StoryCastRow({ view, state, cast, expressions, disabled, onAct }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  const close = useCallback(() => setChosen(null), []);
  return (
    <section className="story-cast" aria-label="장면의 인물">
      {cast.length === 0 ? <p className="hint">이 장면에는 아무도 없습니다.</p> : null}
      <ul className="plain-list story-cast__list">
        {cast.map((id) => (
          <li key={id}>
            <button type="button" className="story-cast__member" onClick={() => setChosen(id)}>
              <Portrait cast={castOf(view, id)} expression={expressions[id] ?? null} />
              <span>{castName(view, id)}</span>
            </button>
          </li>
        ))}
      </ul>
      <Dialog title={chosen ? castName(view, chosen) : '인물'} open={chosen !== null} onClose={close}>
        {chosen ? (
          <CastMenu
            view={view}
            state={state}
            castId={chosen}
            disabled={disabled}
            onAct={(action) => {
              setChosen(null);
              return onAct(action);
            }}
          />
        ) : null}
      </Dialog>
    </section>
  );
}

function Portrait({ cast, expression }: { cast: StoryViewCast | undefined; expression: string | null }) {
  const image = useImageUrl(portraitOf(cast, expression));
  const silhouette = !cast || cast.reveal === 'silhouette';
  if (image.url) return <img src={image.url} alt="" className="story-cast__portrait" />;
  return <span className={silhouette ? 'story-cast__portrait story-cast__portrait--silhouette' : 'story-cast__portrait'} aria-hidden="true" />;
}

/** 인물 창(D5). 서버가 보낸 항목만 그린다 */
function CastProfile({ view, state, cast }: { view: StoryView; state: StoryState; cast: StoryViewCast }) {
  const profile = profileLine(cast);
  const affection = affectionText(cast, state.affection[cast.id]);
  const cooling = coolingText(cast, state.minutes);
  const gifts = giftNames(view, cast);
  const events = eventNames(view, cast);
  return (
    <div className="story-profile">
      {profile ? <p className="hint">{profile}</p> : null}
      {affection ? <p>{affection}</p> : null}
      {cooling ? <p className="hint">{cooling}</p> : null}
      {cast.intro_html ? <IntroHtml html={cast.intro_html} /> : null}
      {gifts.length > 0 ? <p className="hint">건넨 선물: {gifts.join(', ')}</p> : null}
      {events.length > 0 ? <p className="hint">함께 본 이벤트: {events.join(', ')}</p> : null}
    </div>
  );
}

type MenuProps = { view: StoryView; state: StoryState; castId: string; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

function CastMenu({ view, state, castId, disabled, onAct }: MenuProps) {
  const items = heldItems(view, state.items);
  const [item, setItem] = useState('');
  const [confirming, setConfirming] = useState(false);
  const name = castName(view, castId);
  const cast = castOf(view, castId);
  const cooling = cast ? coolingText(cast, state.minutes) : null;

  if (confirming) {
    return (
      <div className="story-confess">
        <p>{name}에게 고백합니다. 성공과 실패는 지금까지의 관계로 정해지고, 엔딩이 열릴 수 있습니다.</p>
        <div className="actions">
          <Button disabled={disabled} onClick={() => void onAct({ kind: 'confess', cast: castId })}>
            고백하기
          </Button>
          <Button variant="quiet" onClick={() => setConfirming(false)}>
            그만두기
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="story-cast-menu">
      {cast ? <CastProfile view={view} state={state} cast={cast} /> : null}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (item) void onAct({ kind: 'give', cast: castId, item });
        }}
      >
        <fieldset className="choice-list">
          <legend>건넬 물건</legend>
          {items.length === 0 ? <p className="hint">건넬 물건이 없습니다.</p> : null}
          {items.map((entry) => (
            <Radio key={entry.id} name="story-gift" label={`${entry.name} × ${entry.count}`} checked={item === entry.id} onChange={() => setItem(entry.id)} />
          ))}
        </fieldset>
        <Button type="submit" variant="secondary" disabled={disabled || !item}>
          건네기
        </Button>
      </form>
      {canConfess(view, state, castId) ? (
        <Button variant="quiet" disabled={disabled || cooling !== null} onClick={() => setConfirming(true)}>
          고백
        </Button>
      ) : null}
    </div>
  );
}
