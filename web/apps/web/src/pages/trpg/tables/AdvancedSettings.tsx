// web/apps/web/src/pages/trpg/tables/AdvancedSettings.tsx
// 테이블 만들기(B4)의 "자세한 설정". 접어 둔다. 서버가 모델 칸을 거절했으면 열어 둔다.
// 만든 뒤에 방장이 바꿀 수 있는 것: 문체, 라운드 시간 제한, 서술 모델, 크레딧 기다리기, 쪽지 알림, 참고 자료(모집 중).
// 바꿀 수 없는 것: 캐릭터 방식(그래서 여기서 좁힌다).

import { Checkbox, SelectField } from '@ai-trpg/ui';
import type { NarrationStyle, PublicListingDetail } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { characterModeLabel, durationLabel, NARRATION_STYLE_VALUES, narrationStyleLabel } from '../labels';
import { CREDIT_WAITS, ROUND_LIMITS, type CreateDraft } from './createForm';
import { ModelSelect } from './ModelSelect';

type Props = {
  listing: PublicListingDetail;
  draft: CreateDraft;
  onChange: (changes: Partial<CreateDraft>) => void;
  hints: Record<string, string>;
  problem: FormProblem | undefined;
};

export function AdvancedSettings({ listing, draft, onChange, hints, problem }: Props) {
  const mustOpen = Boolean(problem?.fields?.narration_model || hints.character_modes);
  return (
    <details className="advanced" open={mustOpen || undefined}>
      <summary>자세한 설정</summary>
      <ModelSelect
        value={draft.narrationModel}
        recommended={listing.recommended_narration_model}
        onChange={(narrationModel) => onChange({ narrationModel })}
        error={problem?.fields?.narration_model}
      />
      <SelectField
        label="서술 문체"
        value={draft.narrationStyle}
        onChange={(event) => onChange({ narrationStyle: event.target.value as NarrationStyle | '' })}
      >
        <option value="">시나리오의 추천</option>
        {NARRATION_STYLE_VALUES.map((style) => (
          <option key={style} value={style}>
            {narrationStyleLabel(style)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="라운드 시간 제한"
        hint="라운드가 열린 뒤 행동을 받는 시간입니다. 지나면 라운드를 닫고 서술합니다."
        value={draft.roundTimeLimit === null ? '' : String(draft.roundTimeLimit)}
        onChange={(event) => onChange({ roundTimeLimit: event.target.value === '' ? null : Number(event.target.value) })}
      >
        {ROUND_LIMITS.map((seconds) => (
          <option key={seconds ?? 'none'} value={seconds === null ? '' : String(seconds)}>
            {durationLabel(seconds)}
          </option>
        ))}
      </SelectField>
      <SelectField
        label="크레딧이 모자란 사람을 기다리는 시간"
        value={String(draft.creditWaitSeconds)}
        onChange={(event) => onChange({ creditWaitSeconds: Number(event.target.value) })}
      >
        {CREDIT_WAITS.map((seconds) => (
          <option key={seconds} value={String(seconds)}>
            {durationLabel(seconds)}
          </option>
        ))}
      </SelectField>
      <Checkbox
        label="기다려도 모자라면 그 사람을 빼고 서술하기"
        checked={draft.removeShortPayers}
        onChange={(event) => onChange({ removeShortPayers: event.target.checked })}
      />
      <Checkbox
        label="쪽지 알림"
        description="쪽지를 보냈다는 사실을 모두에게 알립니다. 내용은 알리지 않습니다."
        checked={draft.whisperNotice}
        onChange={(event) => onChange({ whisperNotice: event.target.checked })}
      />
      {listing.references_allowed ? (
        <Checkbox
          label="참고 자료 켜기"
          description="SRD 같은 바깥 자료를 서술에 참고합니다. 시나리오의 제작자가 허용했습니다."
          checked={draft.referencesEnabled}
          onChange={(event) => onChange({ referencesEnabled: event.target.checked })}
        />
      ) : null}
      {listing.character_modes.length > 1 ? (
        <fieldset className="choice-list">
          <legend>캐릭터를 얻는 방식(만든 뒤에 바꿀 수 없습니다)</legend>
          {listing.character_modes.map((mode) => (
            <Checkbox
              key={mode}
              label={characterModeLabel(mode)}
              checked={draft.characterModes.includes(mode)}
              onChange={(event) =>
                onChange({
                  characterModes: event.target.checked
                    ? [...draft.characterModes, mode]
                    : draft.characterModes.filter((chosen) => chosen !== mode),
                })
              }
            />
          ))}
          {hints.character_modes ? <p className="ui-field__error">{hints.character_modes}</p> : null}
        </fieldset>
      ) : null}
    </details>
  );
}
