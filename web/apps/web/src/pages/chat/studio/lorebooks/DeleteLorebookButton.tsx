// web/apps/web/src/pages/chat/studio/lorebooks/DeleteLorebookButton.tsx
// 로어북을 지우는 단추. 한 번 더 묻는다. 지우면 목록으로 간다.
// 이미 게시한 캐릭터의 판에 복사된 것은 남는다. 이 로어북을 붙인 캐릭터는 다시 게시할 때 막힌다(로어북 탭에서 떼야 한다).

import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { deleteLorebook } from '../../../../api/assetLorebooks';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { useCharacterSending } from '../characters/useCharacterSending';
import { LOREBOOKS_PATH } from './lorebookPaths';
import { describeLorebookProblem } from './lorebookProblem';
import { LOREBOOKS_KEY, lorebookKey } from './lorebookQueries';

export function DeleteLorebookButton({ lorebookId, name }: { lorebookId: string; name: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sending = useCharacterSending(describeLorebookProblem);

  async function remove(): Promise<boolean> {
    const done = await sending.send(() => deleteLorebook(lorebookId));
    if (done === null) return false;
    queryClient.removeQueries({ queryKey: lorebookKey(lorebookId) });
    void queryClient.invalidateQueries({ queryKey: LOREBOOKS_KEY });
    navigate(LOREBOOKS_PATH, { replace: true });
    return true;
  }

  return (
    <ConfirmButton
      label="지우기"
      title="로어북 지우기"
      confirm="지우기"
      busy={sending.busy}
      problem={sending.problem}
      onConfirm={remove}
    >
      <p>
        {name}을(를) 지웁니다. 되돌릴 수 없습니다. 이미 게시한 캐릭터의 판에는 남지만, 이 로어북을 붙인 캐릭터는 로어북 탭에서 떼어야 다시
        게시할 수 있습니다.
      </p>
    </ConfirmButton>
  );
}
