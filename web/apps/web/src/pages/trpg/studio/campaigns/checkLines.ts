// web/apps/web/src/pages/trpg/studio/campaigns/checkLines.ts
// 캠페인의 게시 점검(GET /campaigns/{id}/publish-check)과 게시의 409 가 주는 이름을 화면의 글로 바꾼다. 순수한 함수다.
// 이름은 서버의 것(trpg-server/app/assets/campaigns/publishing.py)이다. 모르는 이름이 오면 이름을 그대로 보인다.

const PROBLEMS: Record<string, string> = {
  episodes_too_few: '편이 둘 이상 있어야 합니다.',
  episode_scenario_missing: '지워진 시나리오의 편이 있습니다. 그 편을 빼 주세요.',
  episode_unpublished: '게시한 판이 없는 시나리오의 편이 있습니다. 그 시나리오를 먼저 게시해 주세요.',
  rulebook_mismatch: '편들의 시나리오가 같은 룰북의 같은 규칙을 쓰지 않습니다. 시나리오마다 마지막 판의 룰북을 맞춰 주세요.',
  campaign_quest_missing: '앞 편의 판에 없는 퀘스트를 보는 조건이 있습니다. 첫 편은 앞 편을 볼 수 없습니다.',
};

const WARNINGS: Record<string, string> = {
  progression_missing: '룰북에 성장이 없어 경험치와 레벨이 다음 편으로 옮겨지지 않습니다.',
  items_not_carried: '뒤의 편들의 판 어디에도 없는 물건이 있습니다. 그 물건은 다음 편으로 옮겨지지 않습니다.',
};

/** 게시를 막는 것 하나의 글 */
export function problemText(name: string): string {
  return PROBLEMS[name] ?? name;
}

/** 게시를 막지 않는 알림 하나의 글 */
export function warningText(name: string): string {
  return WARNINGS[name] ?? name;
}
