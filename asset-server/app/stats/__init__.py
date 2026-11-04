# asset-server/app/stats/__init__.py

"""
작품마다의 시작 수(#985). chat 과 story 서버가 세어 주고, 이 서버가 몇 분마다 통째로 받아 와 쌓는다.

  - client.py: 그 서버의 내부 주소를 서명해 부른다
  - refresher.py: 몇 분마다 받아 와 바꿔 넣는 바퀴
  - repository.py: 받은 수를 바꿔 넣는다
요청의 길에서는 다른 서버를 부르지 않는다. 랭킹(app/rankings/)은 쌓아 둔 수만 읽는다.
"""
