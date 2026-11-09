// web/apps/web/src/pages/operator/inquiries/InquiryBox.tsx
// 상자 하나: 도구 줄(모두 고르기, 고른 것 지우기, 상자 비우기), 목록, 열린 문의. 고른 것은 이 상자에 보이는 줄 안에서만이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { deleteInquiries, type AdminInquiry, type InquiryFolder } from '../../../api/inquiryAdmin';
import type { FormProblem } from '../../../auth/problem';
import { ConfirmButton } from '../../../components/ConfirmButton';
import { formatDateTime } from '../../../format/dateTime';
import { categoryLabel } from '../../support/inquiryView';
import { InquiryDetail } from './InquiryDetail';
import { ADMIN_INQUIRIES_KEY, adminInquiriesQuery } from './inquiryBoxQueries';
import { allSelected, boxLabel, boxProblemText, keepVisible, senderLabel, statusOf, toggled } from './inquiryBoxView';

type Props = { box: InquiryFolder; openId: string | null; onOpen: (id: string | null) => void };

export function InquiryBox({ box, openId, onOpen }: Props) {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery(adminInquiriesQuery(statusOf(box)));
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const ids = items.map((inquiry) => inquiry.id);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const selected = keepVisible(chosen, ids);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const [done, setDone] = useState<string | null>(null);

  async function remove(target: { ids: string[] } | { folder: InquiryFolder }): Promise<boolean> {
    setBusy(true);
    setProblem(undefined);
    try {
      const deleted = await deleteInquiries(target);
      setDone(`문의 ${deleted}개를 지웠습니다.`);
      setChosen(new Set());
      if (openId && ('folder' in target || target.ids.includes(openId))) onOpen(null);
      await queryClient.invalidateQueries({ queryKey: ADMIN_INQUIRIES_KEY });
      setBusy(false);
      return true;
    } catch (error) {
      setProblem({ message: boxProblemText(error) });
      setBusy(false);
      return false;
    }
  }

  return (
    <section className="inquiry-box" aria-label={boxLabel(box, undefined)}>
      <div className="inquiry-box__toolbar" role="toolbar" aria-label="고른 문의">
        <label className="inquiry-box__check">
          <input
            type="checkbox"
            checked={allSelected(selected, ids)}
            onChange={(event) => setChosen(event.target.checked ? new Set(ids) : new Set())}
            disabled={ids.length === 0}
          />
          보이는 문의 모두 고르기
        </label>
        <ConfirmButton
          label={`고른 것 지우기 (${selected.size})`}
          title="고른 문의를 지울까요?"
          confirm="지우기"
          busy={busy}
          problem={problem}
          onConfirm={() => remove({ ids: [...selected] })}
        >
          <p>고른 문의 {selected.size}개를 지웁니다. 되돌릴 수 없습니다. 이미 보낸 답 메일은 그대로 갑니다.</p>
        </ConfirmButton>
        <ConfirmButton
          label="이 상자 비우기"
          title={`"${boxLabel(box, undefined)}" 상자를 비울까요?`}
          confirm="모두 지우기"
          busy={busy}
          problem={problem}
          onConfirm={() => remove({ folder: box })}
        >
          <p>이 상자의 문의를 지금 보이지 않는 것까지 모두 지웁니다. 되돌릴 수 없습니다.</p>
        </ConfirmButton>
      </div>
      {done ? <Notice>{done}</Notice> : null}
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">이 상자에 문의가 없습니다.</p> : null}
      {items.length > 0 ? (
        <ul className="plain-list inquiry-box__list" aria-label="문의">
          {items.map((inquiry) => (
            <InquiryRow
              key={inquiry.id}
              inquiry={inquiry}
              checked={selected.has(inquiry.id)}
              open={inquiry.id === openId}
              onCheck={() => setChosen(toggled(selected, inquiry.id))}
              onOpen={() => onOpen(inquiry.id)}
            />
          ))}
        </ul>
      ) : null}
      {query.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
      {openId ? <InquiryDetail key={openId} id={openId} onDeleted={() => onOpen(null)} /> : null}
    </section>
  );
}

type RowProps = { inquiry: AdminInquiry; checked: boolean; open: boolean; onCheck: () => void; onOpen: () => void };

function InquiryRow({ inquiry, checked, open, onCheck, onOpen }: RowProps) {
  const unread = inquiry.read_at === null;
  const classes = ['inquiry-row', unread ? 'inquiry-row--unread' : '', open ? 'inquiry-row--open' : ''].filter(Boolean).join(' ');
  return (
    <li className={classes}>
      <input type="checkbox" checked={checked} onChange={onCheck} aria-label={`${inquiry.title} 고르기`} />
      <button type="button" className="inquiry-row__open" aria-current={open ? 'true' : undefined} onClick={onOpen}>
        <span className="inquiry-row__sender">{senderLabel(inquiry)}</span>
        <span className="inquiry-row__category">{categoryLabel(inquiry.category)}</span>
        <span className="inquiry-row__title">
          {unread ? <span className="visually-hidden">안 읽음 </span> : null}
          {inquiry.title}
        </span>
        <span className="inquiry-row__status">{inquiry.status === 'answered' ? '답함' : ''}</span>
        <span className="inquiry-row__date">{formatDateTime(inquiry.created_at)}</span>
      </button>
    </li>
  );
}
