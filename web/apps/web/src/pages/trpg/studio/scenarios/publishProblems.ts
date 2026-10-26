// web/apps/web/src/pages/trpg/studio/scenarios/publishProblems.ts
// 게시 점검(GET /scenarios/{id}/publish-check)과 게시의 409 가 주는 문제의 이름을 화면의 글과 묶음으로 바꾼다. 순수한 함수다.
// 이름은 서버의 Problem(trpg-server/app/assets/scenarios/publishing.py)이다. 모르는 이름이 오면 이름을 그대로 보인다.

import type { ScenarioTab } from './scenarioTabs';

type ProblemText = { text: string; section: ScenarioTab };

const PROBLEMS: Record<string, ProblemText> = {
  rulebook_missing: { text: '룰북을 고르지 않았습니다.', section: 'materials' },
  opening_missing: { text: '스타팅이 하나도 없습니다.', section: 'openings' },
  pregen_sheet_missing: { text: '시트가 없는 프리젠이 있습니다.', section: 'characters' },
  pregen_sheet_invalid: { text: '룰북의 규칙에 맞지 않는 프리젠의 시트가 있습니다.', section: 'characters' },
  pregens_too_few: { text: '프리젠만 고를 수 있는데 프리젠이 추천 인원의 최소보다 적습니다.', section: 'characters' },
  default_sheet_missing: { text: '직접 만든 캐릭터가 받을 기본 시트가 없습니다.', section: 'characters' },
  default_sheet_invalid: { text: '기본 시트가 룰북의 규칙에 맞지 않습니다.', section: 'characters' },
  player_made_hp_missing: { text: '능력치를 정하는 방식의 최대 HP(기준값과 상한)가 없습니다.', section: 'characters' },
  point_buy_missing: { text: '점수로 능력치를 사게 했는데 룰북에 점수제가 없습니다.', section: 'characters' },
  score_roll_missing: { text: '주사위로 점수를 정하게 했는데 룰북에 굴리는 법이 없습니다.', section: 'characters' },
  npc_sheet_entry_missing: { text: '붙인 로어북에 없는 항목의 인물 시트가 있습니다.', section: 'npcs' },
  npc_sheet_not_person: { text: '인물이 아닌 항목의 인물 시트가 있습니다.', section: 'npcs' },
  npc_sheet_invalid: { text: '룰북의 규칙에 맞지 않는 인물 시트가 있습니다.', section: 'npcs' },
  npc_attack_invalid: { text: '인물의 공격이 룰북에 없는 능력치나 난이도, 양을 씁니다.', section: 'npcs' },
  default_npc_sheet_missing: { text: '시트가 없는 인물이 있는데 기본 인물 시트가 없습니다.', section: 'npcs' },
  default_npc_sheet_invalid: { text: '기본 인물 시트가 룰북의 규칙에 맞지 않습니다.', section: 'npcs' },
  item_entry_missing: { text: '붙인 로어북에 없는 물건을 가리키는 규칙이나 소지품이 있습니다.', section: 'items' },
  item_not_item: { text: '물건이 아닌 항목을 가리키는 물건 규칙이나 소지품이 있습니다.', section: 'items' },
  item_magnitude_missing: { text: '룰북에 없는 회복이나 피해의 양을 적은 소모품이 있습니다.', section: 'items' },
  item_lock_invalid: { text: '자물쇠 물건을 따는 판정이 룰북에 없는 능력치나 난이도를 씁니다.', section: 'items' },
  item_cure_invalid: { text: '소모품이 룰북에 없는 부상이나 풀 수 없는 결손을 풉니다.', section: 'items' },
  item_injure_invalid: { text: '소모품이 룰북에 없는 부상을 입힙니다.', section: 'items' },
  item_throw_invalid: { text: '던지는 물건의 판정이 룰북에 없는 능력치나 난이도나 피해를 씁니다.', section: 'items' },
  quest_entry_missing: { text: '붙인 로어북에 없는 항목의 퀘스트가 있습니다.', section: 'quests' },
  quest_not_event: { text: '사건이 아닌 항목의 퀘스트가 있습니다.', section: 'quests' },
  quest_condition_missing: { text: '퀘스트의 조건이 가리키는 것이 없습니다.', section: 'quests' },
  quest_condition_invalid: { text: '퀘스트의 조건이 맞지 않는 종류를 가리킵니다.', section: 'quests' },
  quest_condition_impossible: { text: '이룰 수 없는 퀘스트의 조건이 있습니다.', section: 'quests' },
  quest_reveal_cycle: { text: '퀘스트가 드러나는 조건이 서로를 기다립니다.', section: 'quests' },
  currency_missing: { text: '값이나 돈을 적었는데 화폐가 없습니다.', section: 'items' },
  item_slot_invalid: { text: '룰북에 없는 장비 칸을 쓰는 물건이 있습니다.', section: 'items' },
  starting_wear_invalid: { text: '시작할 때의 착용이 맞지 않습니다.', section: 'items' },
  carried_wear_invalid: { text: '인물이나 몬스터의 착용이 맞지 않습니다.', section: 'npcs' },
  attack_weapon_invalid: { text: '인물이나 몬스터의 공격이 착용한 무기를 쓰지 않습니다.', section: 'npcs' },
  map_place_missing: { text: '붙인 로어북에 없는 장소를 가리키는 시작 장소, 길, 명소가 있습니다.', section: 'map' },
  map_not_place: { text: '장소가 아닌 항목을 가리키는 시작 장소, 길, 명소가 있습니다.', section: 'map' },
  map_start_missing: { text: '길이나 명소가 있는데 시작 장소가 없습니다.', section: 'map' },
  route_find_invalid: { text: '숨긴 길을 찾는 판정이 룰북에 없는 능력치나 난이도를 씁니다.', section: 'map' },
  route_cross_invalid: { text: '길을 넘는 판정이 룰북에 없는 능력치나 난이도, 양을 씁니다.', section: 'map' },
  route_key_repeated: { text: '열쇠 하나를 두 자물쇠(길의 자물쇠나 자물쇠 물건)에 적었습니다. 열쇠 하나는 자물쇠 하나만 엽니다.', section: 'map' },
  route_open_invalid: { text: '자물쇠를 따거나 문을 부수거나 고치는 판정이 룰북에 없는 능력치나 난이도를 씁니다.', section: 'map' },
  route_tool_missing: { text: '도구가 있어야 따거나 고치는 문이 있는데, 그 행동을 거드는 물건이 없습니다. 물건 규칙에 거드는 행동을 적어 주세요.', section: 'items' },
  place_item_off_map: { text: '맵에 없는 장소에 놓인 물건이 있습니다.', section: 'map' },
  place_item_find_invalid: { text: '숨긴 물건을 찾는 판정이 룰북에 없는 능력치나 난이도를 씁니다.', section: 'map' },
  cover_off_map: { text: '맵에 없는 장소에 커버가 있습니다.', section: 'map' },
  happening_entry_missing: { text: '붙인 로어북에 없는 항목의 사건 규칙이 있습니다.', section: 'quests' },
  happening_not_event: { text: '사건이 아닌 항목의 사건 규칙이 있습니다.', section: 'quests' },
  happening_condition_missing: { text: '사건의 조건이 가리키는 것이 없습니다.', section: 'quests' },
  happening_condition_invalid: { text: '사건의 조건이 맞지 않는 종류를 가리킵니다.', section: 'quests' },
  happening_condition_impossible: { text: '이룰 수 없는 사건의 조건이 있습니다.', section: 'quests' },
  happening_place_off_map: { text: '맵에 없는 장소로 옮기거나 그곳의 사람을 옮기는 사건이 있습니다.', section: 'quests' },
  happening_npc_not_person: { text: '인물이 아닌 것을 옮기는 사건이 있습니다.', section: 'quests' },
  happening_route_invalid: { text: '판에 없는 길이나 문이 없는 길, 그 길에 없는 장치를 다루는 사건이 있습니다.', section: 'quests' },
  npc_place_not_person: { text: '인물이 아닌 것의 자리가 있습니다.', section: 'map' },
  npc_place_off_map: { text: '맵에 없는 장소에 인물의 자리가 있습니다.', section: 'map' },
  monster_sheet_missing: { text: '붙인 몬스터 모음에 없는 몬스터의 시트가 있습니다.', section: 'monsters' },
  monster_sheet_invalid: { text: '룰북의 규칙에 맞지 않는 몬스터 시트가 있습니다.', section: 'monsters' },
  monster_attack_invalid: { text: '몬스터의 공격이 룰북에 없는 능력치나 난이도, 양을 씁니다.', section: 'monsters' },
  natural_armor_invalid: { text: '몬스터의 타고난 방어가 룰북에 없는 부위에 있습니다.', section: 'monsters' },
  unique_monster_repeated: { text: '네임드 몬스터가 두 마리 이상 놓입니다.', section: 'monsters' },
  encounter_place_missing: { text: '붙인 로어북에 없는 장소의 조우가 있습니다.', section: 'monsters' },
  encounter_not_place: { text: '장소가 아닌 항목의 조우가 있습니다.', section: 'monsters' },
  encounter_monster_missing: { text: '시트가 없는 몬스터의 조우가 있습니다.', section: 'monsters' },
  encounter_map_missing: { text: '조우가 있는데 시작 장소가 없습니다.', section: 'monsters' },
  wander_off_map: { text: '맵에 없는 장소의 무작위 조우 표가 있거나, 맵이 없는데 무작위 조우 표가 있습니다.', section: 'monsters' },
  wander_monster_missing: { text: '시트가 없는 몬스터를 적은 무작위 조우 표가 있습니다.', section: 'monsters' },
};

/** 문제 하나의 글과 묶음. 모르는 이름이면 이름 그대로, 묶음은 없다 */
export function problemLine(name: string): { text: string; section: ScenarioTab | null } {
  return PROBLEMS[name] ?? { text: name, section: null };
}

