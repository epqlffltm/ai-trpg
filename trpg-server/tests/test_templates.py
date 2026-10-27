# trpg-server/tests/test_templates.py

"""
템플릿(app/engine/templates/, #615)을 검증한다. DB 도 HTTP 도 쓰지 않는다.

보는 것.
  - 고를 수 있는 템플릿마다 파일이 있고, 규칙의 모양으로 읽힌다. 틀린 파일은 읽지 않는다.
  - 이미 내놓은 템플릿의 값은 그대로다(해시). 옛 판을 읽을 때 그 값을 쓴다.
  - 템플릿마다 서술 지침(#616)이 있고, 판정 결과의 두 단계를 다 적었다. 지침은 판정을 바꾸지 않는다.
  - 템플릿마다 정해진 눈으로 판정이 성공하고, 한 눈 모자라면 실패한다. 가장 큰 눈과 가장 작은 눈도 본다.
  - 이름에 상용 룰의 이름이 없다. 공개 문서를 본떴으면 출처 표시가 있다.
"""

import hashlib
import json
from pathlib import Path

import pytest

from app.assets.scenarios.upgrades import UPGRADES, upgrade_from_44
from app.engine import templates
from app.engine.check import find_difficulty, modifier_of, resolve
from app.engine.dice import ScriptedDice
from app.engine.ruleset import ArmorMode, Outcome, Ruleset
from app.engine.templates import (
    FORMAT,
    SRD5,
    TEMPLATES,
    Template,
    TemplateFile,
    TemplateFileError,
    file_problem,
    read_template,
)

