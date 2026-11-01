package canonical

import (
	"encoding/hex"
	"encoding/json/jsontext"
	"encoding/json/v2"
	"math"
	"math/big"
	"os"
	"strconv"
	"testing"

	"github.com/google/go-cmp/cmp"
)

// vectorFile is a vector file of conformance/testdata/vectors.
type vectorFile struct {
	Corpus  int          `json:"corpus"`
	Scheme  string       `json:"scheme"`
	Version string       `json:"version"`
	Owner   string       `json:"owner"`
	Cases   []vectorCase `json:"cases"`
}

// vectorCase is one case of a vector file. Its input is JSON in Input, or
// raw bytes in InputHex. It expects exact bytes (Hex), a decoded value
// (Value), or the rejection stage (Reject).
type vectorCase struct {
	ID       string         `json:"id"`
	Input    jsontext.Value `json:"input,omitzero"`
	InputHex string         `json:"input_hex,omitzero"`
	Note     string         `json:"note,omitzero"`
	Expect   struct {
		Hex    string         `json:"hex,omitzero"`
		Value  jsontext.Value `json:"value,omitzero"`
		Reject string         `json:"reject,omitzero"`
	} `json:"expect"`
}

// loadVectors reads the vector file of scheme.
func loadVectors(t *testing.T, scheme string) []vectorCase {
	t.Helper()
	root, err := os.OpenRoot("../../conformance/testdata/vectors")
	if err != nil {
		t.Fatal(err)
	}
	data, err := root.ReadFile(scheme + ".json")
	if closeErr := root.Close(); closeErr != nil {
		t.Fatal(closeErr)
	}
	if err != nil {
		t.Fatal(err)
	}
	var file vectorFile
	if err := json.Unmarshal(data, &file, json.RejectUnknownMembers(true)); err != nil {
		t.Fatal(err)
	}
	if file.Scheme != scheme || len(file.Cases) == 0 {
		t.Fatalf("the vector file names scheme %q and has %d cases", file.Scheme, len(file.Cases))
	}
	return file.Cases
}

// input returns the decoded JSON input of c, with its $int and $float tags
// decoded to the value model.
func (c vectorCase) input(t *testing.T) any {
	t.Helper()
	v, err := DecodeStrict(c.Input)
	if err != nil {
		t.Fatalf("%s: the input is not strict JSON", c.ID)
	}
	return untag(t, v)
}

// rawInput returns the bytes of the input_hex member of c.
func (c vectorCase) rawInput(t *testing.T) []byte {
	t.Helper()
	data, err := hex.DecodeString(c.InputHex)
	if err != nil {
		t.Fatalf("%s: invalid input_hex", c.ID)
	}
	return data
}

// untag decodes the $int and $float tags of a vector input.
func untag(t *testing.T, v any) any {
	t.Helper()
	switch v := v.(type) {
	case map[string]any:
		if number, ok := untagNumber(t, v); ok {
			return number
		}
		out := map[string]any{}
		for name, item := range v {
			out[name] = untag(t, item)
		}
		return out
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = untag(t, item)
		}
		return out
	default:
		return v
	}
}

// untagNumber decodes an object that is one $int or $float tag.
func untagNumber(t *testing.T, v map[string]any) (any, bool) {
	t.Helper()
	if len(v) != 1 {
		return nil, false
	}
	if text, ok := v["$int"].(string); ok {
		n, ok := new(big.Int).SetString(text, 10)
		if !ok {
			t.Fatal("invalid $int tag")
		}
		if n.IsInt64() {
			return n.Int64(), true
		}
		return n, true
	}
	if text, ok := v["$float"].(string); ok {
		f, err := strconv.ParseFloat(text, 64)
		if err != nil {
			t.Fatal("invalid $float tag")
		}
		return f, true
	}
	return nil, false
}

// tag writes a decoded value in the typed form of the vectors: an integer
// outside ±2^53 as {"$int": text}, and a float as {"$float": its Python repr}.
func tag(v any) any {
	switch v := v.(type) {
	case int64:
		if v > -(1<<53) && v < 1<<53 {
			return v
		}
		return map[string]any{"$int": strconv.FormatInt(v, 10)}
	case *big.Int:
		return map[string]any{"$int": v.String()}
	case float64:
		repr := pythonFloat(v)
		switch {
		case math.IsNaN(v):
			repr = "nan"
		case math.IsInf(v, 1):
			repr = "inf"
		case math.IsInf(v, -1):
			repr = "-inf"
		}
		return map[string]any{"$float": repr}
	case []any:
		out := make([]any, len(v))
		for i, item := range v {
			out[i] = tag(item)
		}
		return out
	case map[string]any:
		out := map[string]any{}
		for name, item := range v {
			out[name] = tag(item)
		}
		return out
	default:
		return v
	}
}

// checkBytes compares the result of an encoder with a case that expects hex
// or a serialize rejection. It prints only the case ID, because a vector can
// hold a synthetic secret.
func checkBytes(t *testing.T, c vectorCase, out []byte, err error) {
	t.Helper()
	if c.Expect.Reject != "" {
		if c.Expect.Reject != "serialize" || err == nil {
			t.Errorf("%s: the encoder did not reject the input", c.ID)
		}
		return
	}
	if err != nil || hex.EncodeToString(out) != c.Expect.Hex {
		t.Errorf("%s: the bytes differ from the vector", c.ID)
	}
}

func TestRFC8785Vectors(t *testing.T) {
	for _, c := range loadVectors(t, "rfc8785") {
		out, err := RFC8785(c.input(t))
		checkBytes(t, c, out, err)
	}
}

func TestSortedCompactJSONVectors(t *testing.T) {
	for _, c := range loadVectors(t, "sorted-compact-json") {
		out, err := SortedCompactJSON(c.input(t))
		checkBytes(t, c, out, err)
	}
}

func TestDecodeStrictVectors(t *testing.T) {
	for _, c := range loadVectors(t, "strict-json") {
		v, err := DecodeStrict(c.rawInput(t))
		if c.Expect.Reject != "" {
			if c.Expect.Reject != "parse" || err == nil {
				t.Errorf("%s: the decoder did not reject the input", c.ID)
			}
			continue
		}
		want, wantErr := DecodeStrict(c.Expect.Value)
		if err != nil || wantErr != nil || !cmp.Equal(tag(v), want) {
			t.Errorf("%s: the value differs from the vector", c.ID)
		}
	}
}
