// web/apps/web/src/pages/trpg/lobby/InviteJoinForm.tsx
// 초대 코드로 들어가기(POST /tables/join). 로비에 없는 테이블(비공개)에도 들어간다. 들어가면 테이블 방(B6)으로 간다.
// 코드가 틀리면 404 다(그런 테이블이 있는지 알려 주지 않는다). 이미 앉아 있으면 그 테이블을 모르므로 내 테이블에서 고르게 한다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { joinByInvite } from '../../../api/tables';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { describeJoinProblem, type TableProblem } from '../tables/tableProblem';
import { useEnterTable } from '../tables/useEnterTable';

export function InviteJoinForm() {
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<TableProblem | undefined>();
  const enterTable = useEnterTable();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setProblem(undefined);
    try {
      const table = await joinByInvite(code.trim());
      enterTable(table.id);
    } catch (error) {
      const next = describeJoinProblem(error);
      setProblem(next.seated ? { message: '이미 앉아 있는 테이블입니다. 내 테이블에서 골라 주세요.' } : next);
      setBusy(false);
    }
  }

  return (
    <form className="invite-join" onSubmit={submit} noValidate>
      <ProblemNotice problem={problem} />
      <div className="invite-join__row">
        <TextField
          label="초대 코드로 들어가기"
          name="invite_code"
          autoComplete="off"
          maxLength={64}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <Button type="submit" variant="secondary" busy={busy} disabled={!code.trim()}>
          들어가기
        </Button>
      </div>
    </form>
  );
}