# 내놓은 템플릿의 규칙의 해시. 값을 고치면 이 테스트가 깨진다.
# 이미 내놓은 템플릿의 값은 고치지 않는다. 고치고 싶으면 새 이름으로 하나 더 낸다.
# 규칙의 모양에 칸이 새로 생겨 템플릿에 그 칸을 더한 것이면(있던 값은 그대로) 해시를 새로 적는다.
RELEASED = {
    Template.SRD5: 'f6774238641d3de8e62317632af007adfbf62042bbf6a2df165d7a79fdb30e82',
    Template.HORROR: '7a0782646dbededdc2b9e8d642f2d7ae8023e9aaac0a21ba9109648bc37b3fa5',
    Template.LIGHT: '7fbcfa9ecb20c4722f288fce8f42b769920f663ac19a7fe4b00c6abcb9fc3e19',
}
# 수치의 가진 쪽(holders, #804 ③)을 더하기 전의 해시. 그 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_HOLDERS = {
    Template.SRD5: 'f6774238641d3de8e62317632af007adfbf62042bbf6a2df165d7a79fdb30e82',
    Template.HORROR: '7a0782646dbededdc2b9e8d642f2d7ae8023e9aaac0a21ba9109648bc37b3fa5',
    Template.LIGHT: '361759bf24ba807cd9441e5d390d86c2695b47f18fcfa0ea0362fad5916e5053',
}
# 수치의 보이기(visibility, #804 ③)를 더하기 전의 해시. 그 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_VISIBILITY = {
    Template.SRD5: 'f6774238641d3de8e62317632af007adfbf62042bbf6a2df165d7a79fdb30e82',
    Template.HORROR: '7a0782646dbededdc2b9e8d642f2d7ae8023e9aaac0a21ba9109648bc37b3fa5',
    Template.LIGHT: '6a956aa64a675be7d42cc913f2f2305ebc1885dc0a899c2abac00df156b01335',
}
# 수치의 라운드마다의 변화와 문턱(each_round, at_min, at_max, #804 ②)을 더하기 전의 해시.
# 그 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_THRESHOLDS = {
    Template.SRD5: 'f6774238641d3de8e62317632af007adfbf62042bbf6a2df165d7a79fdb30e82',
    Template.HORROR: '7a0782646dbededdc2b9e8d642f2d7ae8023e9aaac0a21ba9109648bc37b3fa5',
    Template.LIGHT: '0ed777bce720e2638621a50e4c8f2ecc834dc000c40113b33ed2cf9195f7434a',
}
# HP 말고 다른 수치(resources, #804)를 더하기 전의 해시. 그 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_RESOURCES = {
    Template.SRD5: 'fb3c80d973f39c9096a6fb06c38141173a09918dbe8ae498f5b907eb3e0e51e3',
    Template.HORROR: 'd5d89b9a7d6b69758137ca7b08b503b313ddfde07846fade105fb9cd9d406d1f',
    Template.LIGHT: '085c1d6bf07627a80f55ebd68f091d933b5da8f10189538da3b90febebf82a43',
}
# 물건을 쓰는 판정(item_check, #800)을 더하기 전의 해시. 그 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_ITEM_CHECK = {
    Template.SRD5: '1dc689ffc0916445367844b4c31e6d1471da4955de74fc1c36eda73ce2b858b6',
    Template.HORROR: 'a6c09c04b3f6902fdde9de906a489c7a05906bf140fba05060d6d5c7a1f38ac2',
    Template.LIGHT: '46c656de0ab15f6de1cb637693fd90bd4bb5df2deeb28ba7d894ab9a055ce1c5',
}
# 부상의 성질(injuries[].natures, #799)을 더하기 전의 해시. 성질을 뺀 규칙은 그때와 같아야 한다
BEFORE_NATURES = {
    Template.SRD5: 'bb50911c27b1baab1fa2394345ef05fed4cf2a8b1d223d423cfbc75fcda9d4e5',
    Template.HORROR: '3ae1576364da792ef899989385b76670c5b884d58429e9fdebb2a867852169eb',
    Template.LIGHT: '46c656de0ab15f6de1cb637693fd90bd4bb5df2deeb28ba7d894ab9a055ce1c5',
}
# 세이브의 목표값과 관통의 기준값(armor.save_target, pierce_base, #276)을 더하기 전의 해시
BEFORE_SAVES = {
    Template.SRD5: '6b3781462685f0b6d2441ee9c696f8ac839dafa82fae65f1a98c72cd8f400152',
    Template.HORROR: 'ff320c47eb4e0888b2ba329ad8a40c7fefff3b9b0a9fe281a2d0b537b26232e0',
    Template.LIGHT: 'f514139c38ec21f266e4a93ddad6fd0d9c91426f206ee005907602d22c36ce2f',
}
# 방어 방식(armor)과 칸이 맞을 가중치(hit_weight, #276)를 더하기 전의 해시. 둘을 뺀 규칙은 그때와 같아야 한다
BEFORE_ARMOR = {
    Template.SRD5: '903134da06976f9fc6a761880f04ffa9ba2d61a9c2216cf8b319a96a45e9ea25',
    Template.HORROR: '03303285f8d9a686ea8040d5162d7cb3f8c021c7daf5d0fd1b65b1aef057ee55',
    Template.LIGHT: '6adbbd4747389e1d386f75bb57d2d380f0b11012e3124cae90e7379ea69c6134',
}
# 장비의 칸(equipment_slots, #276)을 더하기 전의 해시. 칸을 뺀 규칙은 그때와 같아야 한다
BEFORE_SLOTS = {
    Template.SRD5: '0a9a23ee2bf555e694a520e0f10e4e9adba23eaa57656eccda904dff045cd995',
    Template.HORROR: '72fa8e76f685929a7362ebaa9304677e9b631db949dade6d2d87a7b7fda53859',
    Template.LIGHT: 'ad2871a9fe507d18c59cfa861b94951f20123524852e8ad812ba24f81b97ba88',
}
# 서술 지침(narration, #616)을 더하기 전의 해시. 지침을 뺀 규칙은 그때와 같아야 한다
BEFORE_NARRATION = {
    Template.SRD5: '9f83745c16ede0d830b47f4a9eb65e789f61be1cd471d5d76342ce114bc96384',
    Template.HORROR: 'f01fe773025fc11769c5989e3d92bf886addbc6d470742d36578bf7820cafe33',
    Template.LIGHT: '562d3014c5dee777f7d3436319cffa81b0fe39c244be18308ee0f25bd7c9b443',
}

