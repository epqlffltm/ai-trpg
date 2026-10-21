# trpg-server/tests/test_ci_groups.py

"""
CI 가 테스트를 나눠 돌리는 묶음(scripts/ci_groups.py)을 검사한다. DB 를 쓰지 않는다.

묶음이 틀리면 어떤 테스트가 CI 에서 두 번 돌거나, 더 나쁘게는 한 번도 돌지 않는다.
"""

import json

import pytest

from scripts.ci_groups import CATCH_ALL, GROUPS, TESTS_DIR, files_in, group_of, list_test_files, run

ALL_FILES = list_test_files(TESTS_DIR)


def test_every_test_file_is_in_exactly_one_group():
    placed = [name for group in GROUPS for name in files_in(group, ALL_FILES)]

    assert sorted(placed) == ALL_FILES


def test_this_file_is_collected_too():
    assert 'test_ci_groups.py' in ALL_FILES


@pytest.mark.parametrize('group', [group for group in GROUPS if group != CATCH_ALL])
def test_named_groups_are_not_empty(group):
    assert files_in(group, ALL_FILES)


@pytest.mark.parametrize(('group', 'head'), [(group, head) for group, heads in GROUPS.items() for head in heads])
def test_every_head_matches_a_file_in_its_group(group, head):
    # 파일의 이름을 바꾸고 머리를 고치지 않으면, 그 파일이 엉뚱한 묶음으로 옮겨 간다. 쓰이지 않는 머리로 알아챈다
    matched = [name for name in files_in(group, ALL_FILES) if name.removeprefix('test_').startswith(head)]

    assert matched, f'{group} 의 머리 {head!r} 에 맞는 파일이 없다'


@pytest.mark.parametrize(
    ('file_name', 'group'),
    [
        ('test_scenario_map.py', 'assets'),
        ('test_rounds_api.py', 'rounds'),
        ('test_treatment.py', 'engine'),
        ('test_narration_billing.py', 'models'),
        ('test_monster_turns.py', 'adventure'),
        ('test_embedder.py', 'models'),
        ('test_lore_retrieval.py', 'narration'),
        ('test_stream_api.py', 'realtime'),
        ('test_table_map.py', 'tables'),
        ('test_health.py', CATCH_ALL),
    ],
)
def test_files_land_in_the_related_group(file_name, group):
    assert group_of(file_name) == group


def test_unmatched_files_go_to_the_catch_all_group():
    assert group_of('test_brand_new_feature.py') == CATCH_ALL


def test_list_prints_group_names():
    assert run(['list'], ALL_FILES).splitlines() == list(GROUPS)


def test_json_prints_group_names_for_the_matrix():
    assert json.loads(run(['json'], ALL_FILES)) == list(GROUPS)


def test_files_prints_paths_for_pytest():
    printed = run(['files', 'rounds'], ['test_rounds_api.py', 'test_health.py', 'test_round_checks.py'])

    assert printed.split() == [str(TESTS_DIR / 'test_round_checks.py'), str(TESTS_DIR / 'test_rounds_api.py')]


def test_summary_counts_files_per_group():
    printed = run(['summary'], ['test_rounds_api.py', 'test_health.py'])

    assert 'rounds: 1' in printed
    assert f'{CATCH_ALL}: 1' in printed


@pytest.mark.parametrize('argv', [[], ['files'], ['files', 'nope'], ['shuffle']])
def test_unknown_command_or_group_is_an_error(argv):
    with pytest.raises(ValueError):
        run(argv, ALL_FILES)
