// web/apps/web/src/pages/chat/studio/characters/useCharacterSave.ts
// 캐릭터의 탭 하나를 저장한다(C6). 그 탭의 칸만 PATCH 로 보내고, 받은 캐릭터를 낱개의 읽기에 넣는다.
// 저장하면 게시 점검과 목록(이름, 고친 날)을 다시 읽는다. 무엇을 고쳤든 게시할 수 있는지가 바뀔 수 있다.

import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { updateCharacter } from '../../../../api/characters';
import type { AssetCharacterDetail, AssetCharacterUpdate } from '../../../../api/types';
import { describeCharacterProblem } from './characterProblem';
import { characterKey, characterListKey, checkKey } from './characterQueries';
import { useCharacterSending } from './useCharacterSending';

export function useCharacterSave(characterId: string) {
  const queryClient = useQueryClient();
  const sending = useCharacterSending(describeCharacterProblem);
  const [saved, setSaved] = useState(false);

  /** 저장한 캐릭터, 못 했으면 null */
  async function save(body: AssetCharacterUpdate): Promise<AssetCharacterDetail | null> {
    setSaved(false);
    const result = await sending.send(() => updateCharacter(characterId, body));
    if (!result) return null;
    setSaved(true);
    queryClient.setQueryData(characterKey(characterId), result);
    void queryClient.invalidateQueries({ queryKey: checkKey(characterId) });
    void queryClient.invalidateQueries({ queryKey: characterListKey() });
    return result;
  }

  return { busy: sending.busy, problem: sending.problem, saved, save };
}
