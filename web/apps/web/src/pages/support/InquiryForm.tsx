// web/apps/web/src/pages/support/InquiryForm.tsx
// 문의 보내기. 종류, 제목, 내용, 로그인하지 않았으면 답 받을 주소. 보내면 칸을 비우고 받았다고 알린다.
// 너무 자주 보내면(429) 기다릴 시간만큼 단추를 막는다. 로그인했으면 내 문의를 다시 읽는다.

import { Button, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { sendInquiry } from '../../api/inquiries';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { TextAreaField } from '../../components/TextAreaField';
import { useCountdown } from '../../hooks/useCountdown';
import { BODY_MAX, CATEGORIES, EMPTY_FORM, TITLE_MAX, canSend, describeSendProblem, toDraft, type InquiryForm as Form } from './inquiryView';
import { MY_INQUIRIES_KEY } from './supportQueries';

export function InquiryForm({ signedIn }: { signedIn: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();

  function update(key: keyof Form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setSent(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await sendInquiry(toDraft(form, signedIn));
      setForm(EMPTY_FORM);
      setSent(true);
      if (signedIn) await queryClient.invalidateQueries({ queryKey: MY_INQUIRIES_KEY });
    } catch (error) {
      const next = describeSendProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
    }
    setBusy(false);
  }

  return (
    <form onSubmit={submit} noValidate aria-label="문의 보내기">
      {sent ? <Notice>문의를 받았습니다. {signedIn ? '답은 메일과 아래의 내 문의에서 볼 수 있습니다.' : '답은 적은 주소로 메일을 보냅니다.'}</Notice> : null}
      <ProblemNotice problem={problem} reveal />
      <SelectField label="종류" value={form.category} onChange={(event) => update('category', event.target.value)} error={problem?.fields?.category} required>
        <option value="" disabled>
          종류를 고르세요
        </option>
        {CATEGORIES.map((category) => (
          <option key={category.value} value={category.value}>
            {category.label}
          </option>
        ))}
      </SelectField>
      <TextField
        label="제목"
        maxLength={TITLE_MAX}
        value={form.title}
        onChange={(event) => update('title', event.target.value)}
        error={problem?.fields?.title}
        required
      />
      <TextAreaField
        label="내용"
        rows={8}
        maxLength={BODY_MAX}
        value={form.body}
        onChange={(event) => update('body', event.target.value)}
        error={problem?.fields?.body}
        hint="결제 문의라면 주문 번호를, 오류라면 언제 어느 화면에서 일어났는지 적어 주세요. 비밀번호는 적지 마세요."
        required
      />
      {signedIn ? null : (
        <>
          <p className="hint">로그인하지 않았으면 답 받을 이메일을 적어 주세요. 로그인하면 계정의 이메일로 답합니다.</p>
          <TextField
            label="답 받을 이메일"
            type="email"
            autoComplete="email"
            maxLength={254}
            value={form.email}
            onChange={(event) => update('email', event.target.value)}
            error={problem?.fields?.email}
            required
          />
        </>
      )}
      <Button type="submit" busy={busy} disabled={!canSend(form, signedIn) || wait.remaining > 0}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '문의 보내기'}
      </Button>
    </form>
  );
}
