# shared/reference-core/tests/test_wiki.py

"""
위키백과를 데이터 파일로 만드는 규칙을 검증한다. 네트워크를 쓰지 않는다. API 의 답은 시험 안에 적은 JSON 이다.

보는 것.
  - 거르기(wiki.py): 괄호, 각주, 좌표를 지운다.
    연도·세기·날짜와 나라·도시의 이름이 든 문장, 문서를 소개하는 문장을 뺀다.
    1,000자 안에서 문장째 담는다. 남은 문장이 없으면 None
  - 제목 목록(wiki_titles.py): 칸, 주석, 다른 이름(한국어 이름이 앞, 괄호를 뗀다, 다섯까지), 틀린 줄과 겹친 줄
  - API(wiki_api.py): 물음의 모양, 넘겨주기와 제목 고치기를 따라간다. 없는 문서, 동음이의어, 빈 도입부는 빠진다
  - 만들기(wiki_build.py): 한국어판 먼저, 없거나 남은 글이 없으면 영어판, 둘 다 없으면 알린다. 같은 문서는 앞의 것만
  - 실린 파일: 제목 목록과 이름 목록이 읽힌다
"""

import json
from pathlib import Path
from typing import Any

import pytest

from reference_core.data import WIKIPEDIA_FILE, WIKIPEDIA_PLACES_FILE, WIKIPEDIA_TITLES_FILE, WIKIPEDIA_TRANSLATION_FILE
from reference_core.records import ReferenceKind, ReferenceSource, read_document
from reference_core.translations import TranslationDocument, read_translations
from reference_core.wiki import (
    clean_text,
    kept_sentences,
    lead_content,
    places_pattern,
    read_places,
    within_length,
)
from reference_core.wiki_api import BATCH_SIZE, batches, pages_of, query_params, resolved_titles
from reference_core.wiki_build import BuildReport, build, collect, with_translations
from reference_core.wiki_titles import TitleLineError, WikiTitle, parse_titles, read_titles

PLACES = places_pattern(['포르투갈', '유럽', 'Portugal', 'Iran'])


# --- 거르기 ---


def test_brackets_parentheses_and_coordinates_go():
    text = '캐럭(포르투갈어: nau [나우])은 돛대가 셋인 배다.[1] 좌표 37°33′N 에 있다.'

    assert clean_text(text) == '캐럭은 돛대가 셋인 배다. 좌표 에 있다.'


def test_real_world_sentences_go():
    text = (
        '캐럭은 돛대가 셋인 큰 범선이다. 15세기에 널리 쓰였다. 포르투갈에서 만들었다.\n'
        '뱃머리와 고물에 높은 갑판이 있다. 1492년의 항해에 쓰였다. 유럽의 바다를 다녔다.'
    )

    assert kept_sentences(text, PLACES) == ['캐럭은 돛대가 셋인 큰 범선이다.', '뱃머리와 고물에 높은 갑판이 있다.']


def test_english_real_world_sentences_go():
    text = 'A carrack is a ship. It was used in the 15th century. Portugal built many. Built around 1450. It has masts.'

    assert kept_sentences(text, PLACES) == ['A carrack is a ship.', 'It has masts.']


def test_english_names_match_whole_words_only():
    assert kept_sentences('Tirana is a word here. Iran is not.', PLACES) == ['Tirana is a word here.']


def test_articles_about_themselves_go():
    assert kept_sentences('성은 다음을 가리킨다. 돌로 쌓았다.', PLACES) == ['돌로 쌓았다.']
    assert kept_sentences('Castle may refer to many things.', PLACES) == []


def test_the_content_keeps_whole_sentences_within_the_limit():
    assert within_length(['가' * 6, '나' * 3, '다'], limit=10) == '가가가가가가 나나나'
    assert within_length(['가' * 12], limit=10) == '가' * 10
    assert within_length([], limit=10) == ''


