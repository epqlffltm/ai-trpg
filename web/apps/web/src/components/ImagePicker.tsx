// web/apps/web/src/components/ImagePicker.tsx
// 그림 한 칸. 지금 붙은 그림의 미리 보기, 올리기(파일 고르기), 떼기. 올리면 새 그림의 id 를 넘긴다.
// 저장은 쓰는 쪽(탭)이 한다. 올린 그림은 아무 데도 붙이지 않아도 저장소에 남는다(주인만 본다).

import { Button } from '@ai-trpg/ui';
import { useId, useState, type ChangeEvent } from 'react';
import { uploadImage } from '../api/images';
import type { FormProblem } from '../auth/problem';
import { useImageUrl } from '../hooks/useImageUrl';
import { describeUploadProblem, IMAGE_ACCEPT, imageFileProblem } from './imageFile';
import { ProblemNotice } from './ProblemNotice';

type Props = {
  label: string;
  imageId: string | null;
  onChange: (imageId: string | null) => void;
  hint?: string;
  /** 미리 보기를 체크무늬 위에 그린다. 투명한 그림(캐릭터 그림)이 투명한지 보인다 */
  checkered?: boolean;
};

export function ImagePicker({ label, imageId, onChange, hint, checkered = false }: Props) {
  const inputId = useId();
  const preview = useImageUrl(imageId);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();

  async function choose(event: ChangeEvent<HTMLInputElement>) {
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
      onChange((await uploadImage(file)).id);
    } catch (error) {
      setProblem(describeUploadProblem(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="image-picker">
      <label className="ui-field__label" htmlFor={inputId}>
        {label}
      </label>
      {imageId === null ? <p className="hint">붙인 그림이 없습니다.</p> : null}
      {imageId !== null && preview.url ? <img
          className={checkered ? 'image-picker__preview image-picker__preview--checkered' : 'image-picker__preview'}
          src={preview.url}
          alt={label}
        /> : null}
      {imageId !== null && !preview.url ? <p className="hint">{preview.failed ? '미리 보기를 불러오지 못했습니다.' : '붙인 그림이 있습니다.'}</p> : null}
      <input id={inputId} type="file" accept={IMAGE_ACCEPT} disabled={busy} onChange={(event) => void choose(event)} />
      {busy ? <span aria-busy="true"> 올리는 중</span> : null}
      {hint ? <p className="ui-field__hint">{hint}</p> : null}
      <ProblemNotice problem={problem} />
      {imageId !== null ? (
        <Button variant="quiet" onClick={() => onChange(null)} aria-label={`${label} 떼기`}>
          떼기
        </Button>
      ) : null}
    </div>
  );
}
