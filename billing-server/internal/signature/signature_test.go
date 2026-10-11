// billing-server/internal/signature/signature_test.go

package signature_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/signature"
)

const secret = "this-is-a-test-secret-of-32-chars!"

var (
	sentAt  = time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	payload = []byte("the exact bytes that were sent")
)

func TestASignedPayloadVerifies(t *testing.T) {
	header := signature.Sign(secret, sentAt, payload)

	if err := signature.Verify(secret, header, payload, sentAt); err != nil {
		t.Errorf("방금 서명한 내용을 받지 않았다: %v", err)
	}
	// 모양은 "t=<초>,v1=<16진수 64 글자>" 다. 다른 언어로 짠 서버가 같은 서명을 만들 수 있어야 한다
	stamp, mac, _ := strings.Cut(header, ",v1=")
	if stamp != "t=1772442000" || len(mac) != 64 || strings.ToLower(mac) != mac {
		t.Errorf("서명의 모양 = %q", header)
	}
}

func TestTheSignatureIsAKnownHMAC(t *testing.T) {
	// 다른 서버(파이썬으로 짠 게임 서버)가 같은 값을 만들어야 한다. 계산이 바뀌면 여기서 드러난다.
	// 값은 파이썬의 hmac.new(secret, b"1772442000.hello", hashlib.sha256).hexdigest() 다
	const want = "t=1772442000,v1=c1f7900d5bcf9ad6477841caff0a3f58979e88e8aa1fd95c3d197ae37acd04cb"

	if got := signature.Sign(secret, sentAt, []byte("hello")); got != want {
		t.Errorf("서명 = %q, 기대 = %q", got, want)
	}
}

func TestTheSignatureCoversThePayloadTheTimeAndTheSecret(t *testing.T) {
	header := signature.Sign(secret, sentAt, payload)
	later := signature.Sign(secret, sentAt.Add(time.Second), payload)
	cases := map[string]struct {
		secret  string
		header  string
		payload []byte
	}{
		"내용을 한 글자 고쳤다":   {secret, header, []byte("the exact bytes that were sent.")},
		"내용이 비었다":        {secret, header, nil},
		"비밀이 다르다":        {"another-secret-that-is-32-chars!!", header, payload},
		"시각만 바꿔 붙였다":     {secret, strings.Replace(header, "t=1772442000", "t=1772442001", 1), payload},
		"다른 시각의 서명을 붙였다": {secret, "t=1772442000," + later[strings.Index(later, "v1="):], payload},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			if err := signature.Verify(tc.secret, tc.header, tc.payload, sentAt); !errors.Is(err, signature.ErrInvalid) {
				t.Errorf("오류 = %v. ErrInvalid 이어야 한다", err)
			}
		})
	}
}

func TestTheTimeAndThePayloadCannotTradeCharacters(t *testing.T) {
	// "<시각>.<내용>" 에 서명한다. 사이의 점이 없으면 시각의 끝자리를 내용의 앞으로 옮겨도 같은 글자가 된다
	header := signature.Sign(secret, time.Unix(17724420001, 0), []byte("23"))
	moved := strings.Replace(header, "t=17724420001", "t=1772442000", 1)

	if err := signature.Verify(secret, moved, []byte("123"), sentAt); !errors.Is(err, signature.ErrInvalid) {
		t.Errorf("오류 = %v. ErrInvalid 이어야 한다", err)
	}
}

func TestAShortSecretVerifiesNothing(t *testing.T) {
	// 설정이 빠져 비밀이 비어 있으면, 같은 빈 비밀로 누구나 서명을 만들 수 있다. 그런 서명도 받지 않는다
	for _, weak := range []string{"", "short", strings.Repeat("s", signature.MinSecretLength-1)} {
		header := signature.Sign(weak, sentAt, payload)
		if err := signature.Verify(weak, header, payload, sentAt); !errors.Is(err, signature.ErrInvalid) {
			t.Errorf("길이 %d 의 비밀: 오류 = %v. ErrInvalid 이어야 한다", len(weak), err)
		}
	}
	exact := strings.Repeat("s", signature.MinSecretLength)
	if err := signature.Verify(exact, signature.Sign(exact, sentAt, payload), payload, sentAt); err != nil {
		t.Errorf("가장 짧은 길이의 비밀을 받지 않았다: %v", err)
	}
}

func TestMalformedSignaturesAreRejected(t *testing.T) {
	good := signature.Sign(secret, sentAt, payload)
	mac := good[strings.Index(good, "v1=")+3:]
	headers := map[string]string{
		"비었다":           "",
		"서명만":           "v1=" + mac,
		"시각만":           "t=1772442000",
		"순서가 바뀌었다":      "v1=" + mac + ",t=1772442000",
		"시각이 숫자가 아니다":   "t=yesterday,v1=" + mac,
		"서명이 16진수가 아니다": "t=1772442000,v1=not-hex",
		"서명이 비었다":       "t=1772442000,v1=",
		"서명이 잘렸다":       "t=1772442000,v1=" + mac[:10],
		"다른 판":          "t=1772442000,v0=" + mac,
		"빈칸이 끼었다":       "t=1772442000, v1=" + mac,
		"뒤에 더 붙었다":      good + ",v1=" + mac,
	}
	for name, header := range headers {
		t.Run(name, func(t *testing.T) {
			if err := signature.Verify(secret, header, payload, sentAt); !errors.Is(err, signature.ErrInvalid) {
				t.Errorf("오류 = %v. ErrInvalid 이어야 한다", err)
			}
		})
	}
}

func TestAnUnparsableTimeThatWasSignedIsStillRejected(t *testing.T) {
	// 비밀을 아는 쪽이 숫자가 아닌 시각에 서명했다. 서명은 맞지만 언제 것인지 알 수 없다
	for _, stamp := range []string{"", "soon", "1772442000.5", "99999999999999999999"} {
		header := "t=" + stamp + ",v1=" + macOf(stamp)
		if err := signature.Verify(secret, header, payload, sentAt); !errors.Is(err, signature.ErrInvalid) {
			t.Errorf("시각 %q: 오류 = %v. ErrInvalid 이어야 한다", stamp, err)
		}
	}
}

// macOf 는 Sign 을 거치지 않고 "<stamp>.<내용>" 의 서명을 만든다. Sign 은 숫자인 시각만 만들 수 있다.
func macOf(stamp string) string {
	hash := hmac.New(sha256.New, []byte(secret))
	hash.Write([]byte(stamp + "."))
	hash.Write(payload)
	return hex.EncodeToString(hash.Sum(nil))
}

func TestOnlyFreshSignaturesAreAccepted(t *testing.T) {
	header := signature.Sign(secret, sentAt, payload)
	cases := map[string]struct {
		now  time.Time
		want error
	}{
		"방금":                {sentAt, nil},
		"5분 뒤":              {sentAt.Add(signature.Tolerance), nil},
		"5분 1초 뒤":           {sentAt.Add(signature.Tolerance + time.Second), signature.ErrInvalid},
		"하루 뒤":              {sentAt.Add(24 * time.Hour), signature.ErrInvalid},
		"받는 쪽 시계가 5분 늦다":    {sentAt.Add(-signature.Tolerance), nil},
		"받는 쪽 시계가 5분 1초 늦다": {sentAt.Add(-signature.Tolerance - time.Second), signature.ErrInvalid},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			if err := signature.Verify(secret, header, payload, tc.now); !errors.Is(err, tc.want) {
				t.Errorf("오류 = %v, 기대 = %v", err, tc.want)
			}
		})
	}
}
