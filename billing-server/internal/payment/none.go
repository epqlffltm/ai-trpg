// billing-server/internal/payment/none.go

package payment

import (
	"context"
	"errors"
)

// ErrNoProvider 는 결제 대행사를 두지 않은 프로세스가 결제 대행사를 불렀다는 오류다. 코드의 잘못이다.
var ErrNoProvider = errors.New("이 프로세스에는 결제 대행사가 없습니다")

// None 은 결제 대행사를 부르지 않는 프로세스(정리 작업)가 자리를 채우는 결제 대행사다. 어느 것을 불러도 ErrNoProvider 다.
//
// 주문 서비스는 결제 대행사 없이 만들 수 없다(order.NewService). 정리 작업은 만료된 pending 주문을 DB 에서만 끝내고
// 결제 대행사를 부르지 않는다. 그래서 키를 받지 않고 이것을 끼운다. 잘못 불리면 가짜처럼 답하지 않고 오류를 낸다.
// 가짜(Fake)를 끼우면 잘못 불렸을 때 "승인됨" 같은 답으로 원장이 바뀐다.
type None struct{}

// Confirm 은 ErrNoProvider 다.
func (None) Confirm(context.Context, Request) (Result, error) { return Result{}, ErrNoProvider }

// Cancel 은 ErrNoProvider 다.
func (None) Cancel(context.Context, Request) (Result, error) { return Result{}, ErrNoProvider }

// Lookup 은 ErrNoProvider 다.
func (None) Lookup(context.Context, Request) (Result, error) { return Result{}, ErrNoProvider }
