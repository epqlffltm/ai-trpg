// web/apps/web/src/pages/trpg/portraits/CharacterAvatar.tsx
// 캐릭터 이름 앞의 동그란 그림(#983). 그림이 있으면 그림을, 없거나 받지 못하면 이름의 첫 글자를 둔다.
//   - TableAvatar: 앉은 테이블의 그림(GET /tables/{id}/portraits/{pid}/image)
//   - ListingAvatar: 공개 소개의 그림(GET /listings/{scenario_id}/portraits/{pid}/image)
// enlarge 면 그림을 누를 때 크게 보는 창을 연다. 저장과 지우기는 두지 않는다(제작자의 그림이다).

import { Dialog } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { listingPortraitImageQuery, tablePortraitImageQuery } from './portraitQueries';
import { useBlobUrl } from './useBlobUrl';

/** 이름의 첫 글자. 비었으면 빈 글자 */
export function initialOf(name: string): string {
  return Array.from(name.trim())[0] ?? '';
}

type AvatarProps = { name: string; url: string | null; enlarge?: boolean };

/** 받은 주소로 그린다. 주소가 없으면 첫 글자다 */
export function Avatar({ name, url, enlarge = false }: AvatarProps) {
  const [open, setOpen] = useState(false);
  if (!url) {
    return (
      <span className="portrait-avatar portrait-avatar--initial" aria-hidden="true">
        {initialOf(name)}
      </span>
    );
  }
  if (!enlarge) return <img className="portrait-avatar" src={url} alt={`${name}의 그림`} />;
  return (
    <>
      <button type="button" className="portrait-avatar__button" aria-label={`${name}의 그림 크게 보기`} onClick={() => setOpen(true)}>
        <img className="portrait-avatar" src={url} alt="" />
      </button>
      <Dialog title={`${name}의 그림`} open={open} onClose={() => setOpen(false)}>
        <img className="portrait-large" src={url} alt={`${name}의 그림`} />
        <p className="hint">시나리오 제작자가 붙인 그림입니다.</p>
      </Dialog>
    </>
  );
}

type TableProps = { tableId: string; portraitId: string | null | undefined; name: string; enlarge?: boolean };

export function TableAvatar({ tableId, portraitId, name, enlarge = false }: TableProps) {
  const image = useQuery({ ...tablePortraitImageQuery(tableId, portraitId ?? ''), enabled: Boolean(portraitId) });
  const url = useBlobUrl(portraitId ? image.data : undefined);
  return <Avatar name={name} url={url} enlarge={enlarge} />;
}

type ListingProps = { scenarioId: string; portraitId: string | null | undefined; name: string };

export function ListingAvatar({ scenarioId, portraitId, name }: ListingProps) {
  const image = useQuery({ ...listingPortraitImageQuery(scenarioId, portraitId ?? ''), enabled: Boolean(portraitId) });
  const url = useBlobUrl(portraitId ? image.data : undefined);
  return <Avatar name={name} url={url} />;
}
