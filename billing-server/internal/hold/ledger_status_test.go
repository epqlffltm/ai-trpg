// billing-server/internal/hold/ledger_status_test.go

// 원장의 홀드 줄에 그 홀드의 지금 상태가 붙는지 본다(#430). 실제 홀드 서비스와 지갑으로 돈다.
// 확정은 원장에 줄을 남기지 않으므로, 화면은 이 상태로 hold 줄이 기다리는지, 쓰였는지, 돌아왔는지 안다.
package hold_test

import (
	"testing"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

// statusesByReason 은 이 사용자의 원장에서 이유마다 붙은 홀드의 상태들이다. 최근 줄부터다.
func (f fixture) statusesByReason() map[wallet.Reason][]wallet.HoldStatus {
	f.t.Helper()
	page, err := f.wallet.Entries(ctx(f.t), f.user, wallet.FirstPage, wallet.MaxPageSize)
	if err != nil {
		f.t.Fatalf("원장을 읽지 못했다: %v", err)
	}
	statuses := map[wallet.Reason][]wallet.HoldStatus{}
	for _, entry := range page.Entries {
		statuses[entry.Reason] = append(statuses[entry.Reason], entry.HoldStatus)
	}
	return statuses
}

// sameStatuses 는 두 목록이 같은 차례의 같은 상태인지 본다.
func sameStatuses(got []wallet.HoldStatus, want ...wallet.HoldStatus) bool {
	if len(got) != len(want) {
		return false
	}
	for index := range want {
		if got[index] != want[index] {
			return false
		}
	}
	return true
}

func TestAHoldLineSaysTheHoldIsStillWaiting(t *testing.T) {
	f := setUp(t)
	f.fund(100, 30)
	f.place(newReference())

	got := f.statusesByReason()

	// 무료 30 과 산 것 20 에서 한 줄씩 뺐다. 두 줄 다 기다린다
	if !sameStatuses(got[wallet.ReasonHold], wallet.HoldHeld, wallet.HoldHeld) {
		t.Errorf("hold 줄 = %v", got[wallet.ReasonHold])
	}
	// 홀드의 줄이 아니면 상태가 없다
	if !sameStatuses(got[wallet.ReasonDeposit], "") || !sameStatuses(got[wallet.ReasonGrant], "") {
		t.Errorf("deposit = %v, grant = %v. 비어 있어야 한다", got[wallet.ReasonDeposit], got[wallet.ReasonGrant])
	}
}

func TestACapturedHoldLineSaysTheCreditsWereUsed(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)

	if _, err := f.service.Capture(ctx(t), source, reference); err != nil {
		t.Fatalf("확정하지 못했다: %v", err)
	}

	// 확정은 줄을 더하지 않는다. 있던 hold 줄의 상태가 바뀐다
	if got := f.statusesByReason(); !sameStatuses(got[wallet.ReasonHold], wallet.HoldCaptured) {
		t.Errorf("hold 줄 = %v", got[wallet.ReasonHold])
	}
}

func TestAReleasedHoldMarksBothItsLines(t *testing.T) {
	f := setUp(t)
	f.fund(100, 0)
	reference := newReference()
	f.place(reference)

	if _, err := f.service.Release(ctx(t), source, reference); err != nil {
		t.Fatalf("돌려주지 못했다: %v", err)
	}

	got := f.statusesByReason()
	if !sameStatuses(got[wallet.ReasonHold], wallet.HoldReleased) || !sameStatuses(got[wallet.ReasonRelease], wallet.HoldReleased) {
		t.Errorf("hold = %v, release = %v", got[wallet.ReasonHold], got[wallet.ReasonRelease])
	}
}

func TestEachHoldLineHasItsOwnHoldsStatus(t *testing.T) {
	f := setUp(t)
	f.fund(200, 0)
	waiting, captured := newReference(), newReference()
	f.place(waiting)
	f.place(captured)

	if _, err := f.service.Capture(ctx(t), source, captured); err != nil {
		t.Fatalf("확정하지 못했다: %v", err)
	}

	// 최근 줄부터다. 나중에 건 홀드(확정)가 먼저 온다
	if got := f.statusesByReason(); !sameStatuses(got[wallet.ReasonHold], wallet.HoldCaptured, wallet.HoldHeld) {
		t.Errorf("hold 줄 = %v", got[wallet.ReasonHold])
	}
}
