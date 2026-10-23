// web/apps/web/src/pages/trpg/room/events/useEventContext.ts
// 일어난 일을 글로 바꿀 때 쓰는 것을 모은다. 사람의 이름은 받은 함수로, 모델의 이름은 서술 모델 목록(B8)으로.
// 목록을 아직 못 읽었거나 목록에 없는 모델(은퇴, 꺼짐)이면 이름표 그대로 보인다.

import { useQuery } from '@tanstack/react-query';
import type { TableDetail } from '../../../../api/types';
import { narrationModelsQuery } from '../../queries';
import type { EventContext } from './eventLines';

export function useEventContext(table: TableDetail, nameOfMember: (userId: string) => string): EventContext {
  const models = useQuery(narrationModelsQuery());
  const list = models.data?.models ?? [];
  return {
    table,
    nameOfMember,
    modelName: (slug) => list.find((model) => model.slug === slug)?.display_name ?? slug,
  };
}
