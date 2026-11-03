// web/apps/web/src/pages/chat/studio/characters/ShortcutsTab.tsx
// 캐릭터의 단축어 탭(C6, #981). 대화에서 "/이름"으로 부르면 본문이 그 턴의 내 말 끝에 붙어 모델에 간다.
// 이 캐릭터와의 대화에서만 쓴다. 게시할 때 판에 굳는다(이미 시작한 대화는 그때의 판의 단축어를 쓴다).
// 칸과 규칙은 내 단축어와 같다(components/shortcuts).

import { useState } from 'react';
import type { AssetCharacterDetail } from '../../../../api/types';
import { ShortcutsFields } from '../../../../components/shortcuts/ShortcutsFields';
import { shortcutDrafts, shortcutsHints, toShortcuts, type ShortcutDraft } from '../../../../components/shortcuts/shortcutsForm';
import { CharacterForm } from './CharacterForm';
import { useCharacterSave } from './useCharacterSave';

export function ShortcutsTab({ character }: { character: AssetCharacterDetail }) {
  const [shortcuts, setShortcuts] = useState<ShortcutDraft[]>(() => shortcutDrafts(character.shortcuts));
  const saving = useCharacterSave(character.id);
  const hints = shortcutsHints(shortcuts);

  async function submit() {
    const saved = await saving.save({ shortcuts: toShortcuts(shortcuts) });
    if (saved) setShortcuts(shortcutDrafts(saved.shortcuts));
  }

  return (
    <CharacterForm
      label="단축어"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">
        대화에서 /이름 으로 부르면 본문이 그 턴의 말 끝에 붙어 모델에 갑니다(예: /일기). 이 캐릭터와의 대화에서만 쓰고, 게시해야 대화에 들어갑니다. 같은
        이름의 내 단축어보다 먼저입니다.
      </p>
      <ShortcutsFields shortcuts={shortcuts} hints={hints} onChange={setShortcuts} />
    </CharacterForm>
  );
}
