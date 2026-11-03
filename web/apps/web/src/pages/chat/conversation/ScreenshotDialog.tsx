// web/apps/web/src/pages/chat/conversation/ScreenshotDialog.tsx
// 스크린샷 창(#982). 지금 가지의 말들 가운데 처음과 끝을 고르면 그 사이를 모두 넣어 그림(PNG)으로 내려받는다.
// 이름, 대표 그림, 지금 화면의 테마 색을 담고, 성인 등급이면 "성인"을 부제에 남긴다. 아래에 사이트 이름을 작게 넣는다.
// 화면에서만 만든다. 서버에 올리지 않는다. chat 의 대화와 story 의 장면이 함께 쓴다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useState } from 'react';
import { fetchImage } from '../../../api/images';
import { downloadBlob, drawShot } from './drawShot';
import { contiguousRange, SHOT_MAX_ITEMS, shotFileName, type ShotItem } from './screenshotView';

type Props = {
  title: string;
  subtitle: string;
  items: ShotItem[];
  imageId: string | null;
  open: boolean;
  onClose: () => void;
};

export function ScreenshotDialog({ title, subtitle, items, imageId, open, onClose }: Props) {
  return (
    <Dialog title="그림으로 저장" open={open} onClose={onClose}>
      {open ? <ScreenshotBody title={title} subtitle={subtitle} items={items} imageId={imageId} /> : null}
    </Dialog>
  );
}

function ScreenshotBody({ title, subtitle, items, imageId }: Omit<Props, 'open' | 'onClose'>) {
  const [picked, setPicked] = useState<ReadonlySet<string>>(() => new Set(items.slice(-2).map((item) => item.id)));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const range = contiguousRange(items, picked);
  const tooMany = range.length > SHOT_MAX_ITEMS;

  function toggle(id: string) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function make() {
    setBusy(true);
    setProblem(null);
    const picture = imageId ? await fetchImage(imageId).catch(() => null) : null;
    const blob = await drawShot(title, subtitle, range, picture);
    if (blob) downloadBlob(blob, shotFileName(title));
    else setProblem('이 브라우저에서는 그림을 만들 수 없습니다.');
    setBusy(false);
  }

  return (
    <div className="chat-notes">
      <p className="hint">넣을 말의 처음과 끝을 고르면 그 사이의 말이 모두 들어갑니다. 그림은 이 기기에서만 만들고 서버에 올리지 않습니다.</p>
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      <ul className="plain-list chat-inventory" aria-label="넣을 말">
        {items.map((item) => (
          <li key={item.id}>
            <label>
              <input type="checkbox" checked={picked.has(item.id)} onChange={() => toggle(item.id)} /> {item.label}
            </label>
          </li>
        ))}
      </ul>
      <p className="hint">{tooMany ? `한 번에 ${SHOT_MAX_ITEMS}개까지 넣습니다. 구간을 줄여 주세요.` : `${range.length}개의 말이 들어갑니다.`}</p>
      <Button disabled={busy || range.length === 0 || tooMany} onClick={() => void make()}>
        그림 만들기
      </Button>
    </div>
  );
}
