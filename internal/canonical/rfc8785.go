package canonical

import (
	"encoding/json/jsontext"
	"errors"
	"math"
	"math/big"
	"strconv"

	"github.com/gowebpki/jcs"
)

// maxSafeInteger is the largest integer that the RFC 8785 scheme accepts, as
// in the Python rfc8785 library: 2^53 - 1.
const maxSafeInteger = 9007199254740991

var (
	errUnsafeInteger = errors.New("canonical: an integer is outside the RFC 8785 range of ±(2^53 - 1)")
	errNonFinite     = errors.New("canonical: RFC 8785 has no form for NaN or an infinity")
	errTransform     = errors.New("canonical: the RFC 8785 transform rejected the value")
)

// RFC8785 returns the RFC 8785 form of v (the rfc8785 scheme). It rejects an
// integer outside ±(2^53 - 1) and each non-finite float, as the Python
// rfc8785 library does.
func RFC8785(v any) ([]byte, error) {
	text, err := appendJSON(nil, v)
	if err != nil {
		return nil, err
	}
	out, err := jcs.Transform(text)
	if err != nil {
		// The error of the library can quote the input.
		return nil, errTransform
	}
	return out, nil
}

// appendJSON writes v as JSON text in the domain of RFC 8785. The transform
// sorts the members and rewrites the strings and numbers.
func appendJSON(b []byte, v any) ([]byte, error) {
	switch v := v.(type) {
	case nil:
		return append(b, "null"...), nil
	case bool:
		return strconv.AppendBool(b, v), nil
	case string:
		out, err := jsontext.AppendQuote(b, v)
		if err != nil {
			return nil, errInvalidUTF8
		}
		return out, nil
	case int:
		return appendSafeInteger(b, int64(v))
	case int64:
		return appendSafeInteger(b, v)
	case *big.Int:
		if v == nil {
			return nil, errNilInteger
		}
		if !v.IsInt64() {
			return nil, errUnsafeInteger
		}
		return appendSafeInteger(b, v.Int64())
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return nil, errNonFinite
		}
		return strconv.AppendFloat(b, v, 'g', -1, 64), nil
	case []any:
		return appendArray(b, v, appendJSON)
	case map[string]any:
		return appendJSONObject(b, v)
	default:
		return nil, errUnsupportedType
	}
}

func appendSafeInteger(b []byte, n int64) ([]byte, error) {
	if n < -maxSafeInteger || n > maxSafeInteger {
		return nil, errUnsafeInteger
	}
	return strconv.AppendInt(b, n, 10), nil
}

func appendJSONObject(b []byte, members map[string]any) ([]byte, error) {
	b = append(b, '{')
	first := true
	for name, value := range members {
		if !first {
			b = append(b, ',')
		}
		first = false
		var err error
		if b, err = appendJSON(b, name); err != nil {
			return nil, err
		}
		b = append(b, ':')
		if b, err = appendJSON(b, value); err != nil {
			return nil, err
		}
	}
	return append(b, '}'), nil
}
