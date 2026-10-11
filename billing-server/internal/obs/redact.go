// billing-server/internal/obs/redact.go

package obs

import (
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// 로그 한 줄이 나가기 직전의 마지막 방어선이다. 민감한 값을 로그에 넘기지 않는 것이 먼저고,
// 이것은 그 규칙을 놓친 코드가 있어도 값이 그대로 나가지 않게 한다. 두 가지를 한다.
//   - 칸의 이름이 민감하면 값을 통째로 가린다(IsSensitiveName)
//   - 어느 칸의 글이든, 비밀로 보이는 모양(토큰, 주소에 든 비밀번호, 이메일)을 가린다(ScrubText)

const (
	// Redacted 는 가린 값의 자리에 적는 글이다.
	Redacted = "[REDACTED]"
	// MaxValueLength 는 칸 하나에 적는 글의 가장 긴 길이다. 넘으면 자른다.
	MaxValueLength = 500
	// MaxMessageLength 는 message 칸의 가장 긴 길이다.
	MaxMessageLength = 2000
	// MaxStackLength 는 stack_trace 칸의 가장 긴 길이다.
	MaxStackLength = 16000
	// truncatedMark 는 잘린 글의 끝에 붙는다.
	truncatedMark = "…"
)

// sensitiveWords 는 이름에 들어 있으면 그 칸을 가리는 단어들이다. 이름을 단어로 쪼개서 본다.
var sensitiveWords = map[string]bool{
	"password": true, "passwd": true, "secret": true, "token": true, "jwt": true,
	"authorization": true, "cookie": true, "credential": true, "credentials": true,
	"otp": true, "dsn": true, "email": true, "prompt": true,
	"card": true, "cvc": true, "cvv": true, "code": true, "signature": true,
}

// sensitivePhrases 는 이어진 두 단어로 민감한 것들이다. 단어를 밑줄로 이은 모양으로 적는다.
var sensitivePhrases = []string{
	"api_key", "private_key", "access_key", "payment_key",
	"database_url", "redis_url", "set_cookie",
}

// sensitiveNames 는 이름이 정확히 이것일 때만 가리는 것들이다. 사용자가 쓴 글의 원문이 실리는 이름이다.
var sensitiveNames = map[string]bool{
	"body": true, "content": true, "text": true, "title": true, "declaration": true,
	"memo": true, "note": true, "notes": true, "lore": true, "completion": true,
	"response": true, "headers": true, "request_body": true, "response_body": true,
}

// safeLastWords 는 이름의 마지막 단어가 이것이면 민감한 단어가 있어도 가리지 않는 것들이다.
// token_count, email_hash, code_length 는 값 자체가 아니라 그것의 수, 해시, 길이다.
var safeLastWords = map[string]bool{
	"hash": true, "masked": true, "count": true, "length": true, "version": true,
	"id": true, "ms": true, "seconds": true, "type": true,
}

// safeNames 는 민감한 단어가 들어 있어도 가리지 않는 이름이다. 공통 규격의 칸이다.
var safeNames = map[string]bool{"error_code": true, "status_code": true, "exit_code": true}

var (
	// JWT 의 모양. 점으로 이은 세 마디고 첫 마디가 eyJ 로 시작한다
	jwtPattern = regexp.MustCompile(`eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*`)
	// Authorization 머리말의 값
	authPattern = regexp.MustCompile(`(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}`)
	// 주소에 든 계정과 비밀번호(postgres://계정:비밀번호@호스트)
	userinfoPattern = regexp.MustCompile(`://[^/\s:@]+:[^@\s/]+@`)
	// 이메일 주소
	emailPattern = regexp.MustCompile(`([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})`)
)

// IsSensitiveName 은 이 이름의 칸을 가려야 하는지 본다.
func IsSensitiveName(name string) bool {
	words := splitWords(name)
	if len(words) == 0 {
		return false
	}
	joined := strings.Join(words, "_")
	if safeNames[joined] || safeLastWords[words[len(words)-1]] {
		return false
	}
	return sensitiveNames[joined] || hasSensitivePhrase(joined) || hasSensitiveWord(words)
}

// hasSensitiveWord 는 낱말들 가운데 민감한 것이 있는지 본다.
func hasSensitiveWord(words []string) bool {
	for _, word := range words {
		if sensitiveWords[word] {
			return true
		}
	}
	return false
}

// hasSensitivePhrase 는 밑줄로 이은 이름에 민감한 낱말들이 잇달아 들어 있는지 본다.
func hasSensitivePhrase(joined string) bool {
	for _, phrase := range sensitivePhrases {
		if strings.Contains(joined, phrase) {
			return true
		}
	}
	return false
}

// splitWords 는 이름을 소문자 단어들로 쪼갠다. 밑줄, 점, 붙임표, 공백과 대소문자가 바뀌는 곳에서 나눈다.
// access_token, accessToken, Access-Token 이 모두 [access token] 이 된다.
func splitWords(name string) []string {
	var words []string
	var current []rune
	flush := func() {
		if len(current) > 0 {
			words = append(words, strings.ToLower(string(current)))
			current = nil
		}
	}
	runes := []rune(name)
	for i, r := range runes {
		if r == '_' || r == '.' || r == '-' || unicode.IsSpace(r) {
			flush()
			continue
		}
		if startsNewWord(runes, i) {
			flush()
		}
		current = append(current, r)
	}
	flush()
	return words
}

// startsNewWord 는 i 번째 글자에서 새 낱말이 시작하는지 본다. 소문자나 숫자 뒤의 대문자다(accessToken 의 T).
func startsNewWord(runes []rune, i int) bool {
	if i == 0 || !unicode.IsUpper(runes[i]) {
		return false
	}
	previous := runes[i-1]
	return unicode.IsLower(previous) || unicode.IsDigit(previous)
}

// ScrubText 는 글이 limit 글자를 넘으면 자르고, 비밀로 보이는 모양을 가린다. 자르기를 먼저 한다. 긴 글 전체를 훑지 않는다.
func ScrubText(text string, limit int) string {
	text = truncate(text, limit)
	text = jwtPattern.ReplaceAllString(text, "[REDACTED_JWT]")
	text = authPattern.ReplaceAllString(text, "$1 "+Redacted)
	text = userinfoPattern.ReplaceAllString(text, "://"+Redacted+"@")
	return emailPattern.ReplaceAllString(text, "$1***@$2")
}

// truncate 는 글이 limit 글자를 넘으면 자르고 끝에 표시를 붙인다. 글자의 중간을 자르지 않는다.
func truncate(text string, limit int) string {
	if utf8.RuneCountInString(text) <= limit {
		return text
	}
	return string([]rune(text)[:limit]) + truncatedMark
}
