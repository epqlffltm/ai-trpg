// billing-server/internal/order/create_test.go

package order_test

import (
	"errors"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/order"
)

func TestCreateMakesAPendingOrderFromTheCatalog(t *testing.T) {
	f := setUp(t, approving())

	created, isNew, err := f.service.Create(ctx(t), f.user, productID, newKey())

	if err != nil || !isNew {
		t.Fatalf("주문을 만들지 못했다: %v, 새로 만듦 = %v", err, isNew)
	}
	// 값과 크레딧의 양은 상품 목록에서 온다
	if created.ID == uuid.Nil || created.UserID != f.user || created.ProductID != productID ||
		created.Price != price || created.Credits != credits {
		t.Errorf("주문 = %+v", created)
	}
	if created.Status != order.StatusPending || created.PaymentKey != "" || created.FailureCode != "" || created.PaidAt != nil {
		t.Errorf("새 주문이 pending 의 모양이 아니다: %+v", created)
	}
	if !created.CreatedAt.Equal(startedAt) {
		t.Errorf("만든 시각 = %v, 기대 = %v", created.CreatedAt, startedAt)
	}
	// 돌려준 것과 DB 에 적힌 것이 같다. 주문을 만드는 것만으로는 결제 대행사를 부르지 않는다
	if stored := f.stored(created.ID); stored.Status != order.StatusPending || stored.Price != price || stored.Credits != credits {
		t.Errorf("DB 의 주문 = %+v", stored)
	}
	if confirms, lookups := f.provider.calls(); confirms+lookups != 0 {
		t.Error("주문을 만들었을 뿐인데 결제 대행사를 불렀다")
	}
	f.wantPaidCredits(0, 0)
}

func TestCreateWithTheSameKeyReturnsTheFirstOrder(t *testing.T) {
	f := setUp(t, approving())
	key := newKey()
	first, _, err := f.service.Create(ctx(t), f.user, productID, key)
	if err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}

	second, isNew, err := f.service.Create(ctx(t), f.user, productID, key)

	if err != nil || isNew || second.ID != first.ID {
		t.Errorf("다시 보낸 요청 = %v, 새로 만듦 = %v, %v. 먼저 만든 주문 %v 이어야 한다", second.ID, isNew, err, first.ID)
	}
	if f.count() != 1 {
		t.Errorf("주문이 %d 개다", f.count())
	}
}

func TestCreateWithTheSameKeyStillReturnsTheOrderAfterItIsPaid(t *testing.T) {
	// 치른 뒤에 다시 와도 새 주문을 만들지 않는다. 지금의 상태를 돌려준다
	f := setUp(t, approving())
	key := newKey()
	first, _, _ := f.service.Create(ctx(t), f.user, productID, key)
	f.confirm(first.ID, newPaymentKey())

	again, isNew, err := f.service.Create(ctx(t), f.user, productID, key)

	if err != nil || isNew || again.ID != first.ID || again.Status != order.StatusPaid {
		t.Errorf("다시 보낸 요청 = %+v, 새로 만듦 = %v, %v", again, isNew, err)
	}
}

func TestCreateRefusesAKeyReusedForADifferentProduct(t *testing.T) {
	f := setUp(t, approving())
	key := newKey()
	if _, _, err := f.service.Create(ctx(t), f.user, productID, key); err != nil {
		t.Fatalf("주문을 만들지 못했다: %v", err)
	}

	_, _, err := f.service.Create(ctx(t), f.user, "credits-5000", key)

	if !errors.Is(err, order.ErrKeyReused) {
		t.Errorf("오류 = %v. ErrKeyReused 이어야 한다", err)
	}
	if f.count() != 1 {
		t.Errorf("주문이 %d 개다", f.count())
	}
}

func TestKeysBelongToEachUser(t *testing.T) {
	// 두 사용자가 우연히 같은 키를 써도 서로의 주문이 되지 않는다
	f := setUp(t, approving())
	other := setUp(t, approving())
	key := newKey()

	mine, _, errMine := f.service.Create(ctx(t), f.user, productID, key)
	theirs, isNew, errTheirs := other.service.Create(ctx(t), other.user, productID, key)

	if errMine != nil || errTheirs != nil || !isNew || mine.ID == theirs.ID || theirs.UserID != other.user {
		t.Errorf("내 주문 %v, 남의 주문 %+v (새로 만듦 = %v): %v, %v", mine.ID, theirs, isNew, errMine, errTheirs)
	}
}

