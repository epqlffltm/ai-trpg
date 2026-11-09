// web/apps/web/src/pages/trpg/studio/scenarios/DefendsFields.tsx
// 몬스터와 인물 시트의 방어하는 때(#254) 칸. HP 의 문턱(%)과 라운드마다의 확률(%)이다. 둘 다 비우면 방어하지 않는다.
// 입력의 검사와 보낼 모양은 defendsForm.ts 가 한다.

import { TextField } from '@ai-trpg/ui';
import type { DefendsDraft, DefendsHints } from './defendsForm';

type Props = {
  draft: DefendsDraft;
  hints: DefendsHints;
  onChange: (next: DefendsDraft) => void;
};

export function DefendsFields({ draft, hints, onChange }: Props) {
  return (
    <fieldset className="scenario-choices">
      <legend>방어하는 때(선택)</legend>
      <p className="ui-field__hint">
        방어 태세인 라운드에는 치지 않고, 그를 노린 공격이 불리합니다. HP 의 문턱에 닿으면 늘 방어하고, 아니면 라운드마다 확률로 방어합니다. 둘 다 비우면
        방어하지 않습니다.
      </p>
      <div className="ability-grid">
        <TextField
          label="HP 가 최대의 몇 % 이하일 때(1~99)"
          inputMode="numeric"
          value={draft.below}
          onChange={(event) => onChange({ ...draft, below: event.target.value })}
          error={hints.below}
        />
        <TextField
          label="라운드마다의 확률 %(1~100)"
          inputMode="numeric"
          value={draft.chance}
          onChange={(event) => onChange({ ...draft, chance: event.target.value })}
          error={hints.chance}
        />
      </div>
    </fieldset>
  );
}
