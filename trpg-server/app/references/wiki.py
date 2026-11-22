# trpg-server/app/references/wiki.py

"""
위키백과를 참고 자료로 넣는 규칙(README 의 "위키백과"). DB 도 HTTP 도 모르는 값들이다.

지금은 출처 표시뿐이다. 받는 도구와 거르는 규칙(위키 문법, 실제 세계를 가리키는 문장)은 다음 단계에서 이 파일에 더한다.

정한 것(2026-11-22 유저 결정).
  - 고른 제목 목록만 넣는다. 한국어판 먼저, 없으면 영어판이다.
  - 서술에만 쓴다. 로어북·도감으로 복사하지 않는다(records.py 의 COPYABLE_SOURCES).
  - 위키백과의 글은 CC BY-SA 4.0 이다. 데이터 파일도 같은 조건이다. 줄마다 원문의 주소를 data.url 에 둔다.
"""

WIKIPEDIA_ATTRIBUTION = (
    'This work includes text adapted from Wikipedia articles (Korean and English editions), '
    'licensed under the Creative Commons Attribution-ShareAlike 4.0 International License '
    '(https://creativecommons.org/licenses/by-sa/4.0/). Each entry links to its source article.'
)
WIKIPEDIA_CHANGES = (
    'Only the lead section was used. Wiki markup and sentences about real-world places, people and dates '
    'were removed, and the text was shortened.'
)
WIKIPEDIA_TRANSLATED = ' Entries from the English edition were translated into Korean.'
