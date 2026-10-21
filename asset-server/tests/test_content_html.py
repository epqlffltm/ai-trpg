# asset-server/tests/test_content_html.py

"""
소개 글의 HTML 거르기(app/content/html.py)를 검증한다. 모듈만 본다. DB 도 앱도 쓰지 않는다.

보는 것(docs/architecture/shared-code.md 의 "소개 글의 HTML").
  - 허락한 태그와 속성, CSS 는 그대로 남는다.
  - 스크립트, 이벤트 속성, 다른 페이지 끼워 넣기, 입력 창, 화면을 덮는 CSS, 바깥 주소를 부르는 CSS 를 뺀다.
  - 링크는 https 만, 그림은 우리 그림 저장소의 것만 남는다. 링크에는 rel 이 붙는다.
  - 걸러 낸 것을 알린다. 같은 것은 한 번, 처음 나온 차례다. 거른 글을 다시 거르면 바뀌지 않고 알릴 것도 없다.
  - 크기 상한은 UTF-8 의 바이트로 센다.
"""

import pytest

from app.content.html import (
    INTRO_MAX_BYTES,
    Removed,
    RemovedKind,
    clean_intro,
    cleaned_style,
    intro_too_long,
    removals,
    sanitize,
)

IMAGE_ID = '0b7c6f1e-2d3a-4b5c-8d9e-0f1a2b3c4d5e'
OUR_IMAGE = f'/api/v1/asset/images/{IMAGE_ID}'

SAMPLES = [
    '<h1>제목</h1><p>본문 <strong>강조</strong>와 <em>기울임</em><br>다음 줄</p><hr>',
    '<ul><li>하나</li></ul><ol><li>둘</li></ol>',
    '<table><caption>표</caption><tr><th colspan="2">머리</th></tr><tr><td rowspan="2">칸</td></tr></table>',
    '<details open><summary>접기</summary><div style="color: red; padding: 4px">안</div></details>',
    f'<p><img src="{OUR_IMAGE}" alt="그림" width="100"><a href="https://example.com" title="밖">링크</a></p>',
    '<div onclick="steal()" class="x" style="position: fixed; z-index: 99; color: blue">덮기</div>',
    '<script>alert(1)</script><style>p{}</style><iframe src="https://evil"></iframe>',
    '<form action="https://evil"><input name="pw"><button>로그인</button></form><meta charset="x"><link rel="x">',
    '<a href="javascript:alert(1)">a</a><a href="data:text/html,x">b</a><a href="http://plain">c</a>',
    '<img src="https://tracker.example/p.png"><img src="/api/v1/asset/images/NOT-A-UUID">',
    '<p style="background: url(https://evil/p.png); background-color: url(x); color: re\\64">x</p>',
    '<!-- 주석 --><span style="transform: rotate(1deg)">회전</span>',
]


def test_allowed_content_is_kept():
    allowed = (
        '<h1>제목</h1><p>본문 <strong>강조</strong></p>'
        '<table><tbody><tr><td colspan="2">칸</td></tr></tbody></table>'
        '<details open=""><summary>접기</summary><div style="color:red">안</div></details>'
    )

    cleaned = clean_intro(allowed)

    assert cleaned.html == allowed
    assert cleaned.removed == []


def test_scripts_and_their_content_are_removed():
    cleaned = clean_intro('<p>앞</p><script>alert(1)</script><style>p{display:none}</style><p>뒤</p>')

    assert cleaned.html == '<p>앞</p><p>뒤</p>'
    assert cleaned.removed == [Removed(RemovedKind.TAG, 'script'), Removed(RemovedKind.TAG, 'style')]


@pytest.mark.parametrize('tag', ['iframe', 'object', 'embed', 'form', 'input', 'button', 'meta', 'link'])
def test_tags_that_load_or_ask_for_things_are_removed(tag: str):
    cleaned = clean_intro(f'<div><{tag}></{tag}>남는 글</div>')

    assert tag not in cleaned.html
    assert '남는 글' in cleaned.html
    assert cleaned.removed == [Removed(RemovedKind.TAG, tag)]


def test_event_and_unknown_attributes_are_removed():
    cleaned = clean_intro('<div onclick="steal()" class="x" id="y">글</div>')

    assert cleaned.html == '<div>글</div>'
    assert cleaned.removed == [
        Removed(RemovedKind.ATTRIBUTE, 'div.onclick'),
        Removed(RemovedKind.ATTRIBUTE, 'div.class'),
        Removed(RemovedKind.ATTRIBUTE, 'div.id'),
    ]


