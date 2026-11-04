// web/apps/web/src/pages/wallet/AutoChargeHistory.tsx
// 지갑(A6)의 최근 자동 결제(#980). "보기"를 눌렀을 때만 받는다(지갑을 열 때마다 받지 않는다). 늦게 적힌 것부터 20개다.
// 한 줄은 골드와 값, 상태(처리 중, 결제됨, 거절됨, 하지 않음), 적힌 때와 끝난 때, 까닭. 결제된 것은 그 주문(A8)으로 가는 길을 붙인다.
// 지난 것은 주문 내역(A8)에서 본다(결제된 것만 있다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { AutoChargeHistoryItem } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { goldLabel, wonLabel } from '../charge/chargeView';
import { historyNote, historyStatusLabel } from './autoChargeHistoryView';
import { autoChargeHistoryQuery } from './autoChargeQueries';
import { walletProblemText } from './walletProblem';

export function AutoChargeHistory() {
  const [open, setOpen] = useState(false);
  return (
    <section className="page-section" aria-labelledby="auto-charge-history-heading">
      <h2 id="auto-charge-history-heading">최근 자동 결제</h2>
      <Button variant="secondary" aria-expanded={open} onClick={() => setOpen((before) => !before)}>
        {open ? '접기' : '보기'}
      </Button>
      {open ? <HistoryList /> : null}
    </section>
  );
}

/** 받은 내역. 열 때 받는다 */
function HistoryList() {
  const query = useQuery(autoChargeHistoryQuery());
  if (query.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (query.isError) {
    return (
      <Notice tone="error">
        {walletProblemText(query.error)}{' '}
        <Button variant="quiet" onClick={() => void query.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  if (query.data.items.length === 0) return <p className="hint">아직 자동 결제가 없습니다.</p>;
  return (
    <ol className="plain-list" aria-label="최근 자동 결제, 최근 것이 위">
      {query.data.items.map((item) => (
        <HistoryLine key={item.id} item={item} />
      ))}
    </ol>
  );
}

function HistoryLine({ item }: { item: AutoChargeHistoryItem }) {
  const title = `${goldLabel(item.credits)} · ${wonLabel(item.price)}`;
  const note = historyNote(item);
  return (
    <li className={`auto-charge-history auto-charge-history--${item.status}`}>
      <p>
        {item.status === 'paid' ? <Link to={`/wallet/orders/${item.id}`}>{title}</Link> : title} · {historyStatusLabel(item.status)}
      </p>
      <p className="hint">
        {formatDateTime(item.created_at)}
        {item.finished_at ? ` · 끝남 ${formatDateTime(item.finished_at)}` : ''}
      </p>
      {note ? <p className="hint">{note}</p> : null}
    </li>
  );
}
