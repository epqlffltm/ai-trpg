# trpg-server/app/transcripts/__init__.py

"""
한 판의 기록을 마크다운 한 파일로 내려준다(#403).

  - reading.py: 누가 어디까지 받는가(앉은 사람은 받기 시작한 때까지, 떠난 사람은 떠난 때까지)와 이벤트를 쪽마다 읽기
  - markdown.py: 이벤트를 글로 바꾸기. 앉은 사람에게 내보내는 칸(app/events/responses.py 의 VISIBLE)만 본다
  - router.py: 내려받는 두 길. 다 모으지 않고 흘려 보낸다

읽기만 한다. 기록을 만들면서 테이블의 상태를 바꾸지 않는다.
"""
