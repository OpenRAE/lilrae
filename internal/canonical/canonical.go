// Package canonical encodes JSON values in the canonical forms that records
// store, hash, and sign, and it decodes strict JSON.
//
// The encoders take, and DecodeStrict returns, a JSON value as nil, bool,
// string, int, int64, [*big.Int], float64, []any, or map[string]any. An integer
// and a float are different values, as in Python: 1 and 1.0 encode
// differently. Each function implements one scheme of the serialization
// vectors in conformance/testdata/vectors. An error names the rule that the
// input breaks, and not the input, because the input can hold a secret.
package canonical

import (
	"errors"
	"math/big"
	"strings"
)

// maxIntegerDigits is the longest integer, in decimal digits, that Python
// converts to or from text by default (sys.get_int_max_str_digits).
const maxIntegerDigits = 4300

var (
	errInvalidUTF8     = errors.New("canonical: a string is not valid UTF-8")
	errIntegerTooLong  = errors.New("canonical: an integer has more than 4300 digits")
	errNilInteger      = errors.New("canonical: a *big.Int is nil")
	errNonFinite       = errors.New("canonical: the form has no text for NaN or an infinity")
	errUnsupportedType = errors.New("canonical: a value has a type outside the JSON value model")
)

// tooManyDigits reports whether the decimal text of an integer, with an
// optional minus sign, has more digits than Python reads or writes.
func tooManyDigits(text string) bool {
	return len(strings.TrimPrefix(text, "-")) > maxIntegerDigits
}

// integerText returns the decimal text of n, within the digit limit.
func integerText(n *big.Int) (string, error) {
	if n == nil {
		return "", errNilInteger
	}
	text := n.Text(10)
	if tooManyDigits(text) {
		return "", errIntegerTooLong
	}
	return text, nil
}

// appendArray writes items as a JSON array with no white space, with each
// item in the form that appendValue writes.
func appendArray(b []byte, items []any, appendValue func([]byte, any) ([]byte, error)) ([]byte, error) {
	b = append(b, '[')
	for i, item := range items {
		if i > 0 {
			b = append(b, ',')
		}
		var err error
		if b, err = appendValue(b, item); err != nil {
			return nil, err
		}
	}
	return append(b, ']'), nil
}
