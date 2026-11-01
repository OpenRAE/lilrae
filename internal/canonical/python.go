package canonical

import (
	"maps"
	"math"
	"math/big"
	"slices"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

// SortedCompactJSON returns the bytes of the sorted-compact-json scheme: the
// output of Python's json.dumps(v, sort_keys=True, separators=(',', ':')).
// It sorts member names by code point, escapes each character outside U+0020
// to U+007E, writes floats as Python does, and writes NaN, Infinity, and
// -Infinity for the non-finite floats.
func SortedCompactJSON(v any) ([]byte, error) {
	return pythonForm{ascii: true, nonFinite: true}.append(nil, v)
}

// SortedCompactUTF8JSON returns the output of Python's json.dumps(v,
// sort_keys=True, separators=(',', ':'), ensure_ascii=False,
// allow_nan=False): the form of SortedCompactJSON with raw UTF-8 text, and
// with no text for a non-finite float. The runtime-evidence-json vectors
// define its bytes.
func SortedCompactUTF8JSON(v any) ([]byte, error) {
	return pythonForm{}.append(nil, v)
}

// pythonForm is one form of Python's json.dumps with sort_keys=True and
// separators=(',', ':').
type pythonForm struct {
	// ascii escapes each character outside U+0020 to U+007E, as
	// ensure_ascii=True does. Otherwise only control characters are escaped.
	ascii bool
	// nonFinite writes NaN, Infinity, and -Infinity, as allow_nan=True does.
	// Otherwise the form rejects a non-finite float.
	nonFinite bool
}

func (f pythonForm) append(b []byte, v any) ([]byte, error) {
	switch v := v.(type) {
	case nil:
		return append(b, "null"...), nil
	case bool:
		return strconv.AppendBool(b, v), nil
	case string:
		return f.appendString(b, v)
	case int:
		return strconv.AppendInt(b, int64(v), 10), nil
	case int64:
		return strconv.AppendInt(b, v, 10), nil
	case *big.Int:
		text, err := integerText(v)
		if err != nil {
			return nil, err
		}
		return append(b, text...), nil
	case float64:
		if !f.nonFinite && (math.IsNaN(v) || math.IsInf(v, 0)) {
			return nil, errNonFinite
		}
		return append(b, pythonFloat(v)...), nil
	case []any:
		return appendArray(b, v, f.append)
	case map[string]any:
		return f.appendObject(b, v)
	default:
		return nil, errUnsupportedType
	}
}

func (f pythonForm) appendObject(b []byte, members map[string]any) ([]byte, error) {
	// The byte order of valid UTF-8 is the code point order that Python sorts by.
	names := slices.Sorted(maps.Keys(members))
	b = append(b, '{')
	for i, name := range names {
		if i > 0 {
			b = append(b, ',')
		}
		var err error
		if b, err = f.appendString(b, name); err != nil {
			return nil, err
		}
		b = append(b, ':')
		if b, err = f.append(b, members[name]); err != nil {
			return nil, err
		}
	}
	return append(b, '}'), nil
}

func (f pythonForm) appendString(b []byte, s string) ([]byte, error) {
	if !utf8.ValidString(s) {
		return nil, errInvalidUTF8
	}
	b = append(b, '"')
	for _, r := range s {
		switch r {
		case '"':
			b = append(b, `\"`...)
		case '\\':
			b = append(b, `\\`...)
		case '\n':
			b = append(b, `\n`...)
		case '\r':
			b = append(b, `\r`...)
		case '\t':
			b = append(b, `\t`...)
		case '\b':
			b = append(b, `\b`...)
		case '\f':
			b = append(b, `\f`...)
		default:
			b = f.appendRune(b, r)
		}
	}
	return append(b, '"'), nil
}

func (f pythonForm) appendRune(b []byte, r rune) []byte {
	if r < ' ' {
		return appendUnicodeEscape(b, r)
	}
	if !f.ascii || r <= '~' {
		return utf8.AppendRune(b, r)
	}
	if r > 0xFFFF {
		high, low := utf16.EncodeRune(r)
		return appendUnicodeEscape(appendUnicodeEscape(b, high), low)
	}
	return appendUnicodeEscape(b, r)
}

func appendUnicodeEscape(b []byte, r rune) []byte {
	const hexDigits = "0123456789abcdef"
	return append(b, '\\', 'u', hexDigits[r>>12&0xF], hexDigits[r>>8&0xF], hexDigits[r>>4&0xF], hexDigits[r&0xF])
}

// pythonFloat returns the text that Python's json module writes for f. A
// finite float is its repr: the shortest text that reads back the same value.
// Python writes it in the exponent form when the decimal point of that text is
// at position -4 or lower or above 16, which for a nonzero float is the same
// as a magnitude below 1e-4 or at least 1e16. It writes the fixed form, with
// at least one fraction digit, otherwise.
func pythonFloat(f float64) string {
	if math.IsNaN(f) {
		return "NaN"
	}
	if math.IsInf(f, 1) {
		return "Infinity"
	}
	if math.IsInf(f, -1) {
		return "-Infinity"
	}
	if magnitude := math.Abs(f); f != 0 && (magnitude < 1e-4 || magnitude >= 1e16) {
		return strconv.FormatFloat(f, 'e', -1, 64)
	}
	fixed := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.Contains(fixed, ".") {
		fixed += ".0"
	}
	return fixed
}
