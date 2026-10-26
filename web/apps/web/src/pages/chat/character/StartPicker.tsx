// web/apps/web/src/pages/chat/character/StartPicker.tsx
// 시작 상황을 골라 "시작"(C2). 판의 시작 상황마다 제목, 상황, 시작 시각. 처음 것이 골라져 있다.
// 로그인하지 않았으면 고를 수는 있고, 단추는 로그인으로 보낸다(마치면 이 화면으로 돌아온다).
// 로그인했고 페르소나가 있으면 "나"로 쓸 페르소나를 고른다. 기본 페르소나가 골라져 있고 "페르소나 없이"도 고를 수 있다.
// 페르소나가 없으면 보내지 않는다(서버가 지난번 대화의 것을 쓰고, 없으면 없이 시작한다). 모델은 고르지 않는다(대화에서 고른다).

import { Button, Notice, Radio, SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router';
import type { PublicCharacterDetail } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { personasQuery } from '../../personas/personaQueries';
import { startTimeLabel } from './characterView';
import { useStartConversation } from './useStartConversation';

type Start = PublicCharacterDetail['document']['starts'][number];

export function StartPicker({ characterId, starts }: { characterId: string; starts: Start[] }) {
  const [chosen, setChosen] = useState(0);
  const [persona, setPersona] = useState<PersonaPick>(undefined);
  const signedIn = useSession() !== null;
  const starting = useStartConversation(characterId);
  const index = chosen < starts.length ? chosen : 0;
  const personas = usePersonaList(signedIn);
  const defaultPersona = personas.find((entry) => entry.is_default)?.id ?? personas[0]?.id;

  function submit(event: FormEvent) {
    event.preventDefault();
    starting.start({ start: index, persona: persona === undefined ? defaultPersona : persona });
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
      {personas.length > 0 ? <PersonaSelect personas={personas} value={persona === undefined ? defaultPersona : persona} onChange={setPersona} /> : null}
      {starting.problem ? (
        <Notice tone="error">
          {starting.problem.text} {starting.problem.needsAdult ? <Link to="/me/identity">본인인증하기</Link> : null}
        </Notice>
      ) : null}
      <StartButton busy={starting.busy} />
    </form>
  );
}

/** 고른 페르소나. undefined 는 아직 고르지 않음(기본을 쓴다), null 은 "페르소나 없이" */
type PersonaPick = string | null | undefined;

const WITHOUT_PERSONA = '';

/** 내 페르소나. 로그인했을 때만 읽고, 읽지 못하면 빈 목록(보내지 않는다) */
function usePersonaList(signedIn: boolean) {
  const query = useQuery({ ...personasQuery(), enabled: signedIn });
  return query.data ?? [];
}

type SelectProps = { personas: { id: string; name: string; is_default: boolean }[]; value: string | null | undefined; onChange: (value: string | null) => void };

function PersonaSelect({ personas, value, onChange }: SelectProps) {
  return (
    <SelectField
      label="나(페르소나)"
      value={value ?? WITHOUT_PERSONA}
      onChange={(event) => onChange(event.target.value === WITHOUT_PERSONA ? null : event.target.value)}
      hint="상대가 읽는 나의 설정입니다. 시작할 때의 설정을 복사해 둡니다."
    >
      {personas.map((entry) => (
        <option key={entry.id} value={entry.id}>
          {entry.is_default ? `${entry.name}(기본)` : entry.name}
        </option>
      ))}
      <option value={WITHOUT_PERSONA}>페르소나 없이</option>
    </SelectField>
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