# 템플릿의 이름과 소개에 쓰지 않는 상용 룰의 이름
COMMERCIAL_NAMES = ('d&d', 'dungeons', '던전 앤 드래곤', '던전즈', 'pathfinder', '패스파인더', 'cthulhu', '크툴루')


def dumped(rules: Ruleset, natures: bool = True, resources: bool = False) -> dict:
    """
    규칙의 값. natures 가 거짓이면 부상의 성질(#799)과 그 뒤에 더한 물건을 쓰는 판정(item_check, #800)을 뺀다.
    성질을 더하기 전의 해시와 견줄 때 쓴다. resources 가 거짓이면 가장 나중에 더한 수치(#804)를 뺀다.
    지금의 값(RELEASED)과 견줄 때만 참으로 준다.
    """
    values = rules.model_dump(mode='json')
    if not resources:
        values.pop('resources')
    if not natures:
        values.pop('item_check')
        values['injuries'] = [
            {key: value for key, value in injury.items() if key != 'natures'} for injury in values['injuries']
        ]
    return values


def fingerprint(rules: Ruleset, without: tuple[str, ...] = (), natures: bool = True, resources: bool = False) -> str:
    """규칙의 값을 정해진 차례의 JSON 으로 적어 해시를 낸다. without 의 칸은 빼고 낸다."""
    values = {key: value for key, value in dumped(rules, natures, resources).items() if key not in without}
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def fingerprint_without_resource_fields(rules: Ruleset, new_fields: tuple[str, ...]) -> str:
    """수치마다 new_fields 의 칸을 뺀 규칙의 해시. 수치에 칸을 더하기 전의 해시와 견줄 때 쓴다."""
    values = dumped(rules, resources=True)
    values['resources'] = [
        {key: value for key, value in resource.items() if key not in new_fields} for resource in values['resources']
    ]
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def fingerprint_before_armor(rules: Ruleset) -> str:
    """방어 방식과 칸의 가중치(#276)를 뺀 규칙의 해시."""
    values = {key: value for key, value in dumped(rules, natures=False).items() if key != 'armor'}
    values['equipment_slots'] = [
        {key: value for key, value in slot.items() if key != 'hit_weight'} for slot in values['equipment_slots']
    ]
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def fingerprint_before_saves(rules: Ruleset) -> str:
    """방어 규칙에서 세이브의 목표값과 관통의 기준값(#276)을 뺀 규칙의 해시."""
    values = dumped(rules, natures=False)
    values['armor'] = {'mode': values['armor']['mode']}
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def middle_score(rules: Ruleset) -> int:
    """점수의 범위 가운데의 점수."""
    return (rules.score_min + rules.score_max) // 2


# --- 파일 ---


def test_every_template_has_a_file_that_reads_as_rules():
    assert set(TEMPLATES) == set(Template)
    for template, loaded in TEMPLATES.items():
        assert loaded.key == template.value
        assert loaded.rules.template == template.value


def test_every_file_in_the_folder_is_a_template():
    """폴더에 고를 수 없는 파일이 남아 있지 않다. Template 에서 빠진 템플릿은 파일도 지운다."""
    files = {path.stem for path in templates.TEMPLATES_DIR.glob('*.json')}

    assert files == {template.value for template in Template}


