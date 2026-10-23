// web/apps/web/src/pages/trpg/room/host/TableSettings.tsx
// 방장이 바꾸는 진행의 설정. 고르면 바로 보낸다(칸마다 따로 주소가 있다). 다른 사람은 이벤트로 다시 읽는다.
//   - 서술 문체: 다음 서술부터. 시나리오의 추천 문체에 "(추천)"을 붙인다
//   - 라운드 시간 제한: 다음 라운드부터(지금 열린 라운드의 마감은 그대로)
//   - 크레딧이 모자란 사람을 기다리는 시간과 빼기: 지금 기다리는 라운드에도 바로
//   - 쪽지 알림: 바꾼 뒤에 보내는 쪽지부터
//   - 참고 자료: 모집 중에만. 판의 세계관이 허용하지 않으면 서버가 거절한다
// 서술 모델(B8)은 따로다. 고를 거리는 테이블 만들기(B4)와 같다.

import { Checkbox, SelectField } from '@ai-trpg/ui';
import {
  changeCreditWait,
  changeNarrationStyle,
  changeReferences,
  changeRoundTimeLimit,
  changeWhisperNotice,
} from '../../../../api/tableHost';
import type { NarrationStyle, TableDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { durationLabel, NARRATION_STYLE_VALUES, narrationStyleLabel } from '../../labels';
import { CREDIT_WAITS, ROUND_LIMITS } from '../../tables/createForm';
import { useHostAction } from './useHostAction';

export function TableSettings({ table }: { table: TableDetail }) {
  const action = useHostAction(table.id);
  const run = (call: () => ReturnType<typeof changeWhisperNotice>) => void action.run(call);
  return (
    <div className="host-settings" aria-busy={action.busy || undefined}>
      <ProblemNotice problem={action.problem} />
      <SelectField
        label="서술 문체"
        hint={`시나리오의 추천은 ${narrationStyleLabel(table.recommended_narration_style)}입니다.`}
        value={table.narration_style}
        disabled={action.busy}
        onChange={(event) => run(() => changeNarrationStyle(table.id, event.target.value as NarrationStyle))}
      >
        {NARRATION_STYLE_VALUES.map((style) => (
          <option key={style} value={style}>
            {narrationStyleLabel(style)}
            {style === table.recommended_narration_style ? '(추천)' : ''}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="라운드 시간 제한"
        hint="다음 라운드부터 씁니다."
        value={table.round_time_limit === null ? '' : String(table.round_time_limit)}
        disabled={action.busy}
        onChange={(event) =>
          run(() => changeRoundTimeLimit(table.id, event.target.value === '' ? null : Number(event.target.value)))
        }
      >
        {withCurrent(ROUND_LIMITS, table.round_time_limit).map((seconds) => (
          <option key={seconds ?? 'none'} value={seconds === null ? '' : String(seconds)}>
            {durationLabel(seconds)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="크레딧이 모자란 사람을 기다리는 시간"
        value={String(table.credit_wait_seconds)}
        disabled={action.busy}
        onChange={(event) => run(() => changeCreditWait(table.id, Number(event.target.value), table.remove_short_payers))}
      >
        {withCurrent(CREDIT_WAITS, table.credit_wait_seconds).map((seconds) => (
          <option key={seconds} value={String(seconds)}>
            {durationLabel(seconds)}
          </option>
        ))}
      </SelectField>
      <Checkbox
        label="기다려도 모자라면 그 사람을 빼고 서술하기"
        checked={table.remove_short_payers}
        disabled={action.busy}
        onChange={(event) => run(() => changeCreditWait(table.id, table.credit_wait_seconds, event.target.checked))}
      />
      <Checkbox
        label="쪽지 알림"
        description="쪽지를 보냈다는 사실을 모두에게 알립니다. 내용은 알리지 않습니다."
        checked={table.whisper_notice}
        disabled={action.busy}
        onChange={(event) => run(() => changeWhisperNotice(table.id, event.target.checked))}
      />
      {table.status === 'recruiting' ? (
        <Checkbox
          label="참고 자료 켜기"
          description="SRD 같은 바깥 자료를 서술에 참고합니다. 시작하면 바꿀 수 없습니다."
          checked={table.references_enabled}
          disabled={action.busy}
          onChange={(event) => run(() => changeReferences(table.id, event.target.checked))}
        />
      ) : null}
    </div>
  );
}

/** 고를 거리에 지금 값이 없으면(다른 곳에서 정했다) 넣어 둔다. 고르기 칸이 지금 값을 보이게 */
export function withCurrent<T extends number | null>(choices: T[], current: T): T[] {
  return choices.includes(current) ? choices : [...choices, current];
}
