// web/apps/web/src/pages/chat/studio/characters/SpeechTab.tsx
// 캐릭터의 말 탭(C6): 인사말(대화를 열면 캐릭터가 먼저 하는 말), 말투 예시(모델이 읽는다).

import { useState } from 'react';
import type { AssetCharacterDetail } from '../../../../api/types';
import { TextAreaField } from '../../../../components/TextAreaField';
import { CharacterForm } from './CharacterForm';
import { GREETING_MAX, SPEECH_MAX, speechDraft, speechHints, toSpeechBody, type SpeechDraft } from './textsForm';
import { useCharacterSave } from './useCharacterSave';

export function SpeechTab({ character }: { character: AssetCharacterDetail }) {
  const [draft, setDraft] = useState<SpeechDraft>(() => speechDraft(character));
  const saving = useCharacterSave(character.id);
  const hints = speechHints(draft);

  async function submit() {
    const saved = await saving.save(toSpeechBody(draft));
    if (saved) setDraft(speechDraft(saved));
  }

  return (
    <CharacterForm
      label="말"
      busy={saving.busy}
      problem={saving.problem}
      saved={saving.saved}
      blocked={Object.keys(hints).length > 0}
      onSubmit={() => void submit()}
    >
      <TextAreaField
        label="인사말"
        name="greeting"
        rows={4}
        maxLength={GREETING_MAX}
        value={draft.greeting}
        onChange={(event) => setDraft((current) => ({ ...current, greeting: event.target.value }))}
        error={hints.greeting}
        hint={`${draft.greeting.length} / ${GREETING_MAX}자. 대화를 열면 캐릭터가 먼저 하는 말입니다.`}
      />
      <TextAreaField
        label="말투 예시"
        name="speech_examples"
        rows={8}
        maxLength={SPEECH_MAX}
        value={draft.speechExamples}
        onChange={(event) => setDraft((current) => ({ ...current, speechExamples: event.target.value }))}
        error={hints.speech_examples}
        hint={`${draft.speechExamples.length} / ${SPEECH_MAX}자. 모델이 캐릭터의 말투를 따라 하도록 읽는 예시입니다.`}
      />
    </CharacterForm>
  );
}
