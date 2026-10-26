// web/apps/web/src/pages/personas/PersonaNewPage.tsx
// 페르소나 만들기(C4, /me/personas/new). 만들면 목록으로 돌아간다. 처음 만든 것이 기본이 된다(서버).

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router';
import { createPersona } from '../../api/personas';
import { PersonaForm } from './PersonaForm';
import { EMPTY_PERSONA, personaBody, type PersonaDraft } from './personaForm';
import { describePersonaProblem } from './personaProblem';
import { personasKey } from './personaQueries';

export function PersonaNewPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const creating = useMutation({
    mutationFn: (draft: PersonaDraft) => createPersona(personaBody(draft)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: personasKey() });
      void navigate('/me/personas');
    },
  });
  return (
    <main className="page page--narrow">
      <p>
        <Link to="/me/personas">내 페르소나</Link>
      </p>
      <h1>페르소나 만들기</h1>
      <PersonaForm
        initial={EMPTY_PERSONA}
        submitLabel="만들기"
        busy={creating.isPending}
        problem={creating.error ? describePersonaProblem(creating.error) : undefined}
        onSubmit={(draft) => creating.mutate(draft)}
      />
    </main>
  );
}
