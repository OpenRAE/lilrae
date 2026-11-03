package canonical

import (
	"bytes"
	"encoding/json/jsontext"
	"errors"
	"fmt"
	"io"
	"math/big"
	"strconv"
	"strings"
)

var (
	errNoValue      = errors.New("canonical: the input holds no JSON value")
	errNumberRange  = errors.New("canonical: a number does not decode to a finite float")
	errTrailingData = errors.New("canonical: the input has data after the JSON value")
)

// DecodeStrict decodes one JSON value with the rules of the strict-json
// scheme. It rejects duplicate member names, invalid UTF-8, the constants NaN
// and Infinity, a number that overflows to an infinity, an integer with more
// digits than Python reads, and data after the value. A number without a
// fraction or an exponent decodes to an int64, or to a [*big.Int] when it does
// not fit, and another number decodes to a float64.
func DecodeStrict(data []byte) (any, error) {
	dec := jsontext.NewDecoder(bytes.NewReader(data))
	v, err := decodeValue(dec)
	if err != nil {
		return nil, err
	}
	_, err = dec.ReadToken()
	if errors.Is(err, io.EOF) {
		return v, nil
	}
	if err == nil {
		return nil, errTrailingData
	}
	return nil, syntaxError(dec)
}

func decodeValue(dec *jsontext.Decoder) (any, error) {
	tok, err := dec.ReadToken()
	if errors.Is(err, io.EOF) {
		return nil, errNoValue
	}
	if err != nil {
		return nil, syntaxError(dec)
	}
	switch tok.Kind() {
	case jsontext.KindNull, jsontext.KindFalse, jsontext.KindTrue, jsontext.KindString:
		return scalar(tok), nil
	case jsontext.KindNumber:
		return decodeNumber(tok.String())
	case jsontext.KindBeginArray:
		return decodeArray(dec)
	case jsontext.KindBeginObject:
		return decodeObject(dec)
	case jsontext.KindInvalid, jsontext.KindEndArray, jsontext.KindEndObject:
		// The decoder returns no such token at the start of a value.
	}
	return nil, syntaxError(dec)
}

// scalar returns the value of a null, boolean, or string token.
func scalar(tok jsontext.Token) any {
	if tok.Kind() == jsontext.KindString {
		return tok.String()
	}
	if tok.Kind() == jsontext.KindNull {
		return nil
	}
	return tok.Bool()
}

func decodeArray(dec *jsontext.Decoder) ([]any, error) {
	items := []any{}
	for dec.PeekKind() != jsontext.KindEndArray {
		item, err := decodeValue(dec)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	if _, err := dec.ReadToken(); err != nil {
		return nil, syntaxError(dec)
	}
	return items, nil
}

func decodeObject(dec *jsontext.Decoder) (map[string]any, error) {
	members := map[string]any{}
	for dec.PeekKind() != jsontext.KindEndObject {
		tok, err := dec.ReadToken()
		if err != nil {
			return nil, syntaxError(dec)
		}
		name := tok.String() // The next read voids the token.
		value, err := decodeValue(dec)
		if err != nil {
			return nil, err
		}
		members[name] = value
	}
	if _, err := dec.ReadToken(); err != nil {
		return nil, syntaxError(dec)
	}
	return members, nil
}

// decodeNumber reads JSON number text as Python's json module does: an
// integer when it has no fraction and no exponent, and a float otherwise.
func decodeNumber(text string) (any, error) {
	if !strings.ContainsAny(text, ".eE") {
		if tooManyDigits(text) {
			return nil, errIntegerTooLong
		}
		n, _ := new(big.Int).SetString(text, 10) // jsontext validated the syntax.
		if n.IsInt64() {
			return n.Int64(), nil
		}
		return n, nil
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil {
		return nil, errNumberRange
	}
	return f, nil
}

// syntaxError reports invalid JSON at the offset of the decoder, without the
// text of the error of jsontext, which can quote a member name.
func syntaxError(dec *jsontext.Decoder) error {
	return fmt.Errorf("canonical: the input is not strict JSON at byte %d", dec.InputOffset())
}