def test_nothing_left_means_no_content():
    assert lead_content('1492년에 만들었다. 포르투갈의 배다.', PLACES) is None
    assert lead_content('큰 배다.', PLACES) == '큰 배다.'


def test_an_empty_place_list_matches_nothing():
    assert kept_sentences('어디든 간다.', places_pattern([])) == ['어디든 간다.']


# --- 제목 목록 ---


def test_titles_are_read_with_comments_and_blank_fields():
    titles = parse_titles('# 탈것\n\n범선 | Sailing ship | 돛단배, 범주\n갤리온 | Galleon |\n돛\n')

    assert titles == [
        WikiTitle(ko='범선', en='Sailing ship', aliases=('돛단배', '범주')),
        WikiTitle(ko='갤리온', en='Galleon'),
        WikiTitle(ko='돛'),
    ]


def test_the_korean_name_comes_first_without_the_disambiguation():
    title = WikiTitle(ko='성 (건축)', en='Castle', aliases=('성채', '성', '가' * 31, '보루', '요새', '산성', '진'))

    assert title.korean_name == '성'
    assert title.names() == ['성', '성채', '보루', '요새', '산성']


def test_wrong_and_repeated_lines_are_refused():
    with pytest.raises(TitleLineError, match='2번째'):
        parse_titles('범선\n가 | 나 | 다 | 라')
    with pytest.raises(TitleLineError, match='겹친다'):
        parse_titles('범선\n범선 | Ship')
    with pytest.raises(TitleLineError):
        parse_titles(' | Ship')


# --- API ---


def test_the_question_asks_for_the_lead_revision_url_and_disambiguation():
    params = query_params(['범선', '갤리온'])

    assert params['titles'] == '범선|갤리온'
    assert params['prop'] == 'extracts|revisions|info|pageprops'
    assert (params['exintro'], params['explaintext'], params['redirects'], params['formatversion']) == (
        '1',
        '1',
        '1',
        '2',
    )
    assert batches([str(n) for n in range(BATCH_SIZE + 1)])[-1] == [str(BATCH_SIZE)]


def page(title: str, extract: str, page_id: int = 1, **extra: Any) -> dict[str, Any]:
    url = f'https://ko.wikipedia.org/wiki/{title}'
    return {
        'pageid': page_id,
        'title': title,
        'extract': extract,
        'revisions': [{'revid': page_id * 10}],
        'fullurl': url,
        **extra,
    }


def test_redirects_and_normalized_titles_are_followed():
    query = {
        'normalized': [{'from': 'carrack', 'to': 'Carrack'}],
        'redirects': [{'from': 'Carrack', 'to': 'Carrack (ship)'}],
    }

    assert resolved_titles(query) == {'carrack': 'Carrack (ship)', 'Carrack': 'Carrack (ship)'}


def test_missing_disambiguation_and_empty_pages_are_left_out():
    answer = {
        'query': {
            'redirects': [{'from': '돛단배', 'to': '범선'}],
            'pages': [
                page('범선', '돛으로 가는 배다.', 1),
                {'title': '없는 문서', 'missing': True},
                page('성', '성은 다음을 가리킨다.', 2, pageprops={'disambiguation': ''}),
                page('빈 문서', '  ', 3),
            ],
        }
    }

    found = pages_of('ko', ['돛단배', '없는 문서', '성', '빈 문서', '묻지 않은 것'], answer)

    assert list(found) == ['돛단배']
    assert (found['돛단배'].title, found['돛단배'].revision_id, found['돛단배'].lang) == ('범선', 10, 'ko')


# --- 만들기 ---


