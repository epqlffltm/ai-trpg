// web/apps/web/src/pages/trpg/room/transcript/useTranscriptDownload.ts
// 기록을 한 형식으로 받아 파일로 내려받게 한다. 한 번에 하나만 받는다(서버가 받는 수를 센다).
// 이름은 서버의 것(Content-Disposition)을 쓰고, 없으면 테이블 제목에 확장자를 붙인다. past 면 떠난 테이블의 기록이다.

import { useState } from 'react';
import { fetchTranscript, type TranscriptFormat } from '../../../../api/transcripts';
import { saveBlob } from '../../../../components/saveFile';
import { transcriptProblemText } from './transcriptProblem';
import { fallbackFilename } from './transcriptView';

type State = { busy: TranscriptFormat | null; problem: string | null; saved: string | null };

export function useTranscriptDownload(tableId: string, title: string, past = false) {
  const [state, setState] = useState<State>({ busy: null, problem: null, saved: null });

  async function download(format: TranscriptFormat): Promise<void> {
    if (state.busy) return;
    setState({ busy: format, problem: null, saved: null });
    try {
      const file = await fetchTranscript(tableId, format, past);
      const name = file.filename ?? fallbackFilename(title, format);
      saveBlob(file.blob, name);
      setState({ busy: null, problem: null, saved: name });
    } catch (error) {
      setState({ busy: null, problem: transcriptProblemText(error), saved: null });
    }
  }

  return { ...state, download };
}
