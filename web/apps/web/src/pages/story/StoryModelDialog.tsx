// web/apps/web/src/pages/story/StoryModelDialog.tsx
// 세션의 모델 고르기(D2 의 창). 고를 수 있는 모델(GET /story/models)을 회사별로, 말 한 번의 값과 함께 보인다.
// 성인 등급의 세계관이면 성인 등급에 쓸 수 있는 모델(allows_adult)만 보인다. 고르면 다음 말부터 그 모델이다(청구 없음).
// 글의 모양은 chat 의 모델 고르기와 같다(modelView.ts).

import { Button, Dialog, Notice, Radio } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { chooseStoryModel, type StorySession } from '../../api/story';
import { groupModels, modelLine, modelsFor } from '../chat/conversation/modelView';
import { describeChangeProblem } from '../chat/conversation/turnProblem';
import { STORY_SESSIONS_KEY, storyModelsQuery, storySessionKey } from './storyQueries';

type Props = { session: StorySession; open: boolean; onClose: () => void };

export function StoryModelDialog({ session, open, onClose }: Props) {
  return (
    <Dialog title="모델 고르기" open={open} onClose={onClose}>
      {open ? <ModelChoices session={session} onDone={onClose} /> : null}
    </Dialog>
  );
}

function ModelChoices({ session, onDone }: { session: StorySession; onDone: () => void }) {
  const models = useQuery(storyModelsQuery());
  const [chosen, setChosen] = useState(session.model?.slug ?? '');
  const choosing = useModelChoice(session.id, onDone);
  const items = modelsFor(models.data?.items ?? [], session.world.rating);

  if (models.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (models.isError) return <Notice tone="error">모델 목록을 불러오지 못했습니다. 잠시 뒤에 다시 열어 주세요.</Notice>;
  if (items.length === 0) return <p className="empty-state">지금 이 세션에 고를 수 있는 모델이 없습니다.</p>;
  return (
    <form
      className="chat-models"
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen) choosing.mutate(chosen);
      }}
    >
      {models.data.free ? <p className="hint">결제 서버 없이 도는 서버라 값을 받지 않습니다.</p> : null}
      {groupModels(items).map((group) => (
        <fieldset key={group.vendor} className="chat-models__group">
          <legend>{group.vendor}</legend>
          {group.models.map((model) => (
            <Radio key={model.slug} name="story-model" label={model.display_name} description={modelLine(model)} checked={chosen === model.slug} onChange={() => setChosen(model.slug)} />
          ))}
        </fieldset>
      ))}
      {choosing.error ? <Notice tone="error">{describeChangeProblem(choosing.error)}</Notice> : null}
      <Button type="submit" busy={choosing.isPending} disabled={!chosen || chosen === session.model?.slug}>
        이 모델로 하기
      </Button>
    </form>
  );
}

/** 고른 모델을 세션에 적는다. 세션의 모델 칸만 바꿔 다시 읽지 않는다 */
function useModelChoice(sessionId: string, onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (model: string) => chooseStoryModel(sessionId, model),
    onSuccess: (model) => {
      queryClient.setQueryData(storySessionKey(sessionId), (session: StorySession | undefined) => (session ? { ...session, model } : session));
      void queryClient.invalidateQueries({ queryKey: STORY_SESSIONS_KEY });
      onDone();
    },
  });
}
