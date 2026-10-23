// web/apps/web/src/pages/trpg/studio/collection/ItemsSection.tsx
// 묶음에 담긴 것(로어북의 항목, 몬스터 모음의 몬스터)의 목록. 종류로 거르고, 더하기와 고치기는 창에서, 지우기는 한 번 더 묻는다.
// 무엇을 적는지(입력)는 쓰는 쪽이 form 으로 넘긴다. 이 파일은 목록과 창의 열고 닫기만 맡는다.

import { Button, ChipGroup, Dialog, Notice } from '@ai-trpg/ui';
import { useCallback, useState, type ReactNode } from 'react';
import type { FormProblem } from '../../../../auth/problem';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { itemsOfKind, kindCounts } from './itemsView';

type Item = { id: string; name: string; kind: string };

type Props<T extends Item> = {
  /** 담긴 것의 이름(항목, 몬스터) */
  label: string;
  max: number;
  items: T[] | undefined;
  pending: boolean;
  failed: boolean;
  retry: () => void;
  kindLabels: Record<string, string>;
  /** 목록 한 줄의 설명 */
  summary: (item: T) => ReactNode;
  /** 창 안의 입력. item 이 null 이면 더하기. 끝나면 done 을 부른다 */
  form: (item: T | null, done: () => void) => ReactNode;
  remove: (item: T) => Promise<boolean>;
  removing: { busy: boolean; problem: FormProblem | undefined };
};

export function ItemsSection<T extends Item>(props: Props<T>) {
  const { label, max, items } = props;
  const [kind, setKind] = useState<string | undefined>();
  const [editing, setEditing] = useState<T | 'new' | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const all = items ?? [];
  const full = all.length >= max;
  return (
    <section className="page-section" aria-labelledby="items-heading">
      <h2 id="items-heading">
        {label} <span className="hint">({all.length} / {max})</span>
      </h2>
      <p>
        <Button variant="secondary" disabled={full || !items} onClick={() => setEditing('new')}>
          {label} 더하기
        </Button>
        {full ? <span className="hint"> {max}개까지 담을 수 있습니다.</span> : null}
      </p>
      <ItemsBody {...props} kind={kind} setKind={setKind} edit={setEditing} />
      <Dialog title={editing === 'new' ? `${label} 더하기` : `${label} 고치기`} open={editing !== null} onClose={close}>
        {editing !== null ? props.form(editing === 'new' ? null : editing, close) : null}
      </Dialog>
    </section>
  );
}

type BodyProps<T extends Item> = Props<T> & {
  kind: string | undefined;
  setKind: (kind: string | undefined) => void;
  edit: (item: T) => void;
};

function ItemsBody<T extends Item>({ label, items, pending, failed, retry, kindLabels, summary, remove, removing, kind, setKind, edit }: BodyProps<T>) {
  if (pending) return <p aria-busy="true">불러오는 중</p>;
  if (failed || !items) {
    return (
      <Notice tone="error">
        {label} 목록을 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={retry}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  if (items.length === 0) return <p className="hint">아직 담긴 것이 없습니다.</p>;
  const chips = kindCounts(items, kindLabels).map((entry) => ({ value: entry.kind, label: `${entry.label} ${entry.count}` }));
  return (
    <>
      {chips.length > 1 ? <ChipGroup<string> label="종류로 거르기" chips={chips} selected={kind} onChange={setKind} /> : null}
      <ul className="plain-list studio-list" aria-label={label}>
        {itemsOfKind(items, kind).map((item) => (
          <li key={item.id} className="studio-list__item studio-item">
            <div>
              <strong>{item.name}</strong> <span className="hint">{kindLabels[item.kind] ?? item.kind}</span>
              <div className="studio-list__description">{summary(item)}</div>
            </div>
            <span className="action-chips">
              <Button variant="quiet" aria-label={`${item.name} 고치기`} onClick={() => edit(item)}>
                고치기
              </Button>
              <ConfirmButton
                label="지우기"
                ariaLabel={`${item.name} 지우기`}
                title={`${label} 지우기`}
                confirm="지우기"
                busy={removing.busy}
                problem={removing.problem}
                onConfirm={() => remove(item)}
              >
                <p>「{item.name}」</p>
                <p>지우면 되돌릴 수 없습니다. 이것을 가리키는 시나리오의 규칙이 있으면 다음에 게시할 때 알려 줍니다.</p>
              </ConfirmButton>
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