def test_released_templates_keep_their_values():
    assert set(RELEASED) == set(Template), '새 템플릿을 내면 RELEASED 에 그 해시를 적는다'
    for template, expected in RELEASED.items():
        assert fingerprint(TEMPLATES[template].rules, resources=True) == expected, (
            f'{template.value} 의 값이 바뀌었다. 이미 내놓은 템플릿의 값은 고치지 않는다. 새 이름으로 하나 더 낸다'
        )


def test_adding_the_holders_kept_the_other_values():
    for template, expected in BEFORE_HOLDERS.items():
        assert fingerprint_without_resource_fields(TEMPLATES[template].rules, ('holders',)) == expected


def test_adding_the_visibility_kept_the_other_values():
    for template, expected in BEFORE_VISIBILITY.items():
        assert fingerprint_without_resource_fields(TEMPLATES[template].rules, ('visibility', 'holders')) == expected


def test_adding_the_thresholds_kept_the_other_values():
    fields = ('each_round', 'at_min', 'at_max', 'visibility', 'holders')
    for template, expected in BEFORE_THRESHOLDS.items():
        assert fingerprint_without_resource_fields(TEMPLATES[template].rules, fields) == expected


def test_adding_the_resources_kept_the_other_values():
    for template, expected in BEFORE_RESOURCES.items():
        assert fingerprint(TEMPLATES[template].rules) == expected


def test_adding_the_narration_guide_kept_the_other_values():
    for template, expected in BEFORE_NARRATION.items():
        rules = TEMPLATES[template].rules
        assert fingerprint(rules, without=('narration', 'equipment_slots', 'armor'), natures=False) == expected


def test_adding_the_equipment_slots_kept_the_other_values():
    for template, expected in BEFORE_SLOTS.items():
        assert fingerprint(TEMPLATES[template].rules, without=('equipment_slots', 'armor'), natures=False) == expected


def test_adding_the_item_check_kept_the_other_values():
    for template, expected in BEFORE_ITEM_CHECK.items():
        assert fingerprint(TEMPLATES[template].rules, without=('item_check',)) == expected


def test_adding_the_natures_kept_the_other_values():
    for template, expected in BEFORE_NATURES.items():
        assert fingerprint(TEMPLATES[template].rules, natures=False) == expected


def test_adding_the_saves_kept_the_other_values():
    for template, expected in BEFORE_SAVES.items():
        assert fingerprint_before_saves(TEMPLATES[template].rules) == expected


def test_no_template_saves_and_all_pierce_from_ten():
    """템플릿은 세이브 방식을 쓰지 않는다. 세이브는 룰북에서 고른다. 관통의 기준값은 10 이다(#276)."""
    for template in Template:
        armor = TEMPLATES[template].rules.armor
        assert (armor.save_target, armor.pierce_base) == (None, 10)


def test_adding_the_armor_kept_the_other_values():
    for template, expected in BEFORE_ARMOR.items():
        assert fingerprint_before_armor(TEMPLATES[template].rules) == expected


@pytest.mark.parametrize(
    ('template', 'mode'),
    [(Template.SRD5, ArmorMode.AC), (Template.HORROR, ArmorMode.REDUCE), (Template.LIGHT, ArmorMode.REDUCE)],
)
def test_every_template_blocks_with_its_armor(template: Template, mode: ArmorMode):
    """srd5 는 맞히기 어렵게(ac), horror 와 light 는 피해를 깎는다(reduce). 몸이 가장 잘 맞는다(#276)."""
    rules = TEMPLATES[template].rules
    weights = {slot.key: slot.hit_weight for slot in rules.equipment_slots}

    assert rules.armor.mode == mode
    assert weights['body'] == max(weights.values())


@pytest.mark.parametrize('template', list(Template))
def test_every_template_has_hands_and_a_body(template: Template):
    """모든 템플릿에 무기를 쥘 두 손과 갑옷을 입을 몸이 있다(#276)."""
    keys = [slot.key for slot in TEMPLATES[template].rules.equipment_slots]

    assert keys[:3] == ['main_hand', 'off_hand', 'body']


