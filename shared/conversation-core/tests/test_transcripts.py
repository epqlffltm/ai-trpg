# shared/conversation-core/tests/test_transcripts.py

"""
기록 파일을 쓰는 공통부(conversation_core/transcripts/)를 검증한다. 게임 서버의 쓰는 쪽 테스트를 옮기고 더했다(#1266).

보는 것.
  - 조각: 구분, 문단, 말은 앞뒤를 띄우고 한 줄의 일은 이어 쓴다
  - HTML: 글을 모두 바꿔 쓴다(태그가 되지 않는다). 한 줄의 일들은 <ul> 하나다. 문단 안의 줄은 <br> 이다.
    머리는 스크립트와 밖의 자원을 막는다. 파일 전체는 열린 목록을 닫고 끝난다
  - 마크다운: 맨 앞의 # 은 글자로 남는다. 빈 줄이 둘씩 겹치지 않는다
  - 텍스트: 표시 문법이 없다. 말은 들여 쓴다
  - 머리: 제목, 범위, 내려받은 때
기록의 내용(무엇을 조각으로 바꾸는가)은 쓰는 서버의 테스트가 본다.
"""

from datetime import UTC, datetime

from conversation_core.transcripts import html, markdown, text
from conversation_core.transcripts.blocks import Heading, Note, Paragraph, Speech, stands_apart

AT = datetime(2026, 11, 12, 9, 30, tzinfo=UTC)
BLOCKS = [
    Heading('대화'),
    Paragraph(('# 시작', '', '둘째 문단')),
    Speech('세라', ('안녕', '', '<b>둘</b>')),
    Note('a & b'),
]


def test_only_notes_run_on():
    assert [stands_apart(block) for block in BLOCKS] == [True, True, True, False]


# --- HTML ---


def test_html_blocks_are_escaped_and_notes_share_one_list():
    listing = False
    pieces = []
    for block in [Heading('라운드 <1>'), Note('a & b'), Note('c'), Speech('엘프 "1"', ('안녕', '', '<b>둘</b>'))]:
        chunk, listing = html.with_list(block, listing)
        pieces.append(chunk)
    written = ''.join(pieces) + html.footer(listing)

    assert written == (
        '<h2>라운드 &lt;1&gt;</h2>\n'
        '<ul>\n<li>a &amp; b</li>\n<li>c</li>\n</ul>\n'
        '<blockquote><p class="who">엘프 &quot;1&quot;</p><p>안녕</p><p>&lt;b&gt;둘&lt;/b&gt;</p></blockquote>\n'
        '</body>\n</html>\n'
    )


def test_html_keeps_line_breaks_inside_a_paragraph():
    assert html.block_html(Paragraph(('첫 줄', '둘째 줄', '', '새 문단'))) == '<p>첫 줄<br>둘째 줄</p><p>새 문단</p>\n'


def test_html_empty_lines_make_no_empty_paragraph():
    assert html.paragraphs(('', '하나', '', '', '둘', '')) == [['하나'], ['둘']]


def test_the_html_head_blocks_scripts_and_escapes_the_title():
    written = html.header('<제목>', '말 2개 & 시작', AT)

    assert "content=\"default-src 'none'; style-src 'unsafe-inline'\"" in written
    assert '<title>&lt;제목&gt;</title>' in written
    assert '기록: 말 2개 &amp; 시작<br>내려받은 때: 2026-11-12T09:30:00+00:00' in written


def test_an_html_document_closes_an_open_list():
    written = html.document('밤', '말 1개', [Heading('대화'), Note('끊긴 답')], AT)

    assert written.startswith('<!doctype html>\n')
    assert written.endswith('<h2>대화</h2>\n<ul>\n<li>끊긴 답</li>\n</ul>\n</body>\n</html>\n')


# --- 마크다운 ---


def test_markdown_keeps_a_leading_hash_as_text():
    assert markdown.safe_line('  # 제목 흉내') == '\\# 제목 흉내'
    assert markdown.safe_line('그냥 글') == '그냥 글'


def test_markdown_blocks():
    assert markdown.block_lines(Speech('세라', ('안녕', '', '# 끝'))) == ['> **세라**', '> 안녕', '>', '> \\# 끝']
    assert markdown.block_text(Note('갔다')) == '- 갔다\n'
    assert markdown.block_text(Heading('대화')) == '\n## 대화\n\n'


def test_markdown_never_doubles_an_empty_line():
    assert markdown.joined('끝\n\n', '\n## 대화\n\n') == '## 대화\n\n'
    assert markdown.joined('- 갔다\n', '\n## 대화\n\n') == '\n## 대화\n\n'
    assert markdown.joined('끝\n\n', '- 갔다\n') == '- 갔다\n'


def test_a_markdown_document():
    written = markdown.document('비 오는 밤', '말 2개', BLOCKS, AT)

    assert written.startswith('# 비 오는 밤\n\n- 기록: 말 2개\n- 내려받은 때: 2026-11-12T09:30:00+00:00\n\n')
    assert '\\# 시작' in written
    assert '\n\n\n' not in written


# --- 텍스트 ---


def test_plain_text_has_no_markup():
    blocks = [Heading('라운드 2'), Paragraph(('# 제목 같은 글',)), Speech('엘프', ('간다.', '')), Note('판정: 성공')]

    written = ''.join(text.block_text(block) for block in blocks)

    assert written == '\n== 라운드 2 ==\n\n# 제목 같은 글\n\n엘프:\n    간다.\n\n· 판정: 성공\n'


def test_a_text_document():
    written = text.document('밤', '말 1개', [Note('갔다')], AT)

    assert written == '밤\n기록: 말 1개\n내려받은 때: 2026-11-12T09:30:00+00:00\n· 갔다\n'
