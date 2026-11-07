// web/apps/web/src/pages/me/NicknameChangeForm.tsx
// 마이페이지의 "닉네임 바꾸기". 비밀번호를 다시 받는다. 30일에 한 번이고, 버린 이름은 30일 동안 남이 쓰지 못한다(인증 서버).
// 30일 안이면 언제부터 바꿀 수 있는지만 보이고 칸을 열지 않는다(/me 의 nickname_change_available_at).
// 바꾸면 답을 내 정보에 넣고 갱신을 한 번 한다. 다른 서버는 access 토큰의 닉네임을 보므로, 새 토큰을 받아야 새 이름이 보인다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { changeNickname } from '../../api/account';
import { refreshSession } from '../../api/refresh';
import type { Me } from '../../api/types';
import { describeNicknameChangeProblem } from '../../auth/accountProblem';
import type { FormProblem } from '../../auth/problem';
import { meQuery } from '../../auth/queries';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { useCountdown } from '../../hooks/useCountdown';
import { putQueryData } from '../../queryClient';
import { NICKNAME_PATTERN } from '../signup/profileForm';

const EMPTY = { nickname: '', password: '' };
const RULES = '한글, 영문, 숫자, 밑줄로 2~20자입니다. 띄어 쓸 수 없습니다.';

export function NicknameChangeForm() {
  const me = useQuery(meQuery());
  const [changed, setChanged] = useState(false);
  if (!me.data) return null;
  return (
    <section className="page-section" aria-labelledby="nickname-heading">
      <h2 id="nickname-heading">닉네임 바꾸기</h2>
      <p className="hint">30일에 한 번 바꿀 수 있습니다. 버린 닉네임은 30일 동안 다른 사람이 쓰지 못합니다.</p>
      {changed ? <Notice>닉네임을 바꿨습니다. 새 닉네임은 {me.data.nickname}입니다.</Notice> : null}
      {me.data.nickname_change_available_at ? (
        <p>{formatDateTime(me.data.nickname_change_available_at)}부터 다시 바꿀 수 있습니다.</p>
      ) : (
        <NicknameForm key={me.data.public_id} me={me.data} onChanged={() => setChanged(true)} />
      )}
    </section>
  );
}

function NicknameForm({ me, onChanged }: { me: Me; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();
  const hint = nicknameHint(draft.nickname, me.nickname);
  const ready = Boolean(draft.nickname && draft.password) && !hint;

  function update(key: keyof typeof EMPTY, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const changed = await changeNickname(draft.nickname, draft.password);
      await putQueryData<Me>(queryClient, meQuery().queryKey, (current) => (current ? { ...current, ...changed } : current));
      await queryClient.invalidateQueries({ queryKey: ['auth', 'creators', me.public_id] });
      // 새 이름이 실린 토큰을 받는다. 실패해도 다음 갱신에 실린다
      await refreshSession().catch(() => undefined);
      onChanged();
      return;
    } catch (error) {
      const next = describeNicknameChangeProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      // 30일 안이면 언제부터인지 다시 읽어 보인다
      await queryClient.invalidateQueries({ queryKey: meQuery().queryKey });
    }
    setBusy(false);
  }

  return (
    <form onSubmit={submit} noValidate>
      <ProblemNotice problem={problem} reveal />
      <TextField
        label="새 닉네임"
        name="nickname"
        autoComplete="nickname"
        maxLength={20}
        value={draft.nickname}
        onChange={(event) => update('nickname', event.target.value)}
        error={problem?.fields?.nickname ?? hint}
        required
      />
      <TextField
        label="비밀번호 확인"
        name="password"
        type="password"
        autoComplete="current-password"
        maxLength={128}
        value={draft.password}
        onChange={(event) => update('password', event.target.value)}
        error={problem?.fields?.password}
        required
      />
      <Button type="submit" busy={busy} disabled={!ready || wait.remaining > 0}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '닉네임 바꾸기'}
      </Button>
    </form>
  );
}

/** 보내기 전에 미리 알려 줄 것. 최종 판단은 서버가 한다(예약어, 쓰이고 있는 이름) */
export function nicknameHint(nickname: string, current: string): string | undefined {
  if (!nickname) return undefined;
  if (!NICKNAME_PATTERN.test(nickname)) return RULES;
  if (nickname === current) return '지금의 닉네임과 같습니다.';
  return undefined;
}
