// web/apps/web/src/pages/chat/studio/characters/DeleteCharacterButton.tsx
// 캐릭터를 지우는 단추. 한 번 더 묻는다. 지우면 목록으로 간다. 이미 시작한 남의 대화는 사본으로 돈다.

import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import { deleteCharacter } from '../../../../api/characters';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { describeCharacterProblem } from './characterProblem';
import { CHARACTERS_KEY, characterKey } from './characterQueries';
import { CHARACTERS_PATH } from './characterPaths';
import { useCharacterSending } from './useCharacterSending';

export function DeleteCharacterButton({ characterId, name }: { characterId: string; name: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const sending = useCharacterSending(describeCharacterProblem);

  async function remove(): Promise<boolean> {
    const done = await sending.send(() => deleteCharacter(characterId));
    if (done === null) return false;
    queryClient.removeQueries({ queryKey: characterKey(characterId) });
    void queryClient.invalidateQueries({ queryKey: CHARACTERS_KEY });
    navigate(CHARACTERS_PATH, { replace: true });
    return true;
  }

  return (
    <ConfirmButton
      label="지우기"
      title="캐릭터 지우기"
      confirm="지우기"
      busy={sending.busy}
      problem={sending.problem}
      onConfirm={remove}
    >
      <p>{name}을(를) 지웁니다. 되돌릴 수 없습니다. 이미 시작한 대화는 그때의 판으로 이어집니다.</p>
    </ConfirmButton>
  );
}
