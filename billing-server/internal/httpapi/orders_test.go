// billing-server/internal/httpapi/orders_test.go

package httpapi_test

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const (
	productsURL = httpapi.APIPrefix + "/products"
	ordersURL   = httpapi.APIPrefix + "/orders"
	// orderID 는 가짜 주문의 번호다.
	orderID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
)

// fakeOrders 는 정해 둔 대로 답하는 가짜 주문 서비스다. 무엇을 받았는지 적어 둔다.
type fakeOrders struct {
	order order.Order
	isNew bool
	err   error

	calls      int
	user       uuid.UUID
	orderID    uuid.UUID
	productID  string
	key        string
	paymentKey string
}

func (f *fakeOrders) Create(_ context.Context, userID uuid.UUID, productID string, key string) (order.Order, bool, error) {
	f.calls++
	f.user, f.productID, f.key = userID, productID, key
	return f.order, f.isNew, f.err
}

func (f *fakeOrders) Get(_ context.Context, userID uuid.UUID, id uuid.UUID) (order.Order, error) {
	f.calls++
	f.user, f.orderID = userID, id
	return f.order, f.err
}

func (f *fakeOrders) Confirm(_ context.Context, userID uuid.UUID, id uuid.UUID, paymentKey string) (order.Order, error) {
	f.calls++
	f.user, f.orderID, f.paymentKey = userID, id, paymentKey
	return f.order, f.err
}

func (f *fakeOrders) Refund(_ context.Context, userID uuid.UUID, id uuid.UUID) (order.Order, error) {
	f.calls++
	f.user, f.orderID = userID, id
	return f.order, f.err
}

// sampleOrder 는 응답의 모양을 볼 때 쓰는 주문이다.
func sampleOrder(t *testing.T, status order.Status) order.Order {
	t.Helper()
	return order.Order{
		ID:        mustUUID(t, orderID),
		UserID:    mustUUID(t, testenv.UserID),
		ProductID: "credits-1000",
		Price:     1000,
		Credits:   1000,
		Status:    status,
		CreatedAt: time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC),
		ExpiresAt: time.Date(2026, 3, 3, 9, 0, 0, 0, time.UTC),
	}
}

// request 는 보낼 요청 하나다.
type request struct {
	method  string
	path    string
	body    string
	headers map[string]string
	// anonymous 가 true 면 토큰을 붙이지 않는다.
	anonymous bool
}

// send 는 라우터에 요청을 보내고 응답을 돌려준다. 토큰의 주인은 testenv.UserID 다.
func send(t *testing.T, deps httpapi.Dependencies, r request) *httptest.ResponseRecorder {
	t.Helper()
	return sendAs(t, deps, testenv.UserID, r)
}

// sendAs 는 userID 의 토큰을 가진 것처럼 요청을 보낸다.
func sendAs(t *testing.T, deps httpapi.Dependencies, userID string, r request) *httptest.ResponseRecorder {
	t.Helper()
	deps.DB = &fakeDB{}
	deps.Verifier = &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, userID)}}
	router := httpapi.NewRouter(deps)
	req := httptest.NewRequest(r.method, r.path, strings.NewReader(r.body))
	if !r.anonymous {
		req.Header.Set("Authorization", "Bearer the-token")
	}
	for name, value := range r.headers {
		req.Header.Set(name, value)
	}
	response := httptest.NewRecorder()
	router.ServeHTTP(response, req)
	return response
}

func TestProductsListsWhatIsForSale(t *testing.T) {
	response := send(t, httpapi.Dependencies{}, request{method: http.MethodGet, path: productsURL})

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d", response.Code)
	}
	// 값은 숫자(원), 크레딧은 글자다
	first := `{"products":[{"id":"credits-1000","name":"크레딧 1,000","price":1000,"credits":"1000"},`
	if !strings.HasPrefix(body(response), first) || strings.Count(body(response), `"id"`) != 4 {
		t.Errorf("본문 = %s", body(response))
	}
}

