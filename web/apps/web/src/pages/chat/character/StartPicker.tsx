// web/apps/web/src/pages/chat/character/StartPicker.tsx
// 시작 상황을 골라 "시작"(C2). 판의 시작 상황마다 제목, 상황, 시작 시각. 처음 것이 골라져 있다.
// 로그인하지 않았으면 고를 수는 있고, 단추는 로그인으로 보낸다(마치면 이 화면으로 돌아온다).
// 페르소나와 모델은 고르지 않는다. 서버가 지난번 것을 쓴다(처음이면 없이 시작하고 대화에서 고른다).

import { Button, Notice, Radio } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router';
import type { PublicCharacterDetail } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { startTimeLabel } from './characterView';
import { useStartConversation } from './useStartConversation';

type Start = PublicCharacterDetail['document']['starts'][number];

export function StartPicker({ characterId, starts }: { characterId: string; starts: Start[] }) {
  const [chosen, setChosen] = useState(0);
  const starting = useStartConversation(characterId);
  const index = chosen < starts.length ? chosen : 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    starting.start(index);
  }

  return (
    <form className="character-starts" aria-labelledby="character-starts" onSubmit={submit}>
      <h2 id="character-starts">시작 상황</h2>
      <fieldset className="character-starts__list">
        <legend className="visually-hidden">시작 상황 고르기</legend>
        {starts.map((start, position) => (
          <Radio
            key={`${position}-${start.title}`}
            name="start"
            label={start.title}
            description={
              <>
                <p className="prose">{start.situation}</p>
                <p className="hint">{startTimeLabel(start.hour)}</p>
              </>
            }
            checked={index === position}
            onChange={() => setChosen(position)}
          />
        ))}
      </fieldset>
      {starting.problem ? (
        <Notice tone="error">
          {starting.problem.text} {starting.problem.needsAdult ? <Link to="/me/identity">본인인증하기</Link> : null}
        </Notice>
      ) : null}
      <StartButton busy={starting.busy} />
    </form>
  );
}

function StartButton({ busy }: { busy: boolean }) {
  const signedIn = useSession() !== null;
  const location = useLocation();
  if (!signedIn) {
    return (
      <Link className="ui-button ui-button--primary" to="/login" state={{ from: location.pathname }}>
        로그인하고 대화 시작
      </Link>
    );
  }
  return (
    <Button type="submit" busy={busy}>
      대화 시작
    </Button>
  );
}
