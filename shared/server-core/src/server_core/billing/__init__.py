# shared/server-core/src/server_core/billing/__init__.py

"""
결제 서버를 부르는 것(#1266). 게임, chat, story 서버가 함께 쓴다(docs/architecture/shared-code.md 의 "서버의 공통부").

  - client.py: 결제 서버를 부르는 것의 모양(Billing)과 결과
  - http_billing.py: 실제로 결제 서버를 부르는 것. 요청에 서명하고(service_auth/signing.py) 추적의 머리말을 싣는다
  - free_billing.py: 받지 않는 것. BILLING_URL 을 비우면 이것이다
  - metered.py, metrics.py: 부를 때마다 센다(billing_calls_total)
  - prices.py, price_list.py: 결제 서버의 가격 목록과 그것을 받아 두는 것
  - settings.py: 서버의 설정이 물려받는 칸(BillingSettings)
  - setup.py: 설정을 보고 위의 것들을 만든다

서버에 남는 것: 가격표 이름의 머리와 이름을 짓는 함수(app/billing/prices.py), 청구 기록의 표와 정리 작업(게임 서버),
라우터의 의존성(app/billing/routing.py).
"""
