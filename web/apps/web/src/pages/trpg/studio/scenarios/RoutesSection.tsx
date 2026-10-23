// web/apps/web/src/pages/trpg/studio/scenarios/RoutesSection.tsx
// 지도 탭의 길(B9). 길마다 한 줄("수도원 문 ↔ 종탑 · 끝에 서 보면 앎 · 30분"), 더하기와 고치기는 창에서, 지우기는 한 번 더 묻는다.
// 창의 저장이 길 목록을 통째로 바로 보낸다. 길의 문(넘기, 자물쇠, 빗장, 부수기)은 다음 화면이 고치고 여기서는 그대로 둔다.

import { Button, Checkbox, Dialog, SelectField, TextField } from '@ai-trpg/ui';
import { useCallback, useState, type FormEvent } from 'react';
import type { RouteVisibility, Ruleset, ScenarioDetail } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { MAX_ROUTES, routeDraft, routeHints, routeLine, toRoute, VISIBILITY_VALUES, visibilityLabel, withoutRoute, withRoute, type RouteDraft } from './routesForm';
import type { EntryChoice } from './useLoreEntries';
import { useScenarioSave } from './useScenarioSave';

type Props = { scenario: ScenarioDetail; rules: Ruleset | null; places: EntryChoice[]; nameOf: (placeId: string) => string };

export function RoutesSection({ scenario, rules, places, nameOf }: Props) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const close = useCallback(() => setEditing(null), []);
  const removing = useScenarioSave(scenario.id);
  const routes = scenario.routes;
  return (
    <section className="page-section" aria-labelledby="routes-heading">
      <h2 id="routes-heading">
        길{' '}
        <span className="hint">
          ({routes.length} / {MAX_ROUTES})
        </span>
      </h2>
      <p className="hint">장소 둘을 잇습니다. 창에서 저장하면 바로 저장됩니다. 넘기·자물쇠·빗장 같은 길의 문은 다음에 더하는 화면에서 고칩니다.</p>
      <p>
        <Button variant="secondary" disabled={routes.length >= MAX_ROUTES || places.length < 2} onClick={() => setEditing('new')}>
          길 더하기
        </Button>
      </p>
      {routes.length === 0 ? <p className="hint">아직 길이 없습니다.</p> : null}
      <ul className="plain-list studio-list" aria-label="길">
        {routes.map((route, at) => {
          const name = `${nameOf(route.from_place)}–${nameOf(route.to_place)}`;
          return (
            <li key={`${route.from_place}:${route.to_place}`} className="studio-list__item studio-item">
              <div className="studio-list__description">{routeLine(route, nameOf, rules)}</div>
              <span className="action-chips">
                <Button variant="quiet" aria-label={`${name} 길 고치기`} onClick={() => setEditing(at)}>
                  고치기
                </Button>
                <ConfirmButton
                  label="지우기"
                  ariaLabel={`${name} 길 지우기`}
                  title="길 지우기"
                  confirm="지우기"
                  busy={removing.busy}
                  problem={removing.problem}
                  onConfirm={async () => (await removing.save({ routes: withoutRoute(routes, at) })) !== null}
                >
                  <p>{routeLine(route, nameOf, rules)}</p>
                  <p>길의 문(자물쇠, 빗장)도 함께 지워집니다. 이 길로만 이어진 장소는 맵에서 빠질 수 있습니다.</p>
                </ConfirmButton>
              </span>
            </li>
          );
        })}
      </ul>
      <Dialog title={editing === 'new' ? '길 더하기' : '길 고치기'} open={editing !== null} onClose={close}>
        {editing !== null ? <RouteForm scenario={scenario} rules={rules} places={places} at={editing === 'new' ? null : editing} done={close} /> : null}
      </Dialog>
    </section>
  );
}

type FormProps = { scenario: ScenarioDetail; rules: Ruleset | null; places: EntryChoice[]; at: number | null; done: () => void };

