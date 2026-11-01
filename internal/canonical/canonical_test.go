package canonical

import (
	"errors"
	"math"
	"math/big"
	"strings"
	"testing"
)

func TestSortedCompactJSONEscapesAtEachBoundary(t *testing.T) {
	// The output of Python's json.dumps for the same string.
	const want = `"\u001f ~\u007f\uffff\ud800\udc00\b\f\"\\\n\r\t/<>&"`
	out, err := SortedCompactJSON("\x1f ~\x7f\uffff\U00010000\b\f\"\\\n\r\t/<>&")
	if err != nil || string(out) != want {
		t.Errorf("SortedCompactJSON = %s, %v; want %s", out, err, want)
	}
}

func TestSortedCompactJSONValueModel(t *testing.T) {
	limit := new(big.Int).Sub(new(big.Int).Exp(big.NewInt(10), big.NewInt(maxIntegerDigits), nil), big.NewInt(1))
	tests := []struct {
		name string
		in   any
		want string
	}{
		{"int", map[string]any{"a": 7, "b": int64(-8)}, `{"a":7,"b":-8}`},
		{"literals", []any{nil, true, false}, `[null,true,false]`},
		{"big integer at the digit limit", limit, limit.String()},
		{"negative zero integer", big.NewInt(0), `0`},
	}
	for _, tt := range tests {
		if out, err := SortedCompactJSON(tt.in); err != nil || string(out) != tt.want {
			t.Errorf("%s: SortedCompactJSON = %s, %v; want %s", tt.name, out, err, tt.want)
		}
	}
}

func TestEncodersRejectValuesOutsideTheModel(t *testing.T) {
	var nilInt *big.Int
	tests := []struct {
		name string
		in   any
		want error
	}{
		{"unsupported type", float32(1), errUnsupportedType},
		{"unsupported slice", []string{"a"}, errUnsupportedType},
		{"nil integer", nilInt, errNilInteger},
		{"invalid UTF-8 string", "\xff", errInvalidUTF8},
		{"invalid UTF-8 name", map[string]any{"\xff": 1}, errInvalidUTF8},
		{"error in an array", []any{1, float32(1)}, errUnsupportedType},
		{"error in a member", map[string]any{"a": float32(1)}, errUnsupportedType},
	}
	for _, tt := range tests {
		if _, err := SortedCompactJSON(tt.in); !errors.Is(err, tt.want) {
			t.Errorf("%s: SortedCompactJSON error = %v, want %v", tt.name, err, tt.want)
		}
		if _, err := RFC8785(tt.in); !errors.Is(err, tt.want) {
			t.Errorf("%s: RFC8785 error = %v, want %v", tt.name, err, tt.want)
		}
	}
	tooLong := new(big.Int).Exp(big.NewInt(10), big.NewInt(maxIntegerDigits), nil)
	if _, err := SortedCompactJSON(tooLong); !errors.Is(err, errIntegerTooLong) {
		t.Errorf("SortedCompactJSON(10^4300) error = %v, want %v", err, errIntegerTooLong)
	}
}

func TestRFC8785IntegerRange(t *testing.T) {
	tests := []struct {
		in   any
		want string // "" for a rejection
	}{
		{int64(maxSafeInteger), "9007199254740991"},
		{int64(-maxSafeInteger), "-9007199254740991"},
		{int64(maxSafeInteger + 1), ""},
		{int64(-maxSafeInteger - 1), ""},
		{maxSafeInteger, "9007199254740991"},
		{maxSafeInteger + 1, ""},
		{big.NewInt(maxSafeInteger), "9007199254740991"},
		{big.NewInt(-maxSafeInteger), "-9007199254740991"},
		{big.NewInt(maxSafeInteger + 1), ""},
		{big.NewInt(-maxSafeInteger - 1), ""},
	}
	for _, tt := range tests {
		out, err := RFC8785(tt.in)
		if tt.want == "" {
			if !errors.Is(err, errUnsafeInteger) {
				t.Errorf("RFC8785(%v) error = %v, want %v", tt.in, err, errUnsafeInteger)
			}
			continue
		}
		if err != nil || string(out) != tt.want {
			t.Errorf("RFC8785(%v) = %s, %v; want %s", tt.in, out, err, tt.want)
		}
	}
}

func TestRFC8785RejectsNonFiniteFloats(t *testing.T) {
	for _, f := range []float64{math.NaN(), math.Inf(1), math.Inf(-1)} {
		if _, err := RFC8785(f); !errors.Is(err, errNonFinite) {
			t.Errorf("RFC8785(%v) error = %v, want %v", f, err, errNonFinite)
		}
	}
}

func TestRFC8785ReportsATransformError(t *testing.T) {
	// The library rejects nesting deeper than 10000 levels.
	var v any = []any{}
	for range 10001 {
		v = []any{v}
	}
	if _, err := RFC8785(v); !errors.Is(err, errTransform) {
		t.Errorf("RFC8785 error = %v, want %v", err, errTransform)
	}
}

func TestDecodeStrictNumbers(t *testing.T) {
	tests := []struct {
		in   string
		want any
	}{
		{"9223372036854775807", int64(math.MaxInt64)},
		{"-0", int64(0)},
		{"1e2", 100.0},
		{"1.5", 1.5},
		{"1e-400", 0.0},
	}
	for _, tt := range tests {
		if v, err := DecodeStrict([]byte(tt.in)); err != nil || v != tt.want {
			t.Errorf("DecodeStrict(%s) = %v, %v; want %v", tt.in, v, err, tt.want)
		}
	}
	v, err := DecodeStrict([]byte("9223372036854775808"))
	if n, ok := v.(*big.Int); err != nil || !ok || n.String() != "9223372036854775808" {
		t.Errorf("DecodeStrict(2^63) = %v, %v; want a *big.Int", v, err)
	}
}

func TestDecodeStrictRejections(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want error // nil for a syntax error
	}{
		{"empty", "", errNoValue},
		{"white space", " \n", errNoValue},
		{"overflow", "1e400", errNumberRange},
		{"overflow in an array", "[1, -1e309]", errNumberRange},
		{"trailing value", "1 2", errTrailingData},
		{"trailing garbage", "1 x", nil},
		{"truncated array", "[1,", nil},
		{"truncated object", `{"a":1`, nil},
		{"duplicate name", `{"a":1,"a":2}`, nil},
		{"constant", "NaN", nil},
		{"invalid name", `{1:2}`, nil},
	}
	for _, tt := range tests {
		_, err := DecodeStrict([]byte(tt.in))
		if err == nil || (tt.want != nil && !errors.Is(err, tt.want)) {
			t.Errorf("%s: DecodeStrict error = %v, want %v", tt.name, err, tt.want)
		}
	}
}

func TestDecodeStrictErrorsHoldNoInput(t *testing.T) {
	for _, in := range []string{`{"secret-name":1,"secret-name":2}`, `{"secret-name":1} "secret-value"`, `{"secret-name":secret}`} {
		_, err := DecodeStrict([]byte(in))
		if err == nil || strings.Contains(err.Error(), "secret") {
			t.Errorf("DecodeStrict error = %v, want an error without the input", err)
		}
	}
}