def test_the_old_srd5_name_still_points_to_the_file():
    """옛 판을 올려 읽을 때 쓰는 SRD5 는 파일의 srd5 다."""
    assert SRD5 is TEMPLATES[Template.SRD5].rules


def with_changes(template: Template, **changes) -> TemplateFile:
    """그 템플릿의 파일에서 몇 칸만 바꾼 것."""
    return TEMPLATES[template].model_copy(update=changes)


@pytest.mark.parametrize(
    ('changes', 'problem'),
    [
        ({'format': FORMAT + 1}, '판이'),
        ({'key': 'horror'}, 'key 가'),
        ({'rules': TEMPLATES[Template.HORROR].rules}, '규칙의 template 이'),
    ],
)
def test_a_file_that_is_not_its_template_is_named(changes: dict, problem: str):
    found = file_problem(Template.SRD5, with_changes(Template.SRD5, **changes))

    assert found is not None and found.startswith(problem)


def test_a_matching_file_has_no_problem():
    assert file_problem(Template.LIGHT, TEMPLATES[Template.LIGHT]) is None


def write_srd5(folder: Path, document: dict) -> None:
    (folder / 'srd5.json').write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')


def srd5_document() -> dict:
    return json.loads(templates.template_path(Template.SRD5).read_text(encoding='utf-8'))


@pytest.mark.parametrize(
    'broken',
    [
        # 칸을 빠뜨리면 "없음"으로 읽지 않는다
        lambda document: document['rules'].pop('death_save'),
        lambda document: document['rules'].update(die=1),
        lambda document: document.update(format=FORMAT + 1),
        lambda document: document.update(extra='모르는 칸'),
    ],
)
def test_a_broken_file_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken):
    document = srd5_document()
    broken(document)
    write_srd5(tmp_path, document)
    monkeypatch.setattr(templates, 'TEMPLATES_DIR', tmp_path)

    with pytest.raises(TemplateFileError, match='srd5.json'):
        read_template(Template.SRD5)


def test_a_file_that_is_not_json_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / 'srd5.json').write_text('{"format": 1,', encoding='utf-8')
    monkeypatch.setattr(templates, 'TEMPLATES_DIR', tmp_path)

    with pytest.raises(TemplateFileError, match='srd5.json'):
        read_template(Template.SRD5)


def test_a_missing_file_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(templates, 'TEMPLATES_DIR', tmp_path)

    with pytest.raises(TemplateFileError, match='srd5.json'):
        read_template(Template.SRD5)


# --- 이름과 출처 ---


@pytest.mark.parametrize('template', list(Template))
def test_no_commercial_rule_name_is_used(template: Template):
    loaded = TEMPLATES[template]
    shown = f'{loaded.name} {loaded.summary}'.lower()

    assert not [name for name in COMMERCIAL_NAMES if name in shown]


@pytest.mark.parametrize('template', list(Template))
def test_a_template_that_borrows_from_the_srd_carries_its_attribution(template: Template):
    loaded = TEMPLATES[template]
    borrowed = any('SRD' in note for note in loaded.notes)
    attributed = any('Creative Commons Attribution 4.0' in line for line in loaded.attribution)

    # 본뜬 것이 있으면 출처 표시가 있다. 본뜬 것이 없는 템플릿(가벼운 모험)은 출처 표시가 없어도 된다
    assert attributed or not borrowed


# --- 템플릿마다 판정 ---


@pytest.mark.parametrize('template', list(Template))
def test_exactly_the_target_succeeds_and_one_short_fails(template: Template):
    rules = TEMPLATES[template].rules
    difficulty = find_difficulty(rules, None)
    score = middle_score(rules)
    needed = difficulty.target - modifier_of(rules, score)
    assert 1 < needed <= rules.die, '가운데 점수로 기본 난이도에 주사위로 닿을 수 있어야 한다'

    hit = resolve(rules, score, difficulty, ScriptedDice([needed]))
    miss = resolve(rules, score, difficulty, ScriptedDice([needed - 1]))

    assert (hit.total, hit.target, hit.success) == (difficulty.target, difficulty.target, True)
    assert (miss.total, miss.success) == (difficulty.target - 1, False)


