// web/apps/web/src/pages/chat/studio/characters/IntroTab.tsx
// 캐릭터의 소개 탭(C6). 남에게 보이는 소개이고 HTML 과 인라인 CSS 로 꾸민다(UTF-8 로 50KB 까지).
// 게시할 때 서버가 허용하지 않는 태그, 속성, 스타일, 링크, 그림을 걸러 낸다. 무엇이 걸러질지는 게시 점검이 보인다.

import { useState } from 'react';
import type { AssetCharacterDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import { INTRO_MAX_BYTES, introHint, toIntroBody, utf8Bytes } from './textsForm';
import { useCharacterSave } from './useCharacterSave';

export function IntroTab({ character }: { character: AssetCharacterDetail }) {
  const [intro, setIntro] = useState(character.intro_html);
  const saving = useCharacterSave(character.id);
  const hint = introHint(intro);

  async function submit() {
    const saved = await saving.save(toIntroBody(intro));
    if (saved) setIntro(saved.intro_html);
  }

  return (
    <CharacterForm
      label="소개"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={hint !== undefined}
      onSubmit={() => void submit()}
    >
      <TextAreaField
        label="소개(HTML)"
        name="intro_html"
        rows={14}
        value={intro}
        onChange={(event) => setIntro(event.target.value)}
        error={hint}
        hint={`${Math.ceil(utf8Bytes(intro) / 1024)} / ${INTRO_MAX_BYTES / 1024}KB. 게시할 때 허용하지 않는 것은 걸러지고, 걸러질 것은 게시 점검에 보입니다.`}
      />
    </CharacterForm>
  );
}
