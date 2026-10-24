// web/apps/web/src/pages/identity/FakeIdentityForm.tsx
// 시험용 본인확인 창(VITE_IDENTITY_PROVIDER=fake). 인증 서버의 가짜 업체에 맞춘다. 실제 휴대폰 인증이 아니다.
// 생일과 사람 식별값을 골라 가짜 업체의 글자(fake:<식별값>:<생일>)를 지어 넘긴다. 식별값의 처음 값과 빠른 고르기는 쓰는 곳이 정한다
// (회원의 본인인증 A3 은 계정마다의 값과 성인, 미성년, 만 14세 미만. 보호자의 동의 A4 는 보호자의 값과 성인, 성년 전).
// 실제 업체도 마지막에 글자 하나를 넘긴다(받는 쪽은 같다).

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { birthDateForAge, diHint, fakeIdentityToken } from './identityProvider';

export type AgePreset = { age: number; label: string };

/** 회원의 본인인증(A3) */
export const MEMBER_PRESETS: readonly AgePreset[] = [
  { age: 30, label: '성인(만 30세)' },
  { age: 17, label: '미성년(만 17세)' },
  { age: 13, label: '만 13세(막힘)' },
];

type Props = {
  initialDi: string;
  presets: readonly AgePreset[];
  /** 창의 한 줄 설명 */
  note: string;
  submitLabel: string;
  today: string;
  busy: boolean;
  onToken: (token: string) => void;
};

export function FakeIdentityForm({ initialDi, presets, note, submitLabel, today, busy, onToken }: Props) {
  const [birthDate, setBirthDate] = useState(() => birthDateForAge(today, presets[0]?.age ?? 30));
  const [di, setDi] = useState(initialDi);
  const hint = diHint(di);
  const blocked = hint !== null || birthDate === '';

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!blocked) onToken(fakeIdentityToken(di, birthDate));
  }

  return (
    <form className="checkout" onSubmit={submit} noValidate aria-label="시험용 본인확인">
      <h3>시험용 본인확인</h3>
      <p className="hint">{note}</p>
      <div className="checkout__outcomes">
        {presets.map((preset) => (
          <Button key={preset.age} variant="secondary" disabled={busy} onClick={() => setBirthDate(birthDateForAge(today, preset.age))}>
            {preset.label}
          </Button>
        ))}
      </div>
      <TextField label="생일" type="date" value={birthDate} max={today} onChange={(event) => setBirthDate(event.target.value)} />
      <TextField label="사람 식별값" value={di} onChange={(event) => setDi(event.target.value)} error={hint ?? undefined} />
      <div className="form-actions">
        <Button type="submit" busy={busy} disabled={blocked}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