func TestCreateOrderAnswersCreatedForANewOrder(t *testing.T) {
	orders := &fakeOrders{order: sampleOrder(t, order.StatusPending), isNew: true}

	response := send(t, httpapi.Dependencies{Orders: orders}, request{
		method: http.MethodPost, path: ordersURL,
		body:    `{"product_id":"credits-1000"}`,
		headers: map[string]string{httpapi.IdempotencyHeader: "key-12345678"},
	})

	if response.Code != http.StatusCreated {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	want := `{"id":"` + orderID + `","product_id":"credits-1000","price":1000,"credits":"1000","status":"pending",` +
		`"failure_code":null,"created_at":"2026-03-02T09:00:00Z","expires_at":"2026-03-03T09:00:00Z","paid_at":null,` +
		`"refundable":false,"refundable_until":null,"refunded_at":null}`
	if got := body(response); got != want {
		t.Errorf("본문 = %s\n기대 = %s", got, want)
	}
	// 토큰의 주인, 본문의 상품, 머리말의 키를 그대로 넘겼다
	if orders.user.String() != testenv.UserID || orders.productID != "credits-1000" || orders.key != "key-12345678" {
		t.Errorf("서비스가 받은 것 = %v, %q, %q", orders.user, orders.productID, orders.key)
	}
}

func TestCreateOrderAnswersOKForARepeatedRequest(t *testing.T) {
	// 같은 키로 다시 온 요청이다. 새로 만들지 않았으므로 201 이 아니다
	orders := &fakeOrders{order: sampleOrder(t, order.StatusPending), isNew: false}

	response := send(t, httpapi.Dependencies{Orders: orders}, request{
		method: http.MethodPost, path: ordersURL,
		body:    `{"product_id":"credits-1000"}`,
		headers: map[string]string{httpapi.IdempotencyHeader: "key-12345678"},
	})

	if response.Code != http.StatusOK || !strings.Contains(body(response), orderID) {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestCreateOrderIgnoresPriceAndOwnerInTheBody(t *testing.T) {
	// 본문에 값이나 다른 사용자를 적어 보내도 서비스에는 상품의 번호만 간다
	orders := &fakeOrders{order: sampleOrder(t, order.StatusPending), isNew: true}

	send(t, httpapi.Dependencies{Orders: orders}, request{
		method: http.MethodPost, path: ordersURL,
		body:    `{"product_id":"credits-1000","price":1,"credits":"999999","user_id":"11111111-2222-4333-8444-555555555555"}`,
		headers: map[string]string{httpapi.IdempotencyHeader: "key-12345678"},
	})

	if orders.user.String() != testenv.UserID || orders.productID != "credits-1000" {
		t.Errorf("서비스가 받은 것 = %v, %q", orders.user, orders.productID)
	}
}

func TestOrderErrorsBecomeStatusCodes(t *testing.T) {
	cases := []struct {
		name string
		err  error
		want int
	}{
		{"키의 모양이 틀렸다", order.ErrInvalidKey, http.StatusBadRequest},
		{"없는 상품", order.ErrUnknownProduct, http.StatusBadRequest},
		{"결제 번호의 모양이 틀렸다", order.ErrInvalidPaymentKey, http.StatusBadRequest},
		{"없는 주문", order.ErrNotFound, http.StatusNotFound},
		{"같은 키로 다른 주문", order.ErrKeyReused, http.StatusConflict},
		{"다른 결제 번호", order.ErrPaymentKeyMismatch, http.StatusConflict},
		{"이미 쓰인 결제 번호", order.ErrPaymentKeyUsed, http.StatusConflict},
		{"만료된 주문", order.ErrExpired, http.StatusConflict},
		{"치른 주문이 아니다", order.ErrNotRefundable, http.StatusConflict},
		{"7일이 지났다", order.ErrRefundWindowClosed, http.StatusConflict},
		{"크레딧을 썼다", order.ErrCreditsUsed, http.StatusConflict},
		{"다른 요청과 엇갈렸다", order.ErrRefundBusy, http.StatusConflict},
		{"결제 대행사가 취소를 거절했다", fmt.Errorf("%w(REJECT_CARD_PAYMENT)", order.ErrRefundRefused), http.StatusConflict},
		// 작업의 마감에 걸렸다(#273). 결제를 실패로 정한 것이 아니다. 다시 보내면 된다. 감싼 원인(DB 의 오류)은 싣지 않는다
		{"정한 시간이 지났다", errors.Join(order.ErrTimedOut, errors.New(`relation "orders" does not exist`)), http.StatusServiceUnavailable},
		{"DB 오류", errors.New(`relation "orders" does not exist`), http.StatusInternalServerError},
	}
	requests := []request{
		{method: http.MethodPost, path: ordersURL, body: `{"product_id":"x"}`},
		{method: http.MethodGet, path: ordersURL + "/" + orderID},
		{method: http.MethodPost, path: ordersURL + "/" + orderID + "/confirm", body: `{"payment_key":"x"}`},
		{method: http.MethodPost, path: ordersURL + "/" + orderID + "/refund"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			for _, r := range requests {
				response := send(t, httpapi.Dependencies{Orders: &fakeOrders{err: tc.err}}, r)

				if response.Code != tc.want || !strings.Contains(body(response), `"detail"`) {
					t.Errorf("%s %s: 상태 코드 = %d, 본문 = %s. 기대 = %d", r.method, r.path, response.Code, body(response), tc.want)
				}
				// DB 의 오류는 응답에 싣지 않는다
				if strings.Contains(body(response), "relation") {
					t.Errorf("응답에 DB 의 오류가 실렸다: %s", body(response))
				}
			}
		})
	}
}

func TestOrderAddressesNeedAToken(t *testing.T) {
	requests := []request{
		{method: http.MethodGet, path: productsURL},
		{method: http.MethodPost, path: ordersURL, body: `{"product_id":"credits-1000"}`},
		{method: http.MethodGet, path: ordersURL + "/" + orderID},
		{method: http.MethodPost, path: ordersURL + "/" + orderID + "/confirm", body: `{"payment_key":"fake_ok_1"}`},
		{method: http.MethodPost, path: ordersURL + "/" + orderID + "/refund"},
	}
	for _, r := range requests {
		orders := &fakeOrders{}
		r.anonymous = true

		response := send(t, httpapi.Dependencies{Orders: orders}, r)

		assertUnauthorized(t, response)
		if orders.calls != 0 {
			t.Errorf("%s %s: 토큰이 없는데 주문 서비스를 불렀다", r.method, r.path)
		}
	}
}

func TestBadBodiesAreRejectedBeforeTheService(t *testing.T) {
	bodies := map[string]string{
		"비었다":        "",
		"JSON 이 아니다": "product_id=credits-1000",
		"잘린 JSON":    `{"product_id":"credits-1000"`,
		"타입이 다르다":    `{"product_id":1000,"payment_key":1000}`,
		"배열이다":       `["credits-1000"]`,
		"너무 크다":      `{"product_id":"` + strings.Repeat("x", 20<<10) + `"}`,
	}
	paths := []string{ordersURL, ordersURL + "/" + orderID + "/confirm"}
	for name, text := range bodies {
		t.Run(name, func(t *testing.T) {
			for _, path := range paths {
				orders := &fakeOrders{}

				response := send(t, httpapi.Dependencies{Orders: orders}, request{method: http.MethodPost, path: path, body: text})

				if response.Code != http.StatusBadRequest || orders.calls != 0 {
					t.Errorf("%s: 상태 코드 = %d, 서비스를 부른 횟수 = %d", path, response.Code, orders.calls)
				}
			}
		})
	}
}

func TestGetOrderReturnsTheOrder(t *testing.T) {
	paidAt := time.Date(2026, 3, 2, 9, 5, 0, 0, time.UTC)
	paid := sampleOrder(t, order.StatusPaid)
	paid.PaidAt = &paidAt
	orders := &fakeOrders{order: paid}

	response := send(t, httpapi.Dependencies{Orders: orders}, request{method: http.MethodGet, path: ordersURL + "/" + orderID})

	if response.Code != http.StatusOK || !strings.Contains(body(response), `"status":"paid"`) ||
		!strings.Contains(body(response), `"paid_at":"2026-03-02T09:05:00Z"`) {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	if orders.user.String() != testenv.UserID || orders.orderID.String() != orderID {
		t.Errorf("서비스가 받은 것 = %v, %v", orders.user, orders.orderID)
	}
	// 결제 번호는 응답에 싣지 않는다
	if strings.Contains(body(response), "payment_key") {
		t.Errorf("응답에 결제 번호가 실렸다: %s", body(response))
	}
}

func TestAMalformedOrderIDIsNotFound(t *testing.T) {
	for _, suffix := range []string{"/not-a-uuid", "/123", "/not-a-uuid/confirm", "/not-a-uuid/refund"} {
		orders := &fakeOrders{}
		method := http.MethodGet
		if strings.HasSuffix(suffix, "/confirm") || strings.HasSuffix(suffix, "/refund") {
			method = http.MethodPost
		}

		response := send(t, httpapi.Dependencies{Orders: orders}, request{method: method, path: ordersURL + suffix, body: `{"payment_key":"x"}`})

		if response.Code != http.StatusNotFound || orders.calls != 0 {
			t.Errorf("%s: 상태 코드 = %d, 서비스를 부른 횟수 = %d", suffix, response.Code, orders.calls)
		}
	}
}

func TestConfirmAnswersByTheOrdersStatus(t *testing.T) {
	failed := sampleOrder(t, order.StatusFailed)
	failed.FailureCode = "card_declined"
	cases := []struct {
		name     string
		order    order.Order
		want     int
		contains string
	}{
		{"승인되었다", sampleOrder(t, order.StatusPaid), http.StatusOK, `"status":"paid"`},
		// 거절도 요청이 잘 처리된 것이다. 결과는 본문의 status 로 안다
		{"거절되었다", failed, http.StatusOK, `"status":"failed","failure_code":"card_declined"`},
		// 아직 결과를 모른다. 받기는 했으니 202 다
		{"결과를 모른다", sampleOrder(t, order.StatusConfirming), http.StatusAccepted, `"status":"confirming"`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			orders := &fakeOrders{order: tc.order}

			response := send(t, httpapi.Dependencies{Orders: orders}, request{
				method: http.MethodPost, path: ordersURL + "/" + orderID + "/confirm", body: `{"payment_key":"fake_ok_1"}`,
			})

			if response.Code != tc.want || !strings.Contains(body(response), tc.contains) {
				t.Errorf("상태 코드 = %d, 본문 = %s. 기대 = %d, %s", response.Code, body(response), tc.want, tc.contains)
			}
			if orders.user.String() != testenv.UserID || orders.orderID.String() != orderID || orders.paymentKey != "fake_ok_1" {
				t.Errorf("서비스가 받은 것 = %v, %v, %q", orders.user, orders.orderID, orders.paymentKey)
			}
		})
	}
}

func TestRefundAnswersByTheOrdersStatus(t *testing.T) {
	refundedAt := time.Date(2026, 3, 3, 10, 0, 0, 0, time.UTC)
	refunded := sampleOrder(t, order.StatusRefunded)
	refunded.RefundedAt = &refundedAt
	cases := []struct {
		name     string
		order    order.Order
		want     int
		contains string
	}{
		{"환불되었다", refunded, http.StatusOK, `"status":"refunded"`},
		// 크레딧은 뺐고 결제 대행사의 답을 아직 모른다. 받기는 했으니 202 다
		{"결과를 모른다", sampleOrder(t, order.StatusRefunding), http.StatusAccepted, `"status":"refunding"`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			orders := &fakeOrders{order: tc.order}

			// 본문이 있어도 읽지 않는다. 금액이나 이유를 받지 않는다
			response := send(t, httpapi.Dependencies{Orders: orders}, request{
				method: http.MethodPost, path: ordersURL + "/" + orderID + "/refund", body: `{"amount":1}`,
			})

			if response.Code != tc.want || !strings.Contains(body(response), tc.contains) {
				t.Errorf("상태 코드 = %d, 본문 = %s. 기대 = %d, %s", response.Code, body(response), tc.want, tc.contains)
			}
			if orders.user.String() != testenv.UserID || orders.orderID.String() != orderID {
				t.Errorf("서비스가 받은 것 = %v, %v", orders.user, orders.orderID)
			}
		})
	}
}

func TestTheOrderShowsWhetherItCanBeRefunded(t *testing.T) {
	paidAt := time.Date(2026, 3, 2, 9, 5, 0, 0, time.UTC)
	until := paidAt.Add(order.RefundWindow)
	refundedAt := time.Date(2026, 3, 3, 10, 0, 0, 0, time.UTC)
	refundable := sampleOrder(t, order.StatusPaid)
	refundable.PaidAt, refundable.RefundableUntil, refundable.Refundable = &paidAt, &until, true
	used := refundable
	used.Refundable = false
	refunded := sampleOrder(t, order.StatusRefunded)
	refunded.PaidAt, refunded.RefundableUntil, refunded.RefundedAt = &paidAt, &until, &refundedAt
	cases := []struct {
		name  string
		order order.Order
		want  string
	}{
		{"청약철회할 수 있다", refundable, `"refundable":true,"refundable_until":"2026-03-09T09:05:00Z","refunded_at":null`},
		{"크레딧을 썼다", used, `"refundable":false,"refundable_until":"2026-03-09T09:05:00Z","refunded_at":null`},
		{"치르지 않았다", sampleOrder(t, order.StatusPending), `"refundable":false,"refundable_until":null,"refunded_at":null`},
		{"환불되었다", refunded, `"refundable":false,"refundable_until":"2026-03-09T09:05:00Z","refunded_at":"2026-03-03T10:00:00Z"`},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			response := send(t, httpapi.Dependencies{Orders: &fakeOrders{order: tc.order}}, request{
				method: http.MethodGet, path: ordersURL + "/" + orderID,
			})

			if response.Code != http.StatusOK || !strings.Contains(body(response), tc.want) {
				t.Errorf("상태 코드 = %d, 본문 = %s. 기대 = %s", response.Code, body(response), tc.want)
			}
		})
	}
}
