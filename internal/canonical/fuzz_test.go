package canonical

import (
	"bytes"
	"math/big"
	"testing"

	"github.com/google/go-cmp/cmp"
)

// addSeeds adds the seed inputs of the fuzz tests.
func addSeeds(f *testing.F) {
	f.Helper()
	for _, seed := range []string{
		`{"b":[1,2.5,"x",null,true],"a":{}}`,
		`[1E2,-0.0,5e-324,1.7976931348623157e308]`,
		`{"é":"😀","a\u0000b":"\u001f"}`,
		`9007199254740993`,
		`1e400`,
		`{"a":1,"a":2}`,
	} {
		f.Add([]byte(seed))
	}
}

// FuzzDecodeStrict checks that strict decoding never panics, and that a
// decoded value survives a round trip through SortedCompactJSON.
func FuzzDecodeStrict(f *testing.F) {
	addSeeds(f)
	f.Fuzz(func(t *testing.T, data []byte) {
		v, err := DecodeStrict(data)
		if err != nil {
			return
		}
		out, err := SortedCompactJSON(v)
		if err != nil {
			t.Fatalf("SortedCompactJSON rejected a decoded value: %v", err)
		}
		back, err := DecodeStrict(out)
		if err != nil {
			t.Fatalf("DecodeStrict rejected the sorted form: %v", err)
		}
		if !cmp.Equal(v, back, cmp.Comparer(func(a, b *big.Int) bool { return a.Cmp(b) == 0 })) {
			t.Fatal("the round trip changed the value")
		}
	})
}

// FuzzRFC8785 checks that the RFC 8785 form of a decoded value is strict JSON
// whose own RFC 8785 form is the same bytes.
func FuzzRFC8785(f *testing.F) {
	addSeeds(f)
	f.Fuzz(func(t *testing.T, data []byte) {
		v, err := DecodeStrict(data)
		if err != nil {
			return
		}
		out, err := RFC8785(v)
		if err != nil {
			return
		}
		back, err := DecodeStrict(out)
		if err != nil {
			t.Fatalf("DecodeStrict rejected the RFC 8785 form: %v", err)
		}
		again, err := RFC8785(back)
		if err != nil {
			// An integer form of a large float is outside the integer range.
			return
		}
		if !bytes.Equal(out, again) {
			t.Fatal("the RFC 8785 form is not stable")
		}
	})
}
