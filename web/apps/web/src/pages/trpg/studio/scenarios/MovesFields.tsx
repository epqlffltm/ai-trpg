// web/apps/web/src/pages/trpg/studio/scenarios/MovesFields.tsx
// 몬스터 시트의 사냥과 배회(#254) 칸. 사냥의 칸 수, 배회의 확률과 처음 자리에서 벗어나는 칸 수다. 비우면 자리를 지킨다.
// 입력의 검사와 보낼 모양은 monsterMovesForm.ts 가 한다. 순찰 경로는 조우에 적는다(EncountersSection).

import { TextField } from '@ai-trpg/ui';
import { ROAM_MAX_CHANCE, ROAM_MAX_REACH, type MovesDraft, type MovesHints } from './monsterMovesForm';

type Props = {
  draft: MovesDraft;
  hints: MovesHints;
  onChange: (next: MovesDraft) => void;
};

export function MovesFields({ draft, hints, onChange }: Props) {
  return (
    <fieldset className="scenario-choices">
      <legend>싸우지 않을 때의 움직임(선택)</legend>
      <p className="ui-field__hint">
        캐릭터와 같은 곳에 없을 때 라운드마다 길 한 칸씩 움직입니다. 사냥이 먼저이고, 그다음 조우의 순찰 경로, 그다음 배회입니다. 캐릭터가 있는 곳에 들어온
        라운드에는 치지 않습니다.
      </p>
      <div className="ability-grid">
        <TextField
          label={`사냥하는 거리(1~${ROAM_MAX_REACH}칸)`}
          inputMode="numeric"
          value={draft.hunts}
          onChange={(event) => onChange({ ...draft, hunts: event.target.value })}
          error={hints.hunts}
        />
        <TextField
          label={`배회하는 확률 %(1~${ROAM_MAX_CHANCE})`}
          inputMode="numeric"
          value={draft.chance}
          onChange={(event) => onChange({ ...draft, chance: event.target.value })}
          error={hints.chance}
        />
        <TextField
          label={`배회하는 거리(처음 자리에서 1~${ROAM_MAX_REACH}칸)`}
          inputMode="numeric"
          value={draft.reach}
          onChange={(event) => onChange({ ...draft, reach: event.target.value })}
          error={hints.reach}
        />
      </div>
    </fieldset>
  );
}