@pytest.mark.parametrize('template', list(Template))
def test_the_easiest_and_hardest_rolls_at_the_edges_of_the_die(template: Template):
    """가장 쉬운 난이도는 가장 큰 눈이면 가운데 점수로도 성공하고, 가장 작은 눈이면 가장 낮은 점수로 실패한다."""
    rules = TEMPLATES[template].rules
    easiest = min(rules.difficulties, key=lambda difficulty: difficulty.target)

    best = resolve(rules, middle_score(rules), easiest, ScriptedDice([rules.die]))
    worst = resolve(rules, rules.score_min, easiest, ScriptedDice([1]))

    assert best.success
    assert not worst.success


def test_light_counts_the_score_itself_as_the_modifier():
    """가벼운 모험은 점수가 곧 보정이다. 재치 3 으로 보통(8)에 도전해 눈 5 면 5 + 3 = 8 로 성공이다."""
    rules = TEMPLATES[Template.LIGHT].rules

    check = resolve(rules, 3, find_difficulty(rules, 'medium'), ScriptedDice([5]))

    assert (check.roll, check.modifier, check.total, check.target, check.success) == (5, 3, 8, 8, True)


def test_horror_is_harder_to_survive_than_srd5():
    """공포는 SRD5 보다 죽음의 굴림의 목표가 높고 실패를 덜 견딘다."""
    horror = TEMPLATES[Template.HORROR].rules

    assert horror.death_save.target > SRD5.death_save.target
    assert horror.death_save.failures < SRD5.death_save.failures


def test_light_never_kills_by_the_dice():
    """가벼운 모험에는 죽음의 굴림과 부상이 없다. 쓰러져도 쉬면 일어난다."""
    light = TEMPLATES[Template.LIGHT].rules

    assert light.death_save is None
    assert light.injuries == () and light.injury_table is None
    assert light.rest.revive is not None


# --- 서술 지침(#616) ---


@pytest.mark.parametrize('template', list(Template))
def test_every_template_guides_both_outcomes(template: Template):
    guide = TEMPLATES[template].rules.narration

    assert guide is not None
    assert {item.outcome for item in guide.outcomes} == set(Outcome)


def test_the_guides_differ_between_templates():
    tones = {TEMPLATES[template].rules.narration.tone for template in Template}

    assert len(tones) == len(Template)


@pytest.mark.parametrize('template', list(Template))
def test_the_guide_does_not_change_the_check(template: Template):
    """서술 지침을 지워도 같은 눈이면 같은 판정이다. 엔진은 지침을 보지 않는다."""
    rules = TEMPLATES[template].rules
    plain = rules.model_copy(update={'narration': None})
    difficulty = find_difficulty(rules, None)
    score = middle_score(rules)

    assert resolve(rules, score, difficulty, ScriptedDice([3])) == resolve(plain, score, difficulty, ScriptedDice([3]))


def test_an_old_snapshot_reads_as_no_narration_guide():
    """형식 44 의 판은 지침이 없는 것으로 읽는다. SRD5 의 판타지 분위기를 옛 판에 얹지 않는다."""
    rules = SRD5.model_dump(mode='json')
    rules.pop('narration')
    document = {'format': 44, 'rulebook': {'id': 'r', 'title': '룰북', 'gm_guide': '', 'rules': rules}}

    upgraded = upgrade_from_44(document)

    assert upgraded['format'] == 45
    assert upgraded['rulebook']['rules'] == {**rules, 'narration': None}
    assert 'narration' not in document['rulebook']['rules']
    assert UPGRADES[44] is upgrade_from_44
