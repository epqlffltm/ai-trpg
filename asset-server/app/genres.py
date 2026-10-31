# asset-server/app/genres.py

"""
장르. 캐릭터와 세계관이 하나씩 고른다(비워 둘 수 있다). 운영자가 정한 목록이다. 제작자가 자유롭게 적는 것은 태그다.

장르는 chat 의 대화와 story 의 장면, 그리고 소개 화면의 테마를 정한다. 그래서 하나뿐이고, 이야기의 종류만 둔다.
누구를 위한 이야기인가(남성향, 여성향)와 성인용인지는 장르가 아니다(태그와 등급이다).
TRPG 의 시나리오(trpg-server/app/listings/models.py 의 Genre)와 같은 목록이다. 바꿀 때 함께 바꾼다.
값은 주소와 저장에 쓰는 이름이고, 화면에 보이는 말은 화면이 정한다.
"""

import enum

# 저장하는 칸의 길이. 가장 긴 값보다 넉넉하다
GENRE_MAX_LENGTH = 30


class Genre(enum.StrEnum):
    """
    장르의 목록. 허용 값의 검사는 입력의 모양(schemas.py)이 한다.

    DB 의 CHECK 로 걸지 않는다. 걸면 목록을 바꿀 때마다 마이그레이션이 필요해진다(TRPG 와 같다).
    """

    FANTASY = 'fantasy'  # 판타지
    WUXIA = 'wuxia'  # 무협. 동양판타지를 포함한다
    URBAN_FANTASY = 'urban_fantasy'  # 현대판타지
    SF = 'sf'
    APOCALYPSE = 'apocalypse'  # 아포칼립스
    HORROR = 'horror'  # 공포
    MYSTERY = 'mystery'  # 추리
    ROMANCE = 'romance'  # 로맨스
    SLICE_OF_LIFE = 'slice_of_life'  # 일상
    ALT_HISTORY = 'alt_history'  # 대체역사
    COMEDY = 'comedy'  # 개그
