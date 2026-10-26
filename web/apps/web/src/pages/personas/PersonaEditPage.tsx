// web/apps/web/src/pages/personas/PersonaEditPage.tsx
// 페르소나 고치기(C4, /me/personas/:personaId). 저장하면 그 자리에 "저장했습니다."를 보인다.
// 고쳐도 이미 시작한 대화는 복사해 둔 설정 그대로다(새 설정으로 바꾸는 것은 대화 안에서 고른다. 서버에 그 길이 생기면 더한다).

import { Button, Notice } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router';
import { ApiError } from '../../api/errors';
import { updatePersona } from '../../api/personas';
import type { Persona } from '../../api/types';
import { PersonaForm } from './PersonaForm';
import { draftOf, personaBody, type PersonaDraft } from './personaForm';
import { describePersonaProblem } from './personaProblem';
import { personaQuery, personasKey } from './personaQueries';

export function PersonaEditPage() {
  const { personaId = '' } = useParams();
  const query = useQuery(personaQuery(personaId));
  return (
    <main className="page page--narrow">
      <p>
        <Link to="/me/personas">내 페르소나</Link>
      </p>
      <h1>페르소나 고치기</h1>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? <LoadProblem error={query.error} onRetry={() => void query.refetch()} /> : null}
      {query.data ? <EditForm key={query.data.id} persona={query.data} /> : null}
    </main>
  );
}

function EditForm({ persona }: { persona: Persona }) {
  const queryClient = useQueryClient();
  const saving = useMutation({
    mutationFn: (draft: PersonaDraft) => updatePersona(persona.id, personaBody(draft)),
    onSuccess: (saved) => {
      queryClient.setQueryData([...personasKey(), saved.id], saved);
      void queryClient.invalidateQueries({ queryKey: personasKey(), exact: true });
    },
  });
  return (
    <>
      {saving.isSuccess ? <Notice>저장했습니다.</Notice> : null}
      <PersonaForm
        initial={draftOf(persona)}
        submitLabel="저장하기"
        busy={saving.isPending}
        problem={saving.error ? describePersonaProblem(saving.error) : undefined}
        onSubmit={(draft) => saving.mutate(draft)}
      />
    </>
  );
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return <Notice>없거나 지운 페르소나입니다.</Notice>;
  return (
    <Notice tone="error">
      불러오지 못했습니다.{' '}
      <Button variant="quiet" onClick={onRetry}>
        다시 시도
      </Button>
    </Notice>
  );
}