func TestCreateRejectsUnknownProducts(t *testing.T) {
	f := setUp(t, approving())

	for _, id := range []string{"", "credits-1", "credits-1000; DROP TABLE orders"} {
		if _, _, err := f.service.Create(ctx(t), f.user, id, newKey()); !errors.Is(err, order.ErrUnknownProduct) {
			t.Errorf("상품 %q 의 오류 = %v. ErrUnknownProduct 이어야 한다", id, err)
		}
	}
	if f.count() != 0 {
		t.Error("거절했는데 주문이 생겼다")
	}
}

func TestCreateRejectsBadKeys(t *testing.T) {
	f := setUp(t, approving())
	keys := map[string]string{
		"비었다":    "",
		"너무 짧다":  "short-7",
		"너무 길다":  strings.Repeat("k", 129),
		"빈칸":     "key with spaces",
		"줄 바꿈":   "key-12345\nkey",
		"한글":     "키-12345678",
		"따옴표":    `key-"12345678"`,
		"앞뒤의 빈칸": " key-12345678 ",
	}
	for name, key := range keys {
		t.Run(name, func(t *testing.T) {
			if _, _, err := f.service.Create(ctx(t), f.user, productID, key); !errors.Is(err, order.ErrInvalidKey) {
				t.Errorf("오류 = %v. ErrInvalidKey 이어야 한다", err)
			}
		})
	}
	if f.count() != 0 {
		t.Error("거절했는데 주문이 생겼다")
	}
}

func TestCreateAcceptsTheShortestAndLongestKeys(t *testing.T) {
	f := setUp(t, approving())
	// 사용자가 테스트마다 새것이라 정해 둔 키를 써도 다른 테스트와 부딪치지 않는다
	for _, key := range []string{"k2345678", strings.Repeat("K", 128), "a-b_c-D_9"} {
		if _, isNew, err := f.service.Create(ctx(t), f.user, productID, key); err != nil || !isNew {
			t.Errorf("키 %q: %v, 새로 만듦 = %v", key, err, isNew)
		}
	}
}

func TestConcurrentCreatesWithOneKeyMakeOneOrder(t *testing.T) {
	f := setUp(t, approving())
	key := newKey()
	const n = 20
	ids := make([]uuid.UUID, n)
	fresh := make([]bool, n)
	errs := make([]error, n)

	start := make(chan struct{})
	var done sync.WaitGroup
	for index := range n {
		done.Add(1)
		go func() {
			defer done.Done()
			<-start
			created, isNew, err := f.service.Create(ctx(t), f.user, productID, key)
			ids[index], fresh[index], errs[index] = created.ID, isNew, err
		}()
	}
	close(start)
	done.Wait()

	made := 0
	for index := range n {
		if errs[index] != nil || ids[index] != ids[0] {
			t.Errorf("%d 번째: 주문 %v, %v. 모두 같은 주문이어야 한다", index, ids[index], errs[index])
		}
		if fresh[index] {
			made++
		}
	}
	// 새로 만들었다고 답한 요청은 하나뿐이다
	if made != 1 || f.count() != 1 {
		t.Errorf("새로 만들었다는 답이 %d 번, 주문이 %d 개다. 둘 다 1 이어야 한다", made, f.count())
	}
}

func TestGetReturnsOnlyTheUsersOwnOrder(t *testing.T) {
	f := setUp(t, approving())
	created := f.create()

	mine, err := f.service.Get(ctx(t), f.user, created.ID)
	if err != nil || mine.ID != created.ID || mine.Status != order.StatusPending {
		t.Errorf("내 주문 = %+v, %v", mine, err)
	}
	// 남의 주문은 없는 주문과 같은 답이다. 그런 주문이 있다는 것도 알려 주지 않는다
	if _, err := f.service.Get(ctx(t), uuid.New(), created.ID); !errors.Is(err, order.ErrNotFound) {
		t.Errorf("남의 주문의 오류 = %v. ErrNotFound 이어야 한다", err)
	}
	if _, err := f.service.Get(ctx(t), f.user, uuid.New()); !errors.Is(err, order.ErrNotFound) {
		t.Errorf("없는 주문의 오류 = %v. ErrNotFound 이어야 한다", err)
	}
}
