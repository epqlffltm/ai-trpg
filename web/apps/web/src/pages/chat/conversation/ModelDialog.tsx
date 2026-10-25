// web/apps/web/src/pages/chat/conversation/ModelDialog.tsx
// 대화의 모델 고르기(C3 의 창). 고를 수 있는 모델(GET /chat/models)을 회사별로, 말 한 번의 값과 예약된 바뀜, 종료일과 함께 보인다.
// 성인 등급의 대화에는 성인 대화에 쓸 수 있는 모델(allows_adult)만 보인다. 고르면 다음 말부터 그 모델이다(청구 없음).

import { Button, Dialog, Notice, Radio } from '@ai-trpg/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { chooseConversationModel } from '../../../api/chatConversation';
import type { ConversationDetail } from '../../../api/types';
import { chatModelsQuery, conversationKey } from './conversationQueries';
import { groupModels, modelLine, modelsFor } from './modelView';
import { describeChangeProblem } from './turnProblem';

type Props = { detail: ConversationDetail; open: boolean; onClose: () => void };

export function ModelDialog({ detail, open, onClose }: Props) {
  return (
    <Dialog title="모델 고르기" open={open} onClose={onClose}>
      {open ? <ModelChoices detail={detail} onDone={onClose} /> : null}
    </Dialog>
  );
}

function ModelChoices({ detail, onDone }: { detail: ConversationDetail; onDone: () => void }) {
  const models = useQuery(chatModelsQuery());
  const [chosen, setChosen] = useState(detail.model?.slug ?? '');
  const choosing = useModelChoice(detail.id, onDone);
  const items = modelsFor(models.data?.items ?? [], detail.character.rating);

  if (models.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (models.isError) return <Notice tone="error">모델 목록을 불러오지 못했습니다. 잠시 뒤에 다시 열어 주세요.</Notice>;
  if (items.length === 0) return <p className="empty-state">지금 이 대화에 고를 수 있는 모델이 없습니다.</p>;
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
            <Radio key={model.slug} name="chat-model" label={model.display_name} description={modelLine(model)} checked={chosen === model.slug} onChange={() => setChosen(model.slug)} />
          ))}
        </fieldset>
      ))}
      {choosing.error ? <Notice tone="error">{describeChangeProblem(choosing.error)}</Notice> : null}
      <Button type="submit" busy={choosing.isPending} disabled={!chosen || chosen === detail.model?.slug}>
        이 모델로 하기
      </Button>
    </form>
  );
}

/** 고른 모델을 대화에 적는다. 대화의 모델 칸만 바꿔 다시 읽지 않는다 */
function useModelChoice(conversationId: string, onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (model: string) => chooseConversationModel(conversationId, model),
    onSuccess: (model) => {
      queryClient.setQueryData(conversationKey(conversationId), (detail: ConversationDetail | undefined) => (detail ? { ...detail, model } : detail));
      void queryClient.invalidateQueries({ queryKey: ['chat', 'conversations'] });
      onDone();
    },
  });
}
