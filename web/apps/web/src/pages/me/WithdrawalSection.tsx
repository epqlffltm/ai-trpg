// web/apps/web/src/pages/me/WithdrawalSection.tsx
// 탈퇴 요청(A5, #603). 남은 크레딧이 사라진다는 것과 7일 유예를 먼저 알리고, 창에서 비밀번호를 받아 보낸다(POST /me/withdrawal).
// 요청하면 이 기기를 포함한 모든 세션이 끊긴다. 읽어 둔 것을 버리고 지울 시각을 적어 로그인으로 보낸다.
// 그 안에 다시 로그인하면 유예 화면(WithdrawalPendingPage)에서 취소한다.
// 잔액을 읽지 못해도 요청은 막지 않는다(사라진다는 문장은 그대로 보인다).

import { Button, Dialog, TextField } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { requestWithdrawal } from '../../api/account';
import { describeWithdrawalProblem } from '../../auth/accountProblem';
import type { FormProblem } from '../../auth/problem';
import { ProblemNotice } from '../../components/ProblemNotice';
import { formatDateTime } from '../../format/dateTime';
import { useCountdown } from '../../hooks/useCountdown';
import { walletQuery } from '../wallet/walletQueries';
import { balanceShort } from '../wallet/walletView';

/** 로그인 화면에 보일 안내. 지울 시각을 모르면(서버가 비워 보냈다) 시각 없이 쓴다 */
export function requestedNotice(scheduledAt: string | null): string {
  const when = scheduledAt ? `${formatDateTime(scheduledAt)}에` : '7일 뒤에';
  return `탈퇴를 요청했습니다. ${when} 계정을 지웁니다. 그 전에 다시 로그인하면 취소할 수 있습니다.`;
}

export function WithdrawalSection() {
  const [asking, setAsking] = useState(false);
  const wallet = useQuery(walletQuery());
  const close = useCallback(() => setAsking(false), []);

  return (
    <section className="page-section" aria-labelledby="withdrawal-heading">
      <h2 id="withdrawal-heading">탈퇴</h2>
      <p>
        탈퇴를 요청하면 모든 기기에서 로그아웃되고, 7일 뒤에 계정을 지웁니다. 그 안에 다시 로그인하면 취소할 수 있습니다.
      </p>
      <p>
        탈퇴를 마치면 남은 크레딧은 모두 사라지고 되돌릴 수 없습니다.
        {wallet.data ? ` 지금 남은 것: ${balanceShort(wallet.data)}.` : null}
      </p>
      <p>
        산 지 7일이 지나지 않았고 쓰지 않은 주문은 먼저 <Link to="/wallet/orders">주문 내역</Link>에서 청약철회하세요.
      </p>
      <Button variant="secondary" onClick={() => setAsking(true)}>
        탈퇴하기
      </Button>
      <Dialog title="탈퇴하기" open={asking} onClose={close}>
        <WithdrawalForm />
      </Dialog>
    </section>
  );
}

function WithdrawalForm() {
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const scheduledAt = await requestWithdrawal(password);
      queryClient.clear();
      navigate('/login', { replace: true, state: { notice: requestedNotice(scheduledAt) } });
    } catch (error) {
      const next = describeWithdrawalProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <p>정말 탈퇴하려면 비밀번호를 입력하세요. 남은 크레딧은 탈퇴를 마치면 사라집니다.</p>
      <ProblemNotice problem={problem} />
      <TextField
        label="비밀번호"
        name="password"
        type="password"
        autoComplete="current-password"
        maxLength={128}
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        error={problem?.fields?.password}
        required
      />
      <div className="actions">
        <Button type="submit" busy={busy} disabled={!password || wait.remaining > 0}>
          {wait.remaining > 0 ? `${wait.remaining}초 뒤에 다시` : '탈퇴 요청하기'}
        </Button>
      </div>
    </form>
  );
}
