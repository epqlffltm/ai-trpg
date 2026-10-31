// web/apps/web/src/pages/chat/studio/characters/CharacterNewPage.tsx
// 캐릭터 만들기(C6, /chat/studio/characters/new). 이름과 장르(반드시 하나)를 받고, 만들면 고치기로 간다(처음에는 비공개).
// 나머지 칸은 고치기의 탭에서 채운다. 지금은 운영자만 만든다(아니면 403 operator_only).

import { Button, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import type { AssetGenre } from '../../../../api/types';
import { Link, useNavigate } from 'react-router';
import { createCharacter } from '../../../../api/characters';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { NAME_MAX } from './basicsForm';
import { characterPath, CHARACTERS_PATH } from './characterPaths';
import { describeCharacterProblem } from './characterProblem';
import { GenreSelect } from './GenreSelect';
import { characterListKey } from './characterQueries';
import { useCharacterSending } from './useCharacterSending';

/** 고치기로 넘어갈 때 넘기는 state. 고치기 화면이 "만들었습니다."를 보인다 */
export const CREATED_STATE = { created: true } as const;

export function CharacterNewPage() {
  const [name, setName] = useState('');
  const [genre, setGenre] = useState<AssetGenre | ''>('');
  const [touched, setTouched] = useState(false);
  const sending = useCharacterSending(describeCharacterProblem);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const trimmed = name.trim();
  const hint = trimmed === '' ? '이름을 적어 주세요.' : trimmed.length > NAME_MAX ? `이름은 ${NAME_MAX}자까지입니다.` : undefined;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTouched(true);
    if (hint || genre === '') return;
    const created = await sending.send(() => createCharacter({ name: trimmed, genre }));
    if (!created) return;
    void queryClient.invalidateQueries({ queryKey: characterListKey() });
    navigate(characterPath(created.id), { state: CREATED_STATE });
  }

  return (
    <main className="page page--narrow">
      <p>
        <Link to={CHARACTERS_PATH}>내 캐릭터</Link>
      </p>
      <h1>캐릭터 만들기</h1>
      <form onSubmit={(event) => void submit(event)} noValidate aria-label="캐릭터 만들기">
        <ProblemNotice problem={sending.problem} />
        <TextField
          label="이름"
          name="name"
          maxLength={NAME_MAX}
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={touched ? hint : undefined}
        />
        <GenreSelect value={genre} error={touched && genre === '' ? '장르를 골라 주세요.' : undefined} onChange={setGenre} where="대화" />
        <p className="hint">처음에는 비공개입니다. 나머지 칸은 만든 뒤에 채웁니다.</p>
        <div className="form-actions">
          <Button type="submit" busy={sending.busy}>
            만들기
          </Button>
        </div>
      </form>
    </main>
  );
}
