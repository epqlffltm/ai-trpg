// web/apps/web/src/pages/story/studio/WorldIntroTab.tsx
// 세계관의 소개 탭(D7). 소개(D1)에 보이는 글이고 HTML 과 인라인 CSS 로 꾸민다(UTF-8 로 50KB 까지).
// 게시할 때 서버가 허용하지 않는 태그, 속성, 스타일, 링크, 그림을 걸러 낸다. 무엇이 걸러질지는 게시 점검이 보인다.

import { useState } from 'react';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { TextAreaField } from '../../../components/TextAreaField';
import { CharacterForm as StudioForm } from '../../chat/studio/characters/CharacterForm';
import { INTRO_MAX_BYTES, introHint, utf8Bytes } from '../../chat/studio/characters/textsForm';
import { useWorldSave } from './useWorldSave';

export function WorldIntroTab({ world }: { world: StoryWorldDetail }) {
  const [intro, setIntro] = useState(world.intro_html);
  const saving = useWorldSave(world.id);
  const hint = introHint(intro);

  async function submit() {
    const saved = await saving.save({ intro_html: intro });
    if (saved) setIntro(saved.intro_html);
  }

  return (
    <StudioForm label="소개" busy={saving.busy} problem={saving.problem} saved={saving.saved} blocked={hint !== undefined} onSubmit={() => void submit()}>
      <TextAreaField
        label="소개(HTML)"
        name="intro_html"
        rows={14}
        value={intro}
        onChange={(event) => setIntro(event.target.value)}
        error={hint}
        hint={`${Math.ceil(utf8Bytes(intro) / 1024)} / ${INTRO_MAX_BYTES / 1024}KB. 게시할 때 허용하지 않는 것은 걸러지고, 걸러질 것은 게시 점검에 보입니다.`}
      />
    </StudioForm>
  );
}