function RouteForm({ scenario, rules, places, at, done }: FormProps) {
  const original = at === null ? null : (scenario.routes[at] ?? null);
  const [draft, setDraft] = useState<RouteDraft>(() => routeDraft(original));
  const saving = useScenarioSave(scenario.id);
  const hints = routeHints(draft, scenario.routes, at);
  const blocked = Object.keys(hints).length > 0;

  function update(changes: Partial<RouteDraft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) return;
    if (await saving.save({ routes: withRoute(scenario.routes, at, toRoute(draft, original)) })) done();
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate aria-label="길">
      <ProblemNotice problem={saving.problem} />
      <div className="scenario-players__row">
        <PlaceSelect label="한쪽 끝" value={draft.from} places={places} onChange={(from) => update({ from })} />
        <PlaceSelect label="다른 끝" value={draft.to} places={places} onChange={(to) => update({ to })} />
      </div>
      {hints.ends ? <p className="ui-field__error">{hints.ends}</p> : null}
      <Checkbox
        label="양쪽으로 다닌다"
        description="끄면 한쪽 끝에서 다른 끝으로만 갑니다(떨어지는 구멍, 한쪽에서만 열리는 문)."
        checked={draft.twoWay}
        onChange={(event) => update({ twoWay: event.target.checked })}
      />
      <SelectField label="언제 아는가" value={draft.visibility} onChange={(event) => update({ visibility: event.target.value as RouteVisibility })}>
        {VISIBILITY_VALUES.map((visibility) => (
          <option key={visibility} value={visibility}>
            {visibilityLabel(visibility)}
          </option>
        ))}
      </SelectField>
      {draft.visibility === 'hidden' ? <FindFields draft={draft} rules={rules} hint={hints.find} update={update} /> : null}
      <TextField
        label="걸리는 시간(분, 선택)"
        inputMode="numeric"
        value={draft.minutes}
        onChange={(event) => update({ minutes: event.target.value })}
        error={hints.minutes}
      />
      <p className="ui-field__hint">비우면 옆방처럼 라운드의 걸음 안에 갑니다. 적으면 이 길로 간 다음 라운드에 그만큼 시간이 흐릅니다.</p>
      <div className="actions">
        <Button type="submit" busy={saving.busy} disabled={blocked}>
          {at === null ? '더하기' : '저장'}
        </Button>
      </div>
    </form>
  );
}

function PlaceSelect({ label, value, places, onChange }: { label: string; value: string; places: EntryChoice[]; onChange: (id: string) => void }) {
  return (
    <SelectField label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      {value === '' ? <option value="">고르기</option> : null}
      {value !== '' && !places.some((place) => place.id === value) ? <option value={value}>(붙인 로어북에 없는 장소)</option> : null}
      {places.map((place) => (
        <option key={place.id} value={place.id}>
          {place.name}
        </option>
      ))}
    </SelectField>
  );
}

type FindProps = { draft: RouteDraft; rules: Ruleset | null; hint: string | undefined; update: (changes: Partial<RouteDraft>) => void };

function FindFields({ draft, rules, hint, update }: FindProps) {
  if (!rules) return <p className="ui-field__error">숨긴 길의 찾는 판정은 룰북의 능력치로 정합니다. 룰북을 먼저 고르세요.</p>;
  return (
    <div className="scenario-players__row">
      <SelectField label="찾는 판정의 능력치" value={draft.findAbility} onChange={(event) => update({ findAbility: event.target.value })} error={hint}>
        <option value="">고르기</option>
        {rules.abilities.map((ability) => (
          <option key={ability.key} value={ability.key}>
            {ability.name}
          </option>
        ))}
      </SelectField>
      <SelectField label="찾는 판정의 난이도" value={draft.findDifficulty} onChange={(event) => update({ findDifficulty: event.target.value })}>
        <option value="">룰북의 기본</option>
        {rules.difficulties.map((difficulty) => (
          <option key={difficulty.key} value={difficulty.key}>
            {difficulty.name}
          </option>
        ))}
      </SelectField>
    </div>
  );
}
