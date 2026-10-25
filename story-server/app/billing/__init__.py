# story-server/app/billing/__init__.py

"""
말 한 번의 값을 결제 서버에서 받는다(docs/architecture/story.md 의 "정한 것"의 청구).

chat 서버의 app/billing 과 같은 코드다(가격표 이름의 머리만 story 다).
청구 기록과 정리 작업은 말을 보내는 길과 함께 만든다.
게임, chat, story 의 세 벌이다. 나중에 server-core 로 올려 함께 쓴다(그때까지 고치면 세 벌을 함께 고친다).

  - client.py: 결제 서버를 부르는 것의 모양(Billing)과 결과
  - http_billing.py: 실제로 결제 서버를 부르는 것. 요청에 서명한다(server_core/service_auth/signing.py)
  - free_billing.py: 받지 않는 것. BILLING_URL 을 비우면 이것이다
  - metered.py, metrics.py: 부를 때마다 센다(billing_calls_total)
  - routing.py, router.py: 라우터가 쓰는 가격 목록의 의존성과, 가격 목록을 받지 못했을 때의 503
  - prices.py, price_list.py: 결제 서버의 가격 목록(story.<이름표>.i0.o0)과 그것을 받아 두는 것
  - setup.py: 설정을 보고 위의 것들을 만든다
"""