def test_css_that_covers_the_screen_or_loads_addresses_is_removed():
    cleaned = clean_intro(
        '<div style="position: fixed; z-index: 99; transform: scale(9); color: blue; '
        'background: url(https://evil/p.png); background-color: url(x); width: expression(1); '
        'font-size: 1\\65m">x</div>'
    )

    assert cleaned.html == '<div style="color:blue">x</div>'
    assert [removed.name for removed in cleaned.removed] == [
        'position',
        'z-index',
        'transform',
        'background',
        'background-color',
        'width',
        'font-size',
    ]
    assert {removed.kind for removed in cleaned.removed} == {RemovedKind.STYLE}


def test_a_style_with_nothing_left_is_dropped():
    assert sanitize('<p style="position: absolute">x</p>') == '<p>x</p>'
    assert cleaned_style('color: red;; nothing; PADDING : 2px') == ('color: red; padding: 2px', [])


def test_only_https_links_are_kept_and_they_get_rel():
    cleaned = clean_intro(
        '<a href="https://example.com">좋음</a><a href="javascript:alert(1)">a</a>'
        '<a href="data:text/html,x">b</a><a href="http://plain">c</a>'
    )

    assert cleaned.html == (
        '<a href="https://example.com" rel="noopener noreferrer">좋음</a>'
        '<a rel="noopener noreferrer">a</a><a rel="noopener noreferrer">b</a><a rel="noopener noreferrer">c</a>'
    )
    assert cleaned.removed == [
        Removed(RemovedKind.LINK, 'javascript:alert(1)'),
        Removed(RemovedKind.LINK, 'data:text/html,x'),
        Removed(RemovedKind.LINK, 'http://plain'),
    ]


def test_only_images_from_our_store_are_kept():
    cleaned = clean_intro(
        f'<img src="{OUR_IMAGE}" alt="우리"><img src="https://tracker.example/p.png">'
        f'<img src="{OUR_IMAGE.upper()}"><img src="{OUR_IMAGE}/../x">'
    )

    assert cleaned.html == f'<img src="{OUR_IMAGE}" alt="우리"><img><img><img>'
    assert [removed.kind for removed in cleaned.removed] == [RemovedKind.IMAGE] * 3


def test_removals_are_told_once_in_the_order_they_appear():
    found = removals('<div onclick="a"><script></script><div onclick="b"></div></div>')

    assert found == [Removed(RemovedKind.ATTRIBUTE, 'div.onclick'), Removed(RemovedKind.TAG, 'script')]


def test_comments_are_removed():
    assert sanitize('<p>글<!-- 숨긴 말 --></p>') == '<p>글</p>'


@pytest.mark.parametrize('sample', SAMPLES)
def test_cleaned_html_is_clean(sample: str):
    once = sanitize(sample)

    # 거른 글은 다시 걸러도 같고, 알릴 것이 없다. 거르기와 알리기가 같은 규칙을 쓴다
    assert sanitize(once) == once
    assert removals(once) == []


def test_the_size_is_counted_in_bytes():
    assert not intro_too_long('a' * INTRO_MAX_BYTES)
    assert intro_too_long('a' * (INTRO_MAX_BYTES + 1))
    # 한글은 세 바이트다
    assert intro_too_long('가' * (INTRO_MAX_BYTES // 3 + 1))


def test_a_rel_written_by_the_maker_is_replaced():
    cleaned = clean_intro('<a href="https://example.com" rel="opener">링크</a>')

    assert cleaned.html == '<a href="https://example.com" rel="noopener noreferrer">링크</a>'
    assert cleaned.removed == [Removed(RemovedKind.ATTRIBUTE, 'a.rel')]


def test_self_closing_tags_are_scanned_too():
    assert removals('<br onclick="x"/><img src="https://evil/p.png"/>') == [
        Removed(RemovedKind.ATTRIBUTE, 'br.onclick'),
        Removed(RemovedKind.IMAGE, 'https://evil/p.png'),
    ]


def test_relative_links_and_capital_letters_do_not_slip_through():
    cleaned = clean_intro('<a href="/login">a</a><a href="#top">b</a><p style="color: red; width: URL(x)">c</p>')

    assert 'href' not in cleaned.html
    assert '<p style="color:red">c</p>' in cleaned.html
    assert [removed.name for removed in cleaned.removed] == ['/login', '#top', 'width']
