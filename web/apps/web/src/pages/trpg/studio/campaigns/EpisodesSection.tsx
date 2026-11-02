// web/apps/web/src/pages/trpg/studio/campaigns/EpisodesSection.tsx
// 캠페인의 편(#481 B). 내 시나리오를 골라 마지막 편으로 더하고, 차례를 옮기고, 빼고, 편의 이름을 정한 뒤 한 번에 저장한다.
// 저장은 편의 목록을 통째로 보낸다(PATCH episodes). 저장하기 전의 고침은 게시에 들어가지 않는다.
// 편마다 그 시나리오를 게시한 마지막 판을 보인다. 게시한 판이 없으면 캠페인을 게시하지 못한다(게시 점검이 알린다).
// 저장하면 받은 편으로 고치던 것을 바꾼다(막 더한 편의 게시한 판을 그때 안다). 제목만 저장해도 고치던 편은 그대로다.

import { Button, Notice, SelectField, TextField } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import type { CampaignDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { choicesQuery } from '../scenarios/scenarioQueries';
import { useSaveEpisodes } from './useCampaignActions';
import {
  addEpisode,
  CAMPAIGN_MAX_EPISODES,
  EPISODE_TITLE_MAX,
  episodesChanged,
  episodesDraft,
  longTitles,
  moveEpisode,
  removeEpisode,
  renameEpisode,
  unusedScenarios,
  type EpisodeDraft,
} from './episodesDraft';

export function EpisodesSection({ campaign }: { campaign: CampaignDetail }) {
  const initial = episodesDraft(campaign);
  const [episodes, setEpisodes] = useState<EpisodeDraft[]>(initial);
  const [saved, setSaved] = useState(false);
  const saving = useSaveEpisodes(campaign.id);
  const changed = episodesChanged(initial, episodes);
  const tooLong = longTitles(episodes);

  function edit(next: EpisodeDraft[]) {
    setSaved(false);
    setEpisodes(next);
  }

  async function save() {
    if (!changed || tooLong.length > 0) return;
    const done = await saving.save(episodes);
    if (!done) return;
    setEpisodes(episodesDraft(done));
    setSaved(true);
  }

  return (
    <section className="page-section" aria-labelledby="campaign-episodes-heading">
      <h2 id="campaign-episodes-heading">편</h2>
      <p className="hint">
        편의 차례대로 플레이합니다. 앞 편을 끝낸 사람들이 그 캐릭터를 데리고 다음 편으로 갑니다. {CAMPAIGN_MAX_EPISODES}편까지, 같은 룰북을 쓰는
        시나리오만 묶을 수 있습니다.
      </p>
      {saved ? <Notice>편을 저장했습니다.</Notice> : null}
      <ProblemNotice problem={saving.problem} />
      {episodes.length === 0 ? <p>아직 편이 없습니다. 아래에서 시나리오를 골라 더하세요.</p> : null}
      <ol className="plain-list studio-list" aria-label="편">
        {episodes.map((episode, index) => (
          <EpisodeRow
            key={episode.scenarioId}
            episode={episode}
            index={index}
            count={episodes.length}
            tooLong={tooLong.includes(index)}
            onRename={(title) => edit(renameEpisode(episodes, index, title))}
            onMove={(delta) => edit(moveEpisode(episodes, index, delta))}
            onRemove={() => edit(removeEpisode(episodes, index))}
          />
        ))}
      </ol>
      <AddEpisode episodes={episodes} onAdd={edit} />
      <div className="form-actions">
        <Button busy={saving.busy} disabled={!changed || tooLong.length > 0} onClick={() => void save()}>
          편 저장
        </Button>
        {changed ? <span className="hint">저장하지 않은 고침이 있습니다.</span> : null}
      </div>
    </section>
  );
}

type RowProps = {
  episode: EpisodeDraft;
  index: number;
  count: number;
  tooLong: boolean;
  onRename: (title: string) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
};

function EpisodeRow({ episode, index, count, tooLong, onRename, onMove, onRemove }: RowProps) {
  const name = `${index + 1}편`;
  return (
    <li className="studio-list__item studio-item">
      <div>
        <strong>{name}</strong> {episode.scenarioTitle} <span className="hint">{versionText(episode.lastVersion)}</span>
        <TextField
          label={`${name}의 이름(선택)`}
          value={episode.title}
          placeholder={episode.scenarioTitle}
          onChange={(event) => onRename(event.target.value)}
          error={tooLong ? `편의 이름은 ${EPISODE_TITLE_MAX}자까지입니다.` : undefined}
        />
      </div>
      <div>
        <Button variant="quiet" aria-label={`${name} 앞으로`} disabled={index === 0} onClick={() => onMove(-1)}>
          앞으로
        </Button>
        <Button variant="quiet" aria-label={`${name} 뒤로`} disabled={index === count - 1} onClick={() => onMove(1)}>
          뒤로
        </Button>
        <Button variant="quiet" aria-label={`${name} 빼기`} onClick={onRemove}>
          빼기
        </Button>
      </div>
    </li>
  );
}

/** 편의 시나리오를 게시한 마지막 판. 막 더한 편은 저장해야 안다 */
function versionText(lastVersion: number | null | undefined): string {
  if (lastVersion === undefined) return '저장하면 게시한 판을 확인합니다.';
  return lastVersion === null ? '게시한 판이 없습니다.' : `${lastVersion}판까지 게시했습니다.`;
}

function AddEpisode({ episodes, onAdd }: { episodes: EpisodeDraft[]; onAdd: (next: EpisodeDraft[]) => void }) {
  const scenarios = useQuery(choicesQuery('scenarios'));
  const [chosen, setChosen] = useState('');
  const left = unusedScenarios(scenarios.data?.items ?? [], episodes);
  const full = episodes.length >= CAMPAIGN_MAX_EPISODES;
  const picked = left.find((scenario) => scenario.id === chosen);

  function add() {
    if (!picked) return;
    onAdd(addEpisode(episodes, picked));
    setChosen('');
  }

  if (scenarios.isPending) return <p aria-busy="true">내 시나리오를 불러오는 중</p>;
  if (scenarios.isError) {
    return (
      <Notice tone="error">
        내 시나리오를 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void scenarios.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  if (full) return <p className="hint">편은 {CAMPAIGN_MAX_EPISODES}편까지입니다.</p>;
  if (left.length === 0) return <p className="hint">더할 수 있는 내 시나리오가 없습니다.</p>;
  return (
    <div className="form-actions">
      <SelectField label="더할 시나리오" value={chosen} onChange={(event) => setChosen(event.target.value)}>
        <option value="">고르기</option>
        {left.map((scenario) => (
          <option key={scenario.id} value={scenario.id}>
            {scenario.title}
          </option>
        ))}
      </SelectField>
      <Button variant="secondary" disabled={!picked} onClick={add}>
        편 더하기
      </Button>
    </div>
  );
}
