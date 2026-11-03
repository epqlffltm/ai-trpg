// web/apps/web/src/pages/wallet/CouponForm.tsx
// 쿠폰 넣기(#979). 지갑(A6)의 잔액 아래에 있다. 코드를 넣으면 실버를 받고, 받은 양과 사라지는 때를 보인다.
// 받으면 잔액과 원장을 다시 읽는다(WALLET_KEY). 한 번에 하나만 보낸다. 다시 보내도 두 번 받지 않는다(서버가 409).
// 본인인증 전이면 본인인증으로 가는 길을 붙인다. 너무 자주 틀리면(429) 기다리라고 한다.

import { Button, Notice, TextField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { redeemCoupon } from '../../api/coupons';
import type { CouponRedemption } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { describeCouponProblem, type CouponProblem } from './couponProblem';
import { WALLET_KEY } from './walletQueries';

/** 코드의 가장 긴 글자 수. 서버와 같다(4~32자) */
const CODE_MAX_LENGTH = 32;

export function CouponForm() {
  const queryClient = useQueryClient();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [received, setReceived] = useState<CouponRedemption | null>(null);
  const [problem, setProblem] = useState<CouponProblem | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !code.trim()) return;
    setBusy(true);
    setProblem(null);
    setReceived(null);
    try {
      setReceived(await redeemCoupon(code));
      setCode('');
      void queryClient.invalidateQueries({ queryKey: WALLET_KEY });
    } catch (error) {
      setProblem(describeCouponProblem(error));
    }
    setBusy(false);
  }

  return (
    <section className="page-section" aria-labelledby="coupon-heading">
      <h2 id="coupon-heading">쿠폰</h2>
      <form onSubmit={submit} aria-label="쿠폰 넣기" noValidate>
        {received ? (
          <Notice>
            쿠폰 {received.code}: 실버 {received.silver}을 받았습니다. {formatDateTime(received.expires_at)}에 사라집니다.
          </Notice>
        ) : null}
        {problem ? (
          <Notice tone="error">
            {problem.message}
            {problem.verify ? (
              <>
                {' '}
                <Link to="/me/identity">본인인증하기</Link>
              </>
            ) : null}
          </Notice>
        ) : null}
        <TextField
          label="쿠폰 코드"
          name="coupon_code"
          autoComplete="off"
          maxLength={CODE_MAX_LENGTH}
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <Button type="submit" busy={busy} disabled={!code.trim()}>
          받기
        </Button>
      </form>
    </section>
  );
}
