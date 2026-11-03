// web/apps/web/src/pages/me/MyInviteSection.tsx
// 마이페이지의 "친구 초대"(#990). 내 초대 코드와 가입 주소를 복사하고, 받은 보상의 수를 본다.
// 초대받은 친구가 휴대폰 본인인증을 마치면 두 사람 모두 실버를 받는다. 양과 횟수의 상한은 서버가 정한다.
// 보상은 내가 본인인증을 마친 뒤의 초대부터 받는다. 읽지 못하면 다시 시도를 보인다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchMyInvite } from '../../api/invites';
import { inviteLink, rewardLine } from './inviteView';

export function MyInviteSection() {
  const invite = useQuery({ queryKey: ['auth', 'me', 'invite'], queryFn: ({ signal }) => fetchMyInvite(signal) });
  return (
    <section className="page-section" aria-labelledby="my-invite-heading">
      <h2 id="my-invite-heading">친구 초대</h2>
      <p className="hint">
        초대받은 친구가 가입하고 휴대폰 본인인증을 마치면 두 사람 모두 실버를 받습니다. 내가 본인인증을 마친 뒤의 초대부터 받습니다.
      </p>
      {invite.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {invite.isError ? (
        <Notice tone="error">
          초대 코드를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void invite.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {invite.data ? (
        <>
          <p className="invite-code">
            초대 코드 <code>{invite.data.code}</code>
            <CopyButton text={invite.data.code} label="코드 복사" />
            <CopyButton text={inviteLink(window.location.origin, invite.data.code)} label="가입 주소 복사" />
          </p>
          <p>{rewardLine(invite.data.rewarded, invite.data.limit)}</p>
        </>
      ) : null}
    </section>
  );
}

/** 눌러 복사한다. 복사가 막힌 브라우저면 글이 바뀌지 않는다(코드를 직접 고른다) */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Button variant="quiet" onClick={() => void copy()}>
      {copied ? '복사했습니다' : label}
    </Button>
  );
}
