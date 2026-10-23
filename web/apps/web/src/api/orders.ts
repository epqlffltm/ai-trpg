// web/apps/web/src/api/orders.ts
// 크레딧 충전(결제 서버, A7)과 주문 내역·청약철회(A8). 상품, 주문 만들기, 승인 요청, 주문 읽기, 내 주문 목록, 청약철회.
// 값과 크레딧은 서버가 상품에서 찾는다. 화면은 상품의 번호만 보낸다(보낸 금액을 서버가 쓰지 않는다).
//
//   - 주문 만들기에는 Idempotency-Key 를 붙인다. 화면이 주문마다 새로 짓고, 답을 받지 못해 다시 보낼 때만 같은 것을 쓴다
//   - 승인은 같은 결제 번호로 몇 번 불러도 크레딧이 한 번만 들어간다. 202 는 결과를 모르는 것(confirming)이다
//   - 청약철회는 본문이 없다(금액과 이유는 서버가 정한다). 다시 불러도 한 번만 취소된다. 202 는 결과를 모르는 것(refunding)이다

import { apiRequest } from './http';
import type { Order, OrderPage, Product } from './types';

const BILLING = '/api/v1/billing';

export async function fetchProducts(signal?: AbortSignal): Promise<Product[]> {
  const response = await apiRequest<{ products: Product[] }>(`${BILLING}/products`, signal ? { signal } : {});
  return response.products;
}

/** 주문을 만든다(pending). 같은 키로 이미 만든 것이면 그것이 온다 */
export function createOrder(productId: string, idempotencyKey: string): Promise<Order> {
  return apiRequest<Order>(`${BILLING}/orders`, {
    method: 'POST',
    body: { product_id: productId },
    headers: { 'Idempotency-Key': idempotencyKey },
  });
}

/** 결제창이 준 결제 번호로 승인을 요청한다. paid, failed, 또는 모름(confirming) */
export function confirmOrder(orderId: string, paymentKey: string): Promise<Order> {
  return apiRequest<Order>(`${BILLING}/orders/${encodeURIComponent(orderId)}/confirm`, {
    method: 'POST',
    body: { payment_key: paymentKey },
  });
}

export function fetchOrder(orderId: string, signal?: AbortSignal): Promise<Order> {
  return apiRequest<Order>(`${BILLING}/orders/${encodeURIComponent(orderId)}`, signal ? { signal } : {});
}

/** 주문 목록의 한 쪽에 읽는 주문 수(서버는 1~50) */
export const ORDER_PAGE_SIZE = 20;

/** 내 주문의 한 쪽. 만든 때가 늦은 것부터, 상태와 상관없이 모두. before 는 앞 쪽의 next_before */
export function fetchOrders(before: string | undefined, signal?: AbortSignal): Promise<OrderPage> {
  return apiRequest<OrderPage>(`${BILLING}/orders`, { query: { limit: ORDER_PAGE_SIZE, before }, ...(signal ? { signal } : {}) });
}

/** 청약철회. refunded, 또는 모름(refunding). 할 수 없으면 409 와 그 까닭(code) */
export function refundOrder(orderId: string): Promise<Order> {
  return apiRequest<Order>(`${BILLING}/orders/${encodeURIComponent(orderId)}/refund`, { method: 'POST' });
}
