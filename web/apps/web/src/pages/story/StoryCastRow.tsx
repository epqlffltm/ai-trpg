// web/apps/web/src/pages/story/StoryCastRow.tsx
// 장면의 인물 줄과 인물 메뉴(D2, D5 의 일부). 인물을 누르면 메뉴가 열리고 건네기(가진 물건 하나)와 고백(한 번 더 묻는다)을 한다.
// 고백은 고백이 있는 인물에게만, 엔딩 전에만 보인다. 성공과 실패, 고백을 받지 않는 기간은 엔진이 정한다(422 cooling_down).
// 받는 중이거나 끝난 세션이면 메뉴의 행동을 막는다.

import { Button, Dialog, Radio } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { StoryAction, StoryState } from '../../api/story';
import { canConfess, heldItems } from './storyActions';
import { castName } from './storyWorld';

type Props = { document: Record<string, unknown>; state: StoryState; cast: string[]; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

export function StoryCastRow({ document, state, cast, disabled, onAct }: Props) {
  const [chosen, setChosen] = useState<string | null>(null);
  const close = useCallback(() => setChosen(null), []);
  return (
    <section className="story-cast" aria-label="장면의 인물">
      {cast.length === 0 ? <p className="hint">이 장면에는 아무도 없습니다.</p> : null}
      <ul className="plain-list story-cast__list">
        {cast.map((id) => (
          <li key={id}>
            <button type="button" className="story-cast__member" onClick={() => setChosen(id)}>
              {castName(document, id)}
            </button>
          </li>
        ))}
      </ul>
      <Dialog title={chosen ? castName(document, chosen) : '인물'} open={chosen !== null} onClose={close}>
        {chosen ? (
          <CastMenu
            document={document}
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

type MenuProps = { document: Record<string, unknown>; state: StoryState; castId: string; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

function CastMenu({ document, state, castId, disabled, onAct }: MenuProps) {
  const items = heldItems(document, state.items);
  const [item, setItem] = useState('');
  const [confirming, setConfirming] = useState(false);
  const name = castName(document, castId);

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
      {canConfess(document, state, castId) ? (
        <Button variant="quiet" disabled={disabled} onClick={() => setConfirming(true)}>
          고백
        </Button>
      ) : null}
    </div>
  );
}
