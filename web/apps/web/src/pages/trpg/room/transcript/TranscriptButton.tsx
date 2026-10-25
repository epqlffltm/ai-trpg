// web/apps/web/src/pages/trpg/room/transcript/TranscriptButton.tsx
// 테이블 방의 머리에 두는 "기록 받기". 창에서 형식(마크다운, 웹 문서, 글)을 고르면 그 파일을 내려받는다.
// 받기 시작한 때까지의 서술, 선언, 판정, 상태의 변화, 채팅, 내가 보내거나 받은 쪽지가 들어간다. 사람은 캐릭터 이름으로만 쓴다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import { TRANSCRIPT_FORMATS } from '../../../../api/transcripts';
import type { TableDetail } from '../../../../api/types';
import { formatHint, formatLabel } from './transcriptView';
import { useTranscriptDownload } from './useTranscriptDownload';

export function TranscriptButton({ table }: { table: TableDetail }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const downloading = useTranscriptDownload(table.id, table.title);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        기록 받기
      </Button>
      <Dialog title="기록 받기" open={open} onClose={close}>
        <p className="hint">
          지금까지의 서술, 선언, 판정, 상태의 변화, 채팅과 내가 보내거나 받은 쪽지를 파일 하나로 받습니다. 사람은 캐릭터 이름으로만 씁니다. 10분에 10번까지 받습니다.
        </p>
        {downloading.problem ? <Notice tone="error">{downloading.problem}</Notice> : null}
        {downloading.saved ? <Notice>받았습니다: {downloading.saved}</Notice> : null}
        <ul className="plain-list transcript-formats" aria-label="기록의 형식">
          {TRANSCRIPT_FORMATS.map((format) => (
            <li key={format}>
              <Button variant="secondary" busy={downloading.busy === format} disabled={downloading.busy !== null} onClick={() => void downloading.download(format)}>
                {formatLabel(format)}
              </Button>{' '}
              <span className="hint">{formatHint(format)}</span>
            </li>
          ))}
        </ul>
      </Dialog>
    </>
  );
}
