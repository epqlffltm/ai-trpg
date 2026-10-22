# asset-server/app/content/html.py

"""
제작자가 쓴 소개 글(HTML 과 인라인 CSS)을 허용 목록으로 거른다. 무엇을 걸렀는지도 알린다.

규칙은 docs/architecture/shared-code.md 의 "소개 글의 HTML"이다. 게시할 때 asset-server 가 거르고(이 모듈),
화면이 그릴 때 같은 허용 목록으로 DOMPurify 가 한 번 더 거른다. 두 곳의 목록은 문서의 표를 기준으로 같게 둔다.

이 모듈은 app.* 를 가져오지 않는 순수한 모듈이다(tests/test_content_boundary.py 가 지킨다).
두 번째로 쓰는 곳(TRPG 시나리오 소개를 asset 으로 옮기는 PR)이 생기면 파일째 shared/ 로 옮긴다(2026-10-21 결정).

거르는 것은 nh3(ammonia)가 한다. 무엇이 빠졌는지는 nh3 가 알려 주지 않아서, 같은 판단 함수로 입력을 따로 훑어 모은다.
판단 함수(allowed_link, allowed_image, cleaned_style)는 하나다. 거르기와 알리기가 서로 다른 규칙을 쓰지 않는다.
"""

import enum
import re
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser

import nh3

# 소개 글의 크기 상한(바이트). 그림은 주소만 들어가므로 세지 않는다
INTRO_MAX_BYTES = 50 * 1024

# 허락하는 태그. 문단과 제목, 목록, 표, 강조, 줄바꿈과 가로줄, 상자, 그림, 링크, 접기
ALLOWED_TAGS = frozenset(
    {
        'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li',
        'table', 'caption', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
        'strong', 'em', 'b', 'i', 'u', 's', 'mark', 'small', 'sub', 'sup',
        'br', 'hr',
        'div', 'span',
        'img', 'a',
        'details', 'summary',
    }
)  # fmt: skip
# 모든 태그에 허락하는 속성. CSS 는 인라인(style)만이다
GLOBAL_ATTRIBUTES = frozenset({'style'})
# 태그마다 더 허락하는 속성
TAG_ATTRIBUTES = {
    'a': frozenset({'href', 'title'}),
    'img': frozenset({'src', 'alt', 'width', 'height'}),
    'td': frozenset({'colspan', 'rowspan'}),
    'th': frozenset({'colspan', 'rowspan'}),
    'details': frozenset({'open'}),
}
# 허락하는 CSS 속성. 글자, 상자, 배치다. position, z-index, transform 과 url() 을 받는 속성은 없다
ALLOWED_STYLE_PROPERTIES = frozenset(
    {
        'color', 'font-size', 'font-weight', 'font-style', 'text-align', 'text-decoration', 'line-height',
        'letter-spacing',
        'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
        'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
        'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
        'border-color', 'border-style', 'border-width', 'border-radius',
        'background-color', 'width', 'max-width', 'height', 'max-height',
        'display',
        'flex', 'flex-direction', 'flex-wrap', 'flex-grow', 'flex-shrink', 'flex-basis', 'order',
        'justify-content', 'align-items', 'align-content', 'align-self',
        'grid-template-columns', 'grid-template-rows', 'grid-column', 'grid-row',
        'gap', 'row-gap', 'column-gap',
    }
)  # fmt: skip
# CSS 값에 있으면 그 속성을 뺀다. 바깥 주소 불러오기(url), 옛 브라우저의 스크립트(expression), 글자 숨기기(\ 이스케이프)
FORBIDDEN_STYLE_VALUES = ('url(', 'expression(', '\\')
# 링크는 https 만 받는다. javascript:, data:, http: 는 뺀다
LINK = re.compile(r'^https://[^\s]+$', re.IGNORECASE)
# 그림은 우리 그림 저장소의 것만 받는다. asset-server 가 내주는 주소다(그림의 id 는 소문자 UUID)
IMAGE = re.compile(r'^/api/v1/asset/images/(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$')
# 링크에 붙이는 rel. 연 페이지가 이 페이지를 건드리지 못하고, 어디서 왔는지 알리지 않는다
LINK_REL = 'noopener noreferrer'


class RemovedKind(enum.StrEnum):
    """걸러 낸 것의 종류."""

    # 허락하지 않은 태그(script, iframe, form …). 내용은 남는다(script 와 style 은 내용도 뺀다)
    TAG = 'tag'
    # 허락하지 않은 속성(onclick, class …). 이름은 "태그.속성"이다
    ATTRIBUTE = 'attribute'
    # 허락하지 않은 CSS 속성, 또는 값에 url() 같은 것이 든 CSS 속성
    STYLE = 'style'
    # https 가 아닌 링크
    LINK = 'link'
    # 우리 그림 저장소의 것이 아닌 그림
    IMAGE = 'image'


@dataclass(frozen=True)
class Removed:
    """걸러 낸 것 하나. 게시의 problems[] 로 제작자에게 보인다."""

    kind: RemovedKind
    name: str


@dataclass(frozen=True)
class Cleaned:
    """거른 글과 걸러 낸 것들. 걸러 낸 것은 처음 나온 차례로, 같은 것은 한 번만이다."""

    html: str
    removed: list[Removed]


def allowed_attributes(tag: str) -> frozenset[str]:
    """그 태그에 허락하는 속성."""
    return GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, frozenset())


def allowed_link(href: str) -> bool:
    """받는 링크인가(https)."""
    return LINK.fullmatch(href.strip()) is not None


def allowed_image(src: str) -> bool:
    """받는 그림인가(우리 그림 저장소의 주소)."""
    return IMAGE.fullmatch(src.strip()) is not None


