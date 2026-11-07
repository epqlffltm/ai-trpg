// web/apps/web/src/pages/chat/conversation/ScreenshotDialog.tsx
// 스크린샷 창(#982, Stitch 43번). 지금 가지의 말들 가운데 처음 말과 끝 말을 셀렉트로 고르면 그 사이를 모두 넣어 그림(PNG)으로 내려받는다.
// 옆(좁으면 아래)에 그릴 것의 미리 보기를 글로 보인다.
// 이름, 대표 그림, 지금 화면의 테마 색을 담고, 성인 등급이면 "성인"을 부제에 남긴다. 아래에 사이트 이름을 작게 넣는다.
// 화면에서만 만든다. 서버에 올리지 않는다. chat 의 대화와 story 의 장면이 함께 쓴다.

import { Button, Dialog, Notice, SelectField } from '@ai-trpg/ui';
import { useState } from 'react';
import { fetchImage } from '../../../api/images';
import { downloadBlob, drawShot } from './drawShot';
import { contiguousRange, SHOT_MAX_ITEMS, shotFileName, SITE_NAME, type ShotItem } from './screenshotView';

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
  const [startId, setStartId] = useState(() => items.at(-2)?.id ?? items.at(-1)?.id ?? '');
  const [endId, setEndId] = useState(() => items.at(-1)?.id ?? '');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const range = contiguousRange(items, new Set([startId, endId]));
  const tooMany = range.length > SHOT_MAX_ITEMS;

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
    <div className="chat-notes shot-dialog">
      <p className="hint">처음 말과 끝 말을 고르면 그 사이의 말이 모두 들어갑니다. 그림은 이 기기에서만 만들고 서버에 올리지 않습니다.</p>
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      <div className="shot-dialog__body">
        <div className="shot-dialog__picks">
          <ItemSelect label="처음 말" items={items} value={startId} onChange={setStartId} />
          <ItemSelect label="끝 말" items={items} value={endId} onChange={setEndId} />
          <p className="hint">{tooMany ? `한 번에 ${SHOT_MAX_ITEMS}개까지 넣습니다. 구간을 줄여 주세요.` : `${range.length}개의 말이 들어갑니다.`}</p>
        </div>
        <ShotPreview title={title} subtitle={subtitle} items={tooMany ? [] : range} />
      </div>
      <Button disabled={busy || range.length === 0 || tooMany} onClick={() => void make()}>
        저장
      </Button>
    </div>
  );
}

/** 처음이나 끝의 말을 고르는 셀렉트. 말마다 앞의 한 줄을 보인다 */
function ItemSelect({ label, items, value, onChange }: { label: string; items: ShotItem[]; value: string; onChange: (id: string) => void }) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {items.map((item, index) => (
        <option key={item.id} value={item.id}>
          {`${index + 1}. ${item.label}`}
        </option>
      ))}
    </SelectField>
  );
}

/** 그림의 미리 보기. 그릴 것과 같은 차례(제목, 부제, 말한 이와 글, 아래에 사이트 이름)를 글로 보인다 */
function ShotPreview({ title, subtitle, items }: { title: string; subtitle: string; items: ShotItem[] }) {
  return (
    <figure className="shot-preview" aria-label="미리 보기">
      <p className="shot-preview__title">{title}</p>
      {subtitle ? <p className="shot-preview__subtitle">{subtitle}</p> : null}
      <div className="shot-preview__lines">
        {items.flatMap((item) =>
          item.lines.map((line, index) => (
            <p key={`${item.id}-${index}`} className="shot-preview__line">
              {line.speaker ? <span className="shot-preview__speaker">{line.speaker}</span> : null}
              {line.text}
            </p>
          )),
        )}
      </div>
      <figcaption className="shot-preview__footer">{SITE_NAME}</figcaption>
    </figure>
  );
}
