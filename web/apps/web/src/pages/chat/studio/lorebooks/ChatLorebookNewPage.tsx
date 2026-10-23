// web/apps/web/src/pages/chat/studio/lorebooks/ChatLorebookNewPage.tsx
// 로어북 만들기(chat, /chat/studio/lorebooks/new). 이름만 받고, 만들면 고치기로 가서 항목을 더한다.
// 지금은 운영자만 만든다(아니면 403 operator_only).

import { Button, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { createLorebook } from '../../../../api/assetLorebooks';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { CREATED_STATE } from '../characters/CharacterNewPage';
import { useCharacterSending } from '../characters/useCharacterSending';
import { LOREBOOK_NAME_MAX, nameHint } from './lorebookForm';
import { lorebookPath, LOREBOOKS_PATH } from './lorebookPaths';
import { describeLorebookProblem } from './lorebookProblem';
import { lorebookListKey, lorebookPickerKey } from './lorebookQueries';

export function ChatLorebookNewPage() {
  const [name, setName] = useState('');
  const [touched, setTouched] = useState(false);
  const sending = useCharacterSending(describeLorebookProblem);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const hint = nameHint(name);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (hint) return;
    const created = await sending.send(() => createLorebook({ name: name.trim() }));
    if (!created) return;
    void queryClient.invalidateQueries({ queryKey: lorebookListKey() });
    void queryClient.invalidateQueries({ queryKey: lorebookPickerKey() });
    navigate(lorebookPath(created.id), { state: CREATED_STATE });
  }

  return (
    <main className="page page--narrow">
      <p>
        <Link to={LOREBOOKS_PATH}>내 로어북</Link>
      </p>
      <h1>로어북 만들기</h1>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="로어북 만들기">
        <ProblemNotice problem={sending.problem} />
        <TextField
          label="이름"
          name="name"
          maxLength={LOREBOOK_NAME_MAX}
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={touched ? hint : undefined}
        />
        <p className="hint">항목은 만든 뒤에 더합니다.</p>
        <div className="form-actions">
          <Button type="submit" busy={sending.busy}>
            만들기
          </Button>
        </div>
      </form>
    </main>
  );
}