class FakeWiki:
    """언어판마다 제목 → 문서. 받은 물음을 적는다."""

    def __init__(self, pages: dict[str, dict[str, dict[str, Any]]]) -> None:
        self.pages = pages
        self.asked: list[tuple[str, list[str]]] = []

    def __call__(self, lang: str, titles: list[str]) -> dict[str, Any]:
        self.asked.append((lang, titles))
        known = self.pages.get(lang, {})
        found = [known.get(title, {'title': title, 'missing': True}) for title in titles]
        # 받은 제목이 물은 제목과 다르면 넘겨주기다
        moved = [
            {'from': title, 'to': known[title]['title']}
            for title in titles
            if title in known and known[title]['title'] != title
        ]
        return {'query': {'pages': found, 'redirects': moved}}


def test_korean_first_then_english_then_reported():
    titles = [
        WikiTitle(ko='범선', en='Sailing ship', aliases=('돛단배',)),
        WikiTitle(ko='캐럭', en='Carrack'),
        WikiTitle(ko='코그선', en='Cog (ship)'),
        WikiTitle(ko='없는 배', en='No ship'),
        WikiTitle(ko='돛단배 (배)', en=''),
    ]
    wiki = FakeWiki(
        {
            'ko': {
                '범선': page('범선', '돛으로 가는 배다.', 1),
                '캐럭': page('캐럭', '포르투갈의 배다.', 2),
                '돛단배 (배)': page('범선', '돛으로 가는 배다.', 1),
            },
            'en': {
                'Carrack': page('Carrack', 'A carrack is a large ship.', 5),
                'Cog (ship)': page('Cog (ship)', 'Built in 1300.', 6),
            },
        }
    )

    records, report = collect(titles, wiki, PLACES)

    assert [record.key for record in records] == ['ko/범선', 'en/Carrack']
    sailing, carrack = records
    assert (sailing.kind, sailing.name, sailing.aliases, sailing.name_ko) == (
        ReferenceKind.TOPIC,
        '범선',
        ['범선', '돛단배'],
        '',
    )
    assert sailing.data == {'lang': 'ko', 'page_id': 1, 'revision_id': 10, 'url': 'https://ko.wikipedia.org/wiki/범선'}
    assert (carrack.name, carrack.name_ko, carrack.aliases, carrack.content) == (
        'Carrack',
        '캐럭',
        ['캐럭'],
        'A carrack is a large ship.',
    )
    assert (report.written, report.english, report.missing, report.emptied, report.duplicated) == (
        2,
        ['캐럭'],
        ['없는 배'],
        ['코그선'],
        ['돛단배 (배)'],
    )
    # 한국어판은 목록 전체를, 영어판은 한국어판으로 만들지 못한 것만 묻는다
    assert wiki.asked == [
        ('ko', ['범선', '캐럭', '코그선', '없는 배', '돛단배 (배)']),
        ('en', ['Carrack', 'Cog (ship)', 'No ship']),
    ]


def test_a_redirected_korean_page_keeps_both_names():
    title = WikiTitle(ko='갤리온', en='Galleon', aliases=('대형 범선',))
    wiki = FakeWiki({'ko': {'갤리온': page('갈레온', '돛대가 셋인 큰 배다.')}, 'en': {}})

    (record,), _ = collect([title], wiki, PLACES)

    assert (record.key, record.name, record.aliases) == ('ko/갈레온', '갈레온', ['갤리온', '갈레온', '대형 범선'])


def test_the_page_name_loses_its_disambiguation():
    title = WikiTitle(ko='성채')
    wiki = FakeWiki({'ko': {'성채': page('성 (건축)', '돌로 쌓은 집이다.')}})

    (record,), _ = collect([title], wiki, PLACES)

    assert record.aliases == ['성채', '성']


def test_long_titles_are_left_out():
    long_title = '가' * 101

    records, report = collect(
        [WikiTitle(ko=long_title)], FakeWiki({'ko': {long_title: page(long_title, '배다.')}}), PLACES
    )

    assert records == [] and report.missing == [long_title]


