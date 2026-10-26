// web/apps/web/src/pages/personas/PersonasPage.tsx
// 내 페르소나(C4, /me/personas). 마이페이지에서 온다. 기본이 먼저, 그다음 만든 차례. 고치기, 기본으로 두기, 지우기.
// 지워도 그 페르소나로 시작한 대화는 복사해 둔 설정으로 돈다. 기본을 지우면 가장 먼저 만든 것이 기본이 된다(서버).

import { Button, Notice } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { deletePersona, makeDefaultPersona } from '../../api/personas';
import type { Persona } from '../../api/types';
import { ConfirmButton } from '../../components/ConfirmButton';
import { useImageUrl } from '../../hooks/useImageUrl';
import { describePersonaProblem } from './personaProblem';
import { personasKey, personasQuery } from './personaQueries';

export function PersonasPage() {
  const query = useQuery(personasQuery());
  const personas = query.data ?? [];
  return (
    <main className="page page--medium">
      <p>
        <Link to="/me">내 정보</Link>
      </p>
      <h1>내 페르소나</h1>
      <p className="hint">대화에서 "나"의 설정입니다. TRPG, chat, story 가 함께 씁니다. 대화를 시작할 때 고릅니다.</p>
      <p>
        <Link to="/me/personas/new">페르소나 만들기</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && personas.length === 0 ? (
        <div className="empty-state">
          <p>아직 페르소나가 없습니다.</p>
          <Link to="/me/personas/new">첫 페르소나 만들기</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label="내 페르소나">
        {personas.map((persona) => (
          <PersonaItem key={persona.id} persona={persona} />
        ))}
      </ul>
    </main>
  );
}

function PersonaItem({ persona }: { persona: Persona }) {
  const image = useImageUrl(persona.image_id);
  const changing = usePersonaChange();
  const line = [persona.form_of_address ? `호칭 "${persona.form_of_address}"` : null, persona.age, persona.gender].filter(Boolean).join(' · ');
  return (
    <li className="studio-list__item persona-item">
      {image.url ? <img className="persona-item__image" src={image.url} alt="" /> : null}
      <div>
        <Link to={`/me/personas/${persona.id}`}>{persona.name}</Link> {persona.is_default ? <span className="badge">기본</span> : null}
        {line ? <p className="hint">{line}</p> : null}
        <div className="persona-item__actions">
          {persona.is_default ? null : (
            <Button variant="quiet" disabled={changing.isPending} onClick={() => changing.mutate({ kind: 'default', id: persona.id })}>
              기본으로 두기
            </Button>
          )}
          <ConfirmButton
            label="지우기"
            ariaLabel={`${persona.name} 지우기`}
            title="페르소나 지우기"
            confirm="지우기"
            busy={changing.isPending}
            problem={changing.error ? describePersonaProblem(changing.error) : undefined}
            onConfirm={() => changing.mutateAsync({ kind: 'delete', id: persona.id }).then(() => true, () => false)}
          >
            <p>"{persona.name}"을(를) 지웁니다. 이 페르소나로 시작한 대화는 복사해 둔 설정으로 그대로 이어집니다.</p>
          </ConfirmButton>
        </div>
        {changing.error && changing.variables?.kind === 'default' ? <p className="ui-field__error">{describePersonaProblem(changing.error).message}</p> : null}
      </div>
    </li>
  );
}

/** 기본으로 두기와 지우기. 끝나면 목록을 다시 읽는다(기본이 옮겨 갈 수 있다) */
function usePersonaChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, id }: { kind: 'default' | 'delete'; id: string }) => (kind === 'default' ? makeDefaultPersona(id).then(() => undefined) : deletePersona(id)),
    onSettled: () => queryClient.invalidateQueries({ queryKey: personasKey() }),
  });
}
