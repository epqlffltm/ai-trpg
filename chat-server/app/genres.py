# chat-server/app/genres.py

"""
캐릭터의 장르(판의 형식 9). 규칙이 아니라 대화 화면(C3)의 테마다. DB 도 HTTP 도 모른다(story 의 세계관 장르와 같다).

  - 값의 목록은 asset 서버(asset-server/app/genres.py)가 지킨다. 이 서버는 글자인지만 본다.
    장르가 늘어도 이 서버를 고치지 않아도 되고, 모르는 값 때문에 대화 읽기가 깨지지 않는다
  - 대화 응답의 캐릭터 문서에는 늘 장르가 있다(화면이 장르마다 테마를 고르므로 장르 없는 화면이 없다).
    사본에 장르가 없으면(형식 9 전에 가져온 사본) DEFAULT_GENRE 를 싣는다
    (app/conversations/schemas.py 의 CharacterDocumentOut)
  - 같은 판의 사본을 다시 가져올 때 asset 이 준 판에 장르가 있으면, 장르가 없는 사본에 채운다.
    사본은 사람마다, 판마다 하나라 그 판의 대화 모두가 함께 채워진다. 장르 말고는 사본을 바꾸지 않는다
"""

# 사본에 장르가 없을 때 싣는 장르(story 와 같다)
DEFAULT_GENRE = 'fantasy'


def genre_of(document: dict) -> str | None:
    """판의 문서에 적힌 장르. 없거나, 비었거나, 글자가 아니면 None."""
    genre = document.get('genre')
    return genre if isinstance(genre, str) and genre else None


def shown_genre(document: dict) -> str:
    """대화 응답에 싣는 장르. 판에 없으면 DEFAULT_GENRE."""
    return genre_of(document) or DEFAULT_GENRE


def filled_document(kept: dict, received: dict) -> dict | None:
    """
    둔 사본에 장르가 없고 받은 판에 있으면 장르를 채운 새 문서. 채울 것이 없으면 None.
    장르 말고는 둔 사본 그대로다(판은 바뀌지 않는다).
    """
    genre = genre_of(received)
    if genre is None or genre_of(kept) is not None:
        return None
    return {**kept, 'genre': genre}
