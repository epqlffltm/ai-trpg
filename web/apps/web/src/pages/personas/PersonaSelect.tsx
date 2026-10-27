// web/apps/web/src/pages/personas/PersonaSelect.tsx
// "나(페르소나)" 고르기. chat 의 시작(C2), story 의 시작(D1)과 장면의 페르소나 바꾸기(D2)가 함께 쓴다.
// 내 페르소나를 기본이 먼저인 차례로 늘어놓고 끝에 "페르소나 없이"를 둔다. 값이 null 이면 페르소나 없이다.

import { SelectField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { personasQuery } from './personaQueries';

const WITHOUT_PERSONA = '';

type PersonaEntry = { id: string; name: string; is_default: boolean };
type Props = { personas: PersonaEntry[]; value: string | null | undefined; onChange: (value: string | null) => void; hint?: string };

export function PersonaSelect({ personas, value, onChange, hint = '상대가 읽는 나의 설정입니다. 시작할 때의 설정을 복사해 둡니다.' }: Props) {
  return (
    <SelectField label="나(페르소나)" value={value ?? WITHOUT_PERSONA} onChange={(event) => onChange(event.target.value === WITHOUT_PERSONA ? null : event.target.value)} hint={hint}>
      {personas.map((entry) => (
        <option key={entry.id} value={entry.id}>
          {entry.is_default ? `${entry.name}(기본)` : entry.name}
        </option>
      ))}
      <option value={WITHOUT_PERSONA}>페르소나 없이</option>
    </SelectField>
  );
}

/** 내 페르소나. 로그인했을 때만 읽고, 읽지 못하면 빈 목록이다 */
export function usePersonaList(signedIn: boolean) {
  const query = useQuery({ ...personasQuery(), enabled: signedIn });
  return query.data ?? [];
}

/** 처음 골라 둘 페르소나. 기본, 없으면 처음 것, 페르소나가 없으면 undefined(보내지 않는다) */
export function defaultPersonaId(personas: PersonaEntry[]): string | undefined {
  return personas.find((entry) => entry.is_default)?.id ?? personas[0]?.id;
}