def style_declarations(style: str) -> list[tuple[str, str]]:
    """인라인 CSS 를 (속성, 값)들로. 속성은 소문자다. 콜론이 없는 조각은 버린다."""
    pairs = []
    for piece in style.split(';'):
        name, colon, value = piece.partition(':')
        if colon and name.strip():
            pairs.append((name.strip().lower(), value.strip()))
    return pairs


def allowed_declaration(name: str, value: str) -> bool:
    """받는 CSS 속성인가. 허용 목록에 있고 값에 금지된 것이 없어야 한다."""
    lowered = value.lower()
    return name in ALLOWED_STYLE_PROPERTIES and not any(word in lowered for word in FORBIDDEN_STYLE_VALUES)


def cleaned_style(style: str) -> tuple[str, list[str]]:
    """받는 CSS 속성만 남긴 인라인 CSS 와 뺀 속성의 이름들."""
    kept, dropped = [], []
    for name, value in style_declarations(style):
        if allowed_declaration(name, value):
            kept.append(f'{name}: {value}')
        else:
            dropped.append(name)
    return '; '.join(kept), dropped


def filter_attribute(tag: str, attribute: str, value: str) -> str | None:
    """
    nh3 가 허용 목록을 지난 속성마다 부른다. 값을 고쳐 돌려주거나 None 으로 뺀다.

    style 은 받는 속성만 남긴다(남는 것이 없으면 뺀다). 링크와 그림의 주소는 규칙에 맞을 때만 둔다.
    """
    if attribute == 'style':
        kept, _ = cleaned_style(value)
        return kept or None
    if tag == 'a' and attribute == 'href':
        return value if allowed_link(value) else None
    if tag == 'img' and attribute == 'src':
        return value if allowed_image(value) else None
    return value


def attribute_removals(tag: str, attribute: str, value: str) -> list[Removed]:
    """
    속성 하나에서 걸러질 것들. 거르기(filter_attribute)와 같은 판단이다.

    링크의 rel 은 거를 때 nh3 가 LINK_REL 로 덮어 붙인다. 그 값이면 걸러진 것이 아니다.
    """
    if tag == 'a' and attribute == 'rel' and value == LINK_REL:
        return []
    if attribute not in allowed_attributes(tag):
        return [Removed(RemovedKind.ATTRIBUTE, f'{tag}.{attribute}')]
    if attribute == 'style':
        return [Removed(RemovedKind.STYLE, name) for name in cleaned_style(value)[1]]
    if tag == 'a' and attribute == 'href' and not allowed_link(value):
        return [Removed(RemovedKind.LINK, value.strip())]
    if tag == 'img' and attribute == 'src' and not allowed_image(value):
        return [Removed(RemovedKind.IMAGE, value.strip())]
    return []


def tag_removals(tag: str, attributes: list[tuple[str, str | None]]) -> list[Removed]:
    """태그 하나에서 걸러질 것들. 허락하지 않은 태그는 태그만 알린다(그 속성은 태그와 함께 사라진다)."""
    if tag not in ALLOWED_TAGS:
        return [Removed(RemovedKind.TAG, tag)]
    return [removed for name, value in attributes for removed in attribute_removals(tag, name, value or '')]


class RemovalScanner(HTMLParser):
    """입력을 훑어 걸러질 것을 모은다. 거르지 않는다. 같은 것은 한 번만, 처음 나온 차례로 모은다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.removed: dict[Removed, None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for removed in tag_removals(tag, attrs):
            self.removed.setdefault(removed)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class ImageScanner(HTMLParser):
    """img 의 src 가운데 우리 그림 저장소의 주소에서 그림의 id 를 모은다. 처음 나온 차례로, 같은 것은 한 번만이다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: dict[uuid.UUID, None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != 'img':
            return
        for name, value in attrs:
            found = IMAGE.fullmatch((value or '').strip()) if name == 'src' else None
            if found:
                self.ids.setdefault(uuid.UUID(found['id']))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def image_ids(html: str) -> list[uuid.UUID]:
    """글에 든 우리 그림들의 id. 거른 글을 넣는다(거르기 전의 글이면 걸러질 그림까지 든다)."""
    scanner = ImageScanner()
    scanner.feed(html)
    scanner.close()
    return list(scanner.ids)


def removals(html: str) -> list[Removed]:
    """입력에서 걸러질 것들."""
    scanner = RemovalScanner()
    scanner.feed(html)
    scanner.close()
    return list(scanner.removed)


def sanitize(html: str) -> str:
    """허용 목록으로 거른 HTML. 주석과 script, style 의 내용도 뺀다. 링크에는 rel 을 붙인다."""
    return nh3.clean(
        html,
        tags=set(ALLOWED_TAGS),
        attributes={'*': set(GLOBAL_ATTRIBUTES), **{tag: set(names) for tag, names in TAG_ATTRIBUTES.items()}},
        attribute_filter=filter_attribute,
        url_schemes={'https'},
        link_rel=LINK_REL,
        strip_comments=True,
        # 두 번째 겹이다. filter_attribute 가 이미 걸렀어도 nh3 가 CSS 속성을 한 번 더 본다
        filter_style_properties=set(ALLOWED_STYLE_PROPERTIES),
    )


def clean_intro(html: str) -> Cleaned:
    """소개 글을 거르고, 무엇을 걸렀는지 함께 돌려준다."""
    return Cleaned(html=sanitize(html), removed=removals(html))


def intro_too_long(html: str) -> bool:
    """소개 글이 크기 상한(50KB)을 넘는가. UTF-8 의 바이트로 센다."""
    return len(html.encode('utf-8')) > INTRO_MAX_BYTES
