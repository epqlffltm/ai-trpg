// web/packages/ui/src/ListSection.tsx
// 제목이 붙은 목록 한 줄의 틀. 불러오는 중, 불러오지 못함(다시 시도), 비었음, 내용 가운데 하나를 그린다.
// 줄마다 따로 불러오고 따로 실패한다(화면 명세의 A1 "줄마다 따로"). 한 줄의 실패가 다른 줄을 지우지 않는다.

import type { ReactNode } from 'react';
import { Button } from './Button';

export type ListStatus = 'loading' | 'error' | 'empty' | 'ready';

export type ListSectionProps = {
  title: string;
  status: ListStatus;
  /** 제목 옆의 링크 같은 것("더 보기") */
  action?: ReactNode;
  /** 비었을 때 다음에 할 일을 알리는 글 */
  emptyText?: ReactNode;
  onRetry?: () => void;
  children?: ReactNode;
};

export function ListSection({ title, status, action, emptyText, onRetry, children }: ListSectionProps) {
  return (
    <section className="ui-list-section" aria-busy={status === 'loading' || undefined}>
      <header className="ui-list-section__head">
        <h2 className="ui-list-section__title">{title}</h2>
        {action}
      </header>
      <ListBody status={status} emptyText={emptyText} onRetry={onRetry}>
        {children}
      </ListBody>
    </section>
  );
}

function ListBody({ status, emptyText, onRetry, children }: Omit<ListSectionProps, 'title' | 'action'>) {
  switch (status) {
    case 'loading':
      return <p className="ui-list-section__state">불러오는 중</p>;
    case 'error':
      return (
        <div className="ui-list-section__state" role="alert">
          <p>불러오지 못했습니다.</p>
          {onRetry ? (
            <Button variant="secondary" onClick={onRetry}>
              다시 시도
            </Button>
          ) : null}
        </div>
      );
    case 'empty':
      return <div className="ui-list-section__state">{emptyText ?? '아직 없습니다.'}</div>;
    case 'ready':
      return <>{children}</>;
  }
}
