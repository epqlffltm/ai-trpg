// web/apps/web/src/pages/story/studio/WorldShortcutsTab.tsx
// 세계관의 단축어 탭(D7, #981). 이야기에서 "/이름"으로 부르면 본문이 그 턴의 내 말 끝에 붙어 모델에 간다.
// 이 세계관의 세션에서만 쓴다. 게시할 때 판에 굳는다. 본문은 서술의 요청일 뿐 엔진의 판정(상태)을 바꾸지 못한다.
// 칸과 규칙은 캐릭터의 단축어 탭, 내 단축어와 같다(components/shortcuts).

import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { ShortcutsFields } from '../../../components/shortcuts/ShortcutsFields';
import { shortcutDrafts, shortcutsHints, toShortcuts, type ShortcutDraft } from '../../../components/shortcuts/shortcutsForm';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { useWorldSave } from './useWorldSave';

export function WorldShortcutsTab({ world }: { world: StoryWorldDetail }) {
  const [shortcuts, setShortcuts] = useState<ShortcutDraft[]>(() => shortcutDrafts(world.shortcuts));
  const saving = useWorldSave(world.id);
  const hints = shortcutsHints(shortcuts);

  async function submit() {
    const saved = await saving.save({ shortcuts: toShortcuts(shortcuts) });
    if (saved) setShortcuts(shortcutDrafts(saved.shortcuts));
  }

  return (
    <StudioForm
      label="단축어"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <p className="hint">
        이야기에서 /이름 으로 부르면 본문이 그 턴의 말 끝에 붙어 모델에 갑니다(예: /회상). 서술의 요청일 뿐 시각, 장소, 호감도 같은 상태는 바꾸지
        못합니다. 게시해야 세션에 들어가고, 같은 이름의 내 단축어보다 먼저입니다.
      </p>
      <ShortcutsFields shortcuts={shortcuts} hints={hints} onChange={setShortcuts} />
    </StudioForm>
  );
}
