// web/apps/web/src/pages/trpg/portraits/PortraitChooser.tsx
// 프리젠의 캐릭터 그림(#983) 칸. 붙인 그림을 보이고 "그림 붙이기"·"바꾸기"·"떼기"를 둔다.
// 고르기는 창 안에서 펼치는 칸이다(프리젠 창 안이라 창을 겹치지 않는다): 새 그림 올리기와 내가 올린 그림(최근 것부터, 더 보기).
// 내가 올린 그림마다 지우기(한 번 더 묻는다)가 있다. 프리젠에 붙은 그림은 서버가 막고(409) 쓰는 시나리오들을 알려 준다.
// 저장은 쓰는 쪽(프리젠 창)이 한다. 고른 그림은 저장해야 붙는다.

import { Button } from '@ai-trpg/ui';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { useId, useState, type ChangeEvent } from 'react';
import { Link } from 'react-router';
import { deletePortrait, uploadPortrait, type Portrait } from '../../../api/portraits';
import type { FormProblem } from '../../../auth/problem';
import { IMAGE_ACCEPT, imageFileProblem } from '../../../components/imageFile';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { MyPortrait } from './MyPortrait';
import { describePortraitDeleteProblem, describePortraitUploadProblem, portraitUsers, type PortraitUser } from './portraitProblem';
import { portraitsKey, portraitsQuery } from './portraitQueries';

type Props = { imageId: string | null; onChange: (imageId: string | null) => void };

export function PortraitChooser({ imageId, onChange }: Props) {
  const [open, setOpen] = useState(false);

  function choose(chosen: string) {
    onChange(chosen);
    setOpen(false);
  }

  return (
    <div className="portrait-chooser" role="group" aria-label="캐릭터 그림">
      <span className="ui-field__label">그림(선택)</span>
      {imageId ? <MyPortrait portraitId={imageId} alt="붙인 캐릭터 그림" /> : <p className="hint">붙인 그림이 없습니다.</p>}
      <p className="hint">장면 그림을 그릴 때 이 캐릭터의 얼굴을 맞추는 데 씁니다. 저장해야 붙습니다.</p>
      <span className="action-chips">
        <Button variant="secondary" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
          {imageId ? '바꾸기' : '그림 붙이기'}
        </Button>
        {imageId ? (
          <Button variant="quiet" onClick={() => onChange(null)}>
            떼기
          </Button>
        ) : null}
      </span>
      {open ? <PortraitShelf chosen={imageId} onChoose={choose} onForget={(gone) => gone === imageId && onChange(null)} /> : null}
    </div>
  );
}

type ShelfProps = { chosen: string | null; onChoose: (imageId: string) => void; onForget: (imageId: string) => void };

/** 새 그림 올리기와 내가 올린 그림들 */
function PortraitShelf({ chosen, onChoose, onForget }: ShelfProps) {
  const portraits = useInfiniteQuery(portraitsQuery());
  const items = portraits.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className="portrait-shelf" aria-label="캐릭터 그림 고르기">
      <PortraitUpload onUploaded={onChoose} />
      <h3 className="portrait-shelf__heading">내가 올린 그림</h3>
      {portraits.isPending ? <p className="hint">불러오는 중…</p> : null}
      {portraits.isError ? <p className="ui-field__error">그림 목록을 불러오지 못했습니다.</p> : null}
      {portraits.isSuccess && items.length === 0 ? <p className="hint">아직 올린 그림이 없습니다.</p> : null}
      <ul className="plain-list portrait-shelf__grid" aria-label="내가 올린 그림">
        {items.map((portrait, index) => (
          <ShelfItem
            key={portrait.id}
            portrait={portrait}
            number={index + 1}
            chosen={portrait.id === chosen}
            onChoose={onChoose}
            onForget={onForget}
          />
        ))}
      </ul>
      {portraits.hasNextPage ? (
        <Button variant="quiet" busy={portraits.isFetchingNextPage} onClick={() => void portraits.fetchNextPage()}>
          더 보기
        </Button>
      ) : null}
    </section>
  );
}

/** 새 그림 올리기. 올리면 바로 고른 그림이 된다 */
function PortraitUpload({ onUploaded }: { onUploaded: (imageId: string) => void }) {
  const inputId = useId();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const early = imageFileProblem(file);
    if (early) {
      setProblem({ message: early });
      return;
    }
    setBusy(true);
    setProblem(undefined);
    try {
      const uploaded = await uploadPortrait(file);
      void queryClient.invalidateQueries({ queryKey: portraitsKey() });
      onUploaded(uploaded.id);
    } catch (error) {
      setProblem(describePortraitUploadProblem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="portrait-shelf__upload">
      <label className="ui-field__label" htmlFor={inputId}>
        새 그림 올리기
      </label>
      <input id={inputId} type="file" accept={IMAGE_ACCEPT} disabled={busy} onChange={(event) => void upload(event)} />
      {busy ? <span aria-busy="true"> 올리는 중</span> : null}
      <p className="ui-field__hint">PNG, JPEG, WebP 그림을 10MB 까지 올립니다.</p>
      <ProblemNotice problem={problem} />
    </div>
  );
}

type ItemProps = {
  portrait: Portrait;
  number: number;
  chosen: boolean;
  onChoose: (imageId: string) => void;
  onForget: (imageId: string) => void;
};

/** 내가 올린 그림 하나. 고르기와 지우기(한 번 더 묻는다) */
function ShelfItem({ portrait, number, chosen, onChoose, onForget }: ItemProps) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const [users, setUsers] = useState<PortraitUser[]>([]);
  const name = `그림 ${number}`;

  async function remove() {
    setBusy(true);
    setProblem(undefined);
    setUsers([]);
    try {
      await deletePortrait(portrait.id);
      onForget(portrait.id);
      void queryClient.invalidateQueries({ queryKey: portraitsKey() });
    } catch (error) {
      setProblem(describePortraitDeleteProblem(error));
      setUsers(portraitUsers(error));
      setAsking(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="portrait-shelf__item">
      <MyPortrait portraitId={portrait.id} alt={name} />
      <span className="action-chips">
        <Button variant={chosen ? 'primary' : 'secondary'} aria-pressed={chosen} aria-label={`${name} 고르기`} onClick={() => onChoose(portrait.id)}>
          {chosen ? '고름' : '고르기'}
        </Button>
        {asking ? (
          <>
            <Button variant="quiet" busy={busy} aria-label={`${name} 지우기 확인`} onClick={() => void remove()}>
              지우기 확인
            </Button>
            <Button variant="quiet" onClick={() => setAsking(false)}>
              그대로 두기
            </Button>
          </>
        ) : (
          <Button variant="quiet" aria-label={`${name} 지우기`} onClick={() => setAsking(true)}>
            지우기
          </Button>
        )}
      </span>
      {asking ? <p className="hint">지우면 되돌릴 수 없습니다.</p> : null}
      <ProblemNotice problem={problem} />
      {users.length > 0 ? (
        <ul className="plain-list" aria-label={`${name}을 쓰는 시나리오`}>
          {users.map((user) => (
            <li key={user.id}>
              <Link to={`/trpg/studio/scenarios/${encodeURIComponent(user.id)}?tab=characters`}>{user.title}</Link>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}
