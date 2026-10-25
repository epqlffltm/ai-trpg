// web/apps/web/src/pages/chat/character/introHtml.ts
// 제작자가 쓴 소개 글(HTML 과 인라인 CSS)을 그리기 전에 한 번 더 거른다(두 번째 겹). 게시할 때 asset 서버가 이미 걸렀다.
// 허용 목록은 asset-server/app/content/html.py 와 같다(docs/architecture/shared-code.md 의 "소개 글의 HTML"). 바꾸면 세 곳을 함께 바꾼다.
//
// 그린 뒤의 일을 위해 세 가지를 바꾼다.
//   - 거른 인라인 CSS 는 style 이 아니라 data-intro-style 에 둔다. 화면의 CSP(default-src 'self', style-src 를 따로 두지 않음)는
//     HTML 의 style 속성을 막는다. CSP 를 넓히지 않고, 그린 뒤에 CSSOM(element.style)으로 입힌다(IntroHtml). CSSOM 은 CSP 가 막지 않는다.
//   - 우리 그림 저장소의 img 는 src 를 빼고 data-image-id 에 그림의 id 를 둔다. img 는 토큰을 싣지 못해 성인 등급의 그림을 받지 못한다.
//     그래서 브라우저가 먼저 부르지 않게 하고, 화면이 토큰을 실어 받아 blob: 주소를 넣는다(IntroHtml).
//   - 링크는 새 창으로 열고 rel="noopener noreferrer" 를 붙이고, 바깥 링크라는 표시(intro-link--external)를 단다.

import DOMPurify from 'dompurify';

const ALLOWED_TAGS = [
  'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'table', 'caption', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
  'strong', 'em', 'b', 'i', 'u', 's', 'mark', 'small', 'sub', 'sup',
  'br', 'hr',
  'div', 'span',
  'img', 'a',
  'details', 'summary',
];
const GLOBAL_ATTRIBUTES = ['style'];
const TAG_ATTRIBUTES: Record<string, readonly string[]> = {
  a: ['href', 'title'],
  img: ['src', 'alt', 'width', 'height'],
  td: ['colspan', 'rowspan'],
  th: ['colspan', 'rowspan'],
  details: ['open'],
};
const ALLOWED_STYLE_PROPERTIES = new Set([
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
]);
const FORBIDDEN_STYLE_VALUES = ['url(', 'expression(', '\\'];
const LINK = /^https:\/\/\S+$/i;
const IMAGE = /^\/api\/v1\/asset\/images\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;
const LINK_REL = 'noopener noreferrer';

/** 그 태그에 허락하는 속성인가 */
export function allowedAttribute(tag: string, attribute: string): boolean {
  return GLOBAL_ATTRIBUTES.includes(attribute) || (TAG_ATTRIBUTES[tag]?.includes(attribute) ?? false);
}

/** 받는 CSS 속성만 남긴 인라인 CSS. 남는 것이 없으면 빈 글 */
export function cleanStyle(style: string): string {
  return style
    .split(';')
    .map((piece) => {
      const colon = piece.indexOf(':');
      return colon < 0 ? null : { name: piece.slice(0, colon).trim().toLowerCase(), value: piece.slice(colon + 1).trim() };
    })
    .filter((pair): pair is { name: string; value: string } => pair !== null && pair.name !== '' && allowedDeclaration(pair.name, pair.value))
    .map((pair) => `${pair.name}: ${pair.value}`)
    .join('; ');
}

function allowedDeclaration(name: string, value: string): boolean {
  const lowered = value.toLowerCase();
  return ALLOWED_STYLE_PROPERTIES.has(name) && !FORBIDDEN_STYLE_VALUES.some((word) => lowered.includes(word));
}

/** 우리 그림 저장소의 주소면 그림의 id, 아니면 null */
export function imageIdOf(src: string): string | null {
  return IMAGE.exec(src.trim())?.[1] ?? null;
}

/** 받는 링크인가(https) */
export function allowedLink(href: string): boolean {
  return LINK.test(href.trim());
}

const purifier = DOMPurify();

// 속성마다: 태그마다의 허용 목록, 거른 CSS, https 링크, 우리 그림만
purifier.addHook('uponSanitizeAttribute', (node, data) => {
  const tag = node.nodeName.toLowerCase();
  const value = data.attrValue;
  if (!allowedAttribute(tag, data.attrName)) data.keepAttr = false;
  else if (data.attrName === 'style') {
    const style = cleanStyle(value);
    if (style) data.attrValue = style;
    else data.keepAttr = false;
  } else if (tag === 'a' && data.attrName === 'href') data.keepAttr = allowedLink(value);
  else if (tag === 'img' && data.attrName === 'src') data.keepAttr = imageIdOf(value) !== null;
});

// 남은 것을 그리기 좋게: CSS 와 그림은 data- 로 옮기고, 링크는 새 창과 표시
purifier.addHook('afterSanitizeAttributes', (node) => {
  if (node instanceof Element) markStyle(node);
  if (node instanceof HTMLImageElement) markImage(node);
  if (node instanceof HTMLAnchorElement && node.hasAttribute('href')) markLink(node);
});

function markStyle(element: Element): void {
  const style = element.getAttribute('style');
  if (style === null) return;
  element.removeAttribute('style');
  element.setAttribute('data-intro-style', style);
}

function markImage(image: HTMLImageElement): void {
  const id = imageIdOf(image.getAttribute('src') ?? '');
  image.removeAttribute('src');
  if (id) image.setAttribute('data-image-id', id);
}

function markLink(link: HTMLAnchorElement): void {
  link.setAttribute('target', '_blank');
  link.setAttribute('rel', LINK_REL);
  link.setAttribute('class', 'intro-link--external');
}

/** 그릴 수 있게 거른 소개 글 */
export function sanitizeIntro(html: string): string {
  return purifier.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [...new Set([...GLOBAL_ATTRIBUTES, ...Object.values(TAG_ATTRIBUTES).flat()])],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  });
}
