// web/apps/web/src/pages/story/studio/DeleteWorldButton.tsx
// 세계관을 지우는 단추. 한 번 더 묻는다. 지우면 목록으로 간다. 이미 시작한 세션은 그때의 판으로 이어진다.

import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { deleteStoryWorld } from '../../../api/storyWorlds';
import { ConfirmButton } from '../../../components/ConfirmButton';
import { useCharacterSending } from '../../chat/studio/characters/useCharacterSending';
import { describeWorldProblem } from './worldProblem';
import { WORLDS_PATH } from './worldPaths';
import { MY_WORLDS_KEY, WORLDS_KEY, worldKey } from './worldQueries';

export function DeleteWorldButton({ worldId, name }: { worldId: string; name: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sending = useCharacterSending(describeWorldProblem);

  async function remove(): Promise<boolean> {
    const done = await sending.send(() => deleteStoryWorld(worldId));
    if (done === null) return false;
    queryClient.removeQueries({ queryKey: worldKey(worldId) });
    void queryClient.invalidateQueries({ queryKey: WORLDS_KEY });
    void queryClient.invalidateQueries({ queryKey: MY_WORLDS_KEY });
    navigate(WORLDS_PATH, { replace: true });
    return true;
  }

  return (
    <ConfirmButton label="지우기" title="세계관 지우기" confirm="지우기" busy={sending.busy} problem={sending.problem} onConfirm={remove}>
      <p>{name}을(를) 지웁니다. 낸 판도 함께 지워지고 되돌릴 수 없습니다. 이미 시작한 세션은 그때의 판으로 이어집니다.</p>
    </ConfirmButton>
  );
}
