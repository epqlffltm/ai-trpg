// web/apps/web/src/pages/trpg/studio/rulebooks/useRulebookActions.ts
// 룰북을 만들고, 고치고, 지운다(B9). 한 번에 하나만 보낸다.
// 받은 룰북은 그 낱개의 읽기에 바로 넣고, 목록은 다시 읽는다(제목과 고친 때가 바뀐다).

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { createRulebook, deleteRulebook, updateRulebook } from '../../../../api/rulebooks';
import type { RulebookDetail } from '../../../../api/types';
import type { FormProblem } from '../../../../auth/problem';
import { toRulebookCreate, toRulebookUpdate, type RulebookDraft } from './rulebookForm';
import { describeDeleteProblem, describeSaveProblem } from './rulebookProblem';
import { RULEBOOKS_KEY, rulebookQuery } from './rulebookQueries';

type Sending = { busy: boolean; problem: FormProblem | undefined };

/** 보내기 하나의 상태. 보내는 동안 busy, 실패하면 problem. 성공하면 결과를, 실패하면 null 을 돌려준다 */
function useSending() {
  const [state, setState] = useState<Sending>({ busy: false, problem: undefined });

  async function send<T>(request: () => Promise<T>, describe: (error: unknown) => FormProblem): Promise<T | null> {
    if (state.busy) return null;
    setState({ busy: true, problem: undefined });
    try {
      const result = await request();
      setState({ busy: false, problem: undefined });
      return result;
    } catch (error) {
      setState({ busy: false, problem: describe(error) });
      return null;
    }
  }

  return { ...state, send };
}

/** 받은 룰북을 낱개의 읽기에 넣고 목록을 무른다 */
function useRemember() {
  const queryClient = useQueryClient();
  return (rulebook: RulebookDetail) => {
    queryClient.setQueryData(rulebookQuery(rulebook.id).queryKey, rulebook);
    void queryClient.invalidateQueries({ queryKey: [...RULEBOOKS_KEY, 'list'] });
  };
}

export function useCreateRulebook() {
  const sending = useSending();
  const remember = useRemember();
  async function create(draft: RulebookDraft): Promise<RulebookDetail | null> {
    const made = await sending.send(() => createRulebook(toRulebookCreate(draft)), describeSaveProblem);
    if (made) remember(made);
    return made;
  }
  return { busy: sending.busy, problem: sending.problem, create };
}

export function useUpdateRulebook(rulebookId: string) {
  const sending = useSending();
  const remember = useRemember();
  async function update(draft: RulebookDraft): Promise<RulebookDetail | null> {
    const saved = await sending.send(() => updateRulebook(rulebookId, toRulebookUpdate(draft)), describeSaveProblem);
    if (saved) remember(saved);
    return saved;
  }
  return { busy: sending.busy, problem: sending.problem, update };
}

export function useDeleteRulebook(rulebookId: string) {
  const queryClient = useQueryClient();
  const sending = useSending();
  /** 지웠으면 true. 낱개의 읽기를 버리고 목록을 무른다 */
  async function remove(): Promise<boolean> {
    const done = await sending.send(async () => {
      await deleteRulebook(rulebookId);
      return true;
    }, describeDeleteProblem);
    if (!done) return false;
    queryClient.removeQueries({ queryKey: rulebookQuery(rulebookId).queryKey });
    void queryClient.invalidateQueries({ queryKey: [...RULEBOOKS_KEY, 'list'] });
    return true;
  }
  return { busy: sending.busy, problem: sending.problem, remove };
}