def test_the_file_is_written_as_a_wikipedia_document(tmp_path: Path):
    titles, places, output = tmp_path / 'titles.txt', tmp_path / 'places.txt', tmp_path / 'out' / 'wikipedia.json'
    titles.write_text('범선 | Sailing ship\n', encoding='utf-8')
    places.write_text('# 거를 곳\n포르투갈\n', encoding='utf-8')

    report = build(
        titles,
        places,
        output,
        FakeWiki({'ko': {'범선': page('범선', '돛으로 가는 배다. 포르투갈의 배.')}}),
        '2026-11-24',
    )

    document = read_document(output)
    assert report.written == 1
    assert (document.source, document.origin.revision, document.origin.license) == (
        ReferenceSource.WIKIPEDIA,
        '2026-11-24',
        'CC-BY-SA-4.0',
    )
    assert document.entries[0].content == '돛으로 가는 배다.'


# --- 번역 ---


def english_record(key: str = 'en/Carrack'):
    title = WikiTitle(ko='캐럭', en='Carrack')
    (record,), _ = collect(
        [title], FakeWiki({'ko': {}, 'en': {'Carrack': page('Carrack', 'A carrack is a large ship.')}}), PLACES
    )
    assert record.key == key
    return record


def translations(entries: dict, source: str = 'wikipedia') -> TranslationDocument:
    return TranslationDocument.model_validate({'format': 1, 'source': source, 'language': 'ko', 'entries': entries})


def test_english_lines_get_their_translation_and_the_rest_is_reported():
    report = BuildReport()
    record = english_record()

    (done,) = with_translations(
        [record],
        translations({'en/Carrack': {'name': '캐럭', 'content': '큰 배다.'}, 'en/Gone': {'name': '없음'}}),
        report,
    )
    (left,) = with_translations([record], translations({}), report)

    assert (done.name_ko, done.content_ko, done.aliases) == ('캐럭', '큰 배다.', ['캐럭'])
    assert report.untranslated == ['en/Carrack'] and left.content_ko == ''
    assert with_translations([record], translations({'en/Gone': {'name': '없음'}}), BuildReport()) == [record]


def test_a_translation_of_another_source_is_refused():
    with pytest.raises(ValueError, match='위키백과'):
        with_translations([english_record()], translations({}, source='srd51'), BuildReport())


def test_the_build_applies_the_translation_file(tmp_path: Path):
    titles, places, output, translation = (tmp_path / name for name in ('t.txt', 'p.txt', 'w.json', 'w.ko.json'))
    titles.write_text('캐럭 | Carrack\n', encoding='utf-8')
    places.write_text('', encoding='utf-8')
    body = {
        'format': 1,
        'source': 'wikipedia',
        'language': 'ko',
        'entries': {'en/Carrack': {'name': '캐럭', 'content': '큰 배다.'}},
    }
    translation.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    wiki = FakeWiki({'ko': {}, 'en': {'Carrack': page('Carrack', 'A carrack is a large ship.')}})

    report = build(titles, places, output, wiki, '2026-11-24', translation)

    assert read_document(output).entries[0].content_ko == '큰 배다.'
    assert report.untranslated == [] and report.stale == []


# --- 실린 파일 ---


def test_the_shipped_lists_are_read():
    titles = read_titles(WIKIPEDIA_TITLES_FILE)
    places = read_places(WIKIPEDIA_PLACES_FILE)

    assert len(titles) > 100 and all(title.ko for title in titles)
    assert '포르투갈' in places and 'Portugal' in places
    # 실린 데이터 파일의 영어판 줄은 모두 번역이 있다. 번역 파일에는 자료에 없는 줄이 없다
    document = read_document(WIKIPEDIA_FILE)
    english = {record.key for record in document.entries if record.data['lang'] == 'en'}
    assert english and all(record.content_ko for record in document.entries if record.key in english)
    assert set(read_translations(WIKIPEDIA_TRANSLATION_FILE).entries) == english
    # 한국어 이름은 두 글자 이상이다(한 글자는 낱말 속에서 잘못 걸린다)
    assert all(len(place) >= 2 for place in places if not place.isascii())
