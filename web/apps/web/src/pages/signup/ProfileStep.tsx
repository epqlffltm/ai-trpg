// web/apps/web/src/pages/signup/ProfileStep.tsx
// 가입 3단계. 아이디, 닉네임, 비밀번호, 만 14세 이상, 동의를 받아 계정을 만든다. 가입 티켓은 30분 유효하다.
// 동의 항목과 판은 서버(GET /consents)에서 읽는다. 판이 바뀌었다고 하면 다시 읽고 체크를 비운다.
// 실패는 그 칸에 보인다. 티켓을 쓸 수 없으면 1단계로, 이미 가입한 이메일이면 로그인으로 보낸다.

import { Button, Checkbox, Notice, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { completeSignup, fetchConsentDocuments } from '../../api/signup';
import { describeSignupProblem, type SignupProblem } from '../../auth/signupProblem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatRemaining, useCountdown } from '../../hooks/useCountdown';
import { itemsWithoutDocument } from '../../legal/consentItems';
import { ConsentList } from './ConsentList';
import { canSubmit, EMPTY_DRAFT, profileHints, toSignupProfile, type ProfileDraft } from './profileForm';

type Props = {
  ticket: string;
  ticketEndsAt: number;
  onDone: (username: string) => void;
  onRestart: (problem: SignupProblem) => void;
  onAlreadyRegistered: (problem: SignupProblem) => void;
};

export function ProfileStep({ ticket, ticketEndsAt, onDone, onRestart, onAlreadyRegistered }: Props) {
  const consents = useQuery({ queryKey: ['auth', 'consents'], queryFn: ({ signal }) => fetchConsentDocuments(signal) });
  const [draft, setDraft] = useState<ProfileDraft>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<SignupProblem | undefined>();
  const ticketClock = useCountdown(ticketEndsAt);
  const documents = consents.data ?? [];
  const missingDocuments = itemsWithoutDocument(documents);
  const hints = profileHints(draft);

  function update<K extends keyof ProfileDraft>(key: K, value: ProfileDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function fail(error: unknown) {
    const next = describeSignupProblem(error, 'profile');
    if (next.restart) return onRestart(next);
    if (next.goToLogin) return onAlreadyRegistered(next);
    setProblem(next);
    if (next.consentsChanged) {
      setDraft((current) => ({ ...current, agreed: {} }));
      await consents.refetch();
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      await completeSignup(ticket, toSignupProfile(draft, documents));
      onDone(draft.username);
    } catch (error) {
      await fail(error);
      setBusy(false);
    }
  }

  if (ticketClock.remaining === 0) {
    return (
      <>
        <Notice tone="error">가입 시간이 지났습니다.</Notice>
        <Button onClick={() => onRestart({ message: '이메일부터 다시 인증해 주세요.' })}>처음부터 다시</Button>
      </>
    );
  }

  return (
    <form onSubmit={submit} noValidate>
      <p>{formatRemaining(ticketClock.remaining)} 안에 마쳐 주세요.</p>
      <ProblemNotice problem={problem} />
      <TextField
        label="아이디"
        name="username"
        autoComplete="username"
        value={draft.username}
        onChange={(event) => update('username', event.target.value)}
        error={problem?.fields?.username ?? hints.username}
        required
      />
      <TextField
        label="닉네임"
        name="nickname"
        autoComplete="nickname"
        value={draft.nickname}
        onChange={(event) => update('nickname', event.target.value)}
        error={problem?.fields?.nickname ?? hints.nickname}
        required
      />
      <TextField
        label="비밀번호"
        name="password"
        type="password"
        autoComplete="new-password"
        maxLength={128}
        value={draft.password}
        onChange={(event) => update('password', event.target.value)}
        error={problem?.fields?.password}
        required
      />
      <TextField
        label="비밀번호 확인"
        name="passwordAgain"
        type="password"
        autoComplete="new-password"
        maxLength={128}
        value={draft.passwordAgain}
        onChange={(event) => update('passwordAgain', event.target.value)}
        error={hints.passwordAgain}
        required
      />
      <Checkbox
        label="만 14세 이상입니다"
        description="실제 나이는 본인인증에서 다시 확인합니다."
        checked={draft.ageOver14}
        onChange={(event) => update('ageOver14', event.target.checked)}
      />
      {problem?.fields?.age_over_14 ? <p className="ui-field__error">{problem.fields.age_over_14}</p> : null}
      <ConsentSection
        consents={consents}
        documents={documents}
        missingDocuments={missingDocuments}
        agreed={draft.agreed}
        onChange={(item, value) => update('agreed', { ...draft.agreed, [item]: value })}
      />
      <Button
        type="submit"
        busy={busy}
        disabled={!canSubmit(draft, documents) || missingDocuments.length > 0 || consents.isPending}
      >
        가입하기
      </Button>
    </form>
  );
}

type ConsentSectionProps = {
  consents: { isPending: boolean; isError: boolean; refetch: () => unknown };
  documents: Parameters<typeof ConsentList>[0]['documents'];
  missingDocuments: string[];
  agreed: Record<string, boolean>;
  onChange: (item: string, value: boolean) => void;
};

function ConsentSection({ consents, documents, missingDocuments, agreed, onChange }: ConsentSectionProps) {
  if (consents.isPending) return <p>동의 항목을 불러오는 중</p>;
  if (consents.isError) {
    return (
      <Notice tone="error">
        동의 항목을 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void consents.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return (
    <>
      {missingDocuments.length > 0 ? (
        <Notice tone="error">새 판의 문서를 이 화면이 아직 갖고 있지 않습니다. 새로 고쳐 주세요.</Notice>
      ) : null}
      <ConsentList documents={documents} agreed={agreed} onChange={onChange} />
    </>
  );
}
