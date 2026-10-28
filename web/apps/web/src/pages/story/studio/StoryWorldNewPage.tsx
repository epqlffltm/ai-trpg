// web/apps/web/src/pages/story/studio/StoryWorldNewPage.tsx
// 세계관 만들기(D7, /story/studio/worlds/new). 이름만 받고, 만들면 고치기로 간다(처음에는 비공개, 시간대는 아침·낮·저녁·밤).
// 나머지 칸은 고치기의 탭에서 채운다. 지금은 운영자만 만든다(아니면 403 operator_only).

import { Button, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { createStoryWorld } from '../../../api/storyWorlds';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { useCharacterSending } from '../../chat/studio/characters/useCharacterSending';
import { NAME_MAX, worldNameHint } from './worldBasicsForm';
import { WORLDS_PATH, worldPath } from './worldPaths';
import { describeWorldProblem } from './worldProblem';
import { MY_WORLDS_KEY, worldListKey } from './worldQueries';

/** 고치기로 넘어갈 때 넘기는 state. 고치기 화면이 "만들었습니다."를 보인다 */
export const CREATED_STATE = { created: true } as const;

export function StoryWorldNewPage() {
  const [name, setName] = useState('');
  const [touched, setTouched] = useState(false);
  const sending = useCharacterSending(describeWorldProblem);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const hint = worldNameHint(name);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (hint) return;
    const created = await sending.send(() => createStoryWorld({ name: name.trim() }));
    if (!created) return;
    void queryClient.invalidateQueries({ queryKey: worldListKey() });
    void queryClient.invalidateQueries({ queryKey: MY_WORLDS_KEY });
    navigate(worldPath(created.id), { state: CREATED_STATE });
  }

  return (
    <main className="page page--narrow">
      <p>
        <Link to={WORLDS_PATH}>내 세계관</Link>
      </p>
      <h1>세계관 만들기</h1>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="세계관 만들기">
        <ProblemNotice problem={sending.problem} />
        <TextField label="이름" name="name" maxLength={NAME_MAX} value={name} onChange={(event) => setName(event.target.value)} error={touched ? hint : undefined} />
        <p className="hint">처음에는 비공개이고 시간대는 아침, 낮, 저녁, 밤입니다. 나머지 칸은 만든 뒤에 채웁니다.</p>
        <div className="form-actions">
          <Button type="submit" busy={sending.busy}>
            만들기
          </Button>
        </div>
      </form>
    </main>
  );
}
