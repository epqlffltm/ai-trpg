// web/apps/web/src/pages/gallery/SceneTile.tsx
// 갤러리의 칸 하나. 연 씬은 그림과 이름, 연 날이고 누르면 크게 본다. 열지 않은 씬은 흐린 그림이고 이름을 가린다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { formatDate } from '../../format/dateTime';
import { useImageUrl } from '../../hooks/useImageUrl';
import type { SceneCell } from './galleryView';

export function SceneTile({ cell }: { cell: SceneCell }) {
  const image = useImageUrl(cell.imageId);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const opened = cell.unlockedAt !== null;
  const picture = image.url ? <img src={image.url} alt={opened ? cell.title : '아직 열지 않은 장면'} className="scene-tile__image" /> : <div className="scene-tile__image scene-tile__image--empty" aria-hidden="true" />;

  if (!opened) {
    return (
      <li className="scene-tile scene-tile--locked">
        {picture}
        <p className="hint">아직 열지 않음</p>
      </li>
    );
  }
  return (
    <li className="scene-tile">
      <Button variant="quiet" aria-label={`${cell.title} 크게 보기`} onClick={() => setOpen(true)}>
        {picture}
      </Button>
      <p className="scene-tile__title">{cell.title}</p>
      <p className="hint">{formatDate(cell.unlockedAt as string)}</p>
      <Dialog title={cell.title} open={open} onClose={close}>
        {image.url ? <img src={image.url} alt={cell.title} className="scene-tile__large" /> : <p className="hint">그림을 불러오지 못했습니다.</p>}
      </Dialog>
    </li>
  );
}
