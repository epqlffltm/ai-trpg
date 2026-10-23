// web/apps/web/src/pages/operator/ReasonField.tsx
// 운영자가 쓰는 사유 한 칸. 조치와 보기마다 감사 기록에 남는다. 신고한 사람과 주인에게는 가지 않는다.

import { TextAreaField } from '../../components/TextAreaField';
import { REASON_MAX_LENGTH } from './moderationPure';

type Props = { label: string; value: string; error: string | undefined; onChange: (value: string) => void };

export function ReasonField({ label, value, error, onChange }: Props) {
  return (
    <TextAreaField
      label={label}
      value={value}
      rows={2}
      maxLength={REASON_MAX_LENGTH}
      error={error}
      hint={`감사 기록에만 남고 당사자에게는 가지 않습니다. ${REASON_MAX_LENGTH}자까지.`}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
