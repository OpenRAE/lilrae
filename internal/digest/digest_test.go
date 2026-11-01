package digest_test

import (
	"encoding/hex"
	"encoding/json/v2"
	"os"
	"testing"

	"github.com/OpenRAE/lilrae/internal/digest"
)

// sha256Corpus is the vector file of the sha256-bytes scheme of Go port 04.
type sha256Corpus struct {
	Corpus  int    `json:"corpus"`
	Scheme  string `json:"scheme"`
	Version string `json:"version"`
	Owner   string `json:"owner"`
	Cases   []struct {
		ID       string `json:"id"`
		InputHex string `json:"input_hex"`
		Note     string `json:"note,omitempty"`
		Expect   struct {
			Text string `json:"text"`
		} `json:"expect"`
	} `json:"cases"`
}

func TestSHA256HexVectors(t *testing.T) {
	data, err := os.ReadFile("../../conformance/testdata/vectors/sha256-bytes.json")
	if err != nil {
		t.Fatal(err)
	}
	var c sha256Corpus
	if err := json.Unmarshal(data, &c, json.RejectUnknownMembers(true)); err != nil {
		t.Fatal(err)
	}
	if c.Scheme != "sha256-bytes" || len(c.Cases) == 0 {
		t.Fatalf("the corpus has scheme %q and %d cases", c.Scheme, len(c.Cases))
	}
	for _, tc := range c.Cases {
		input, err := hex.DecodeString(tc.InputHex)
		if err != nil {
			t.Fatalf("%s: %v", tc.ID, err)
		}
		if got := digest.SHA256Hex(input); got != tc.Expect.Text {
			t.Errorf("%s: the digest differs from the vector", tc.ID)
		}
	}
}

func TestSHA256Ref(t *testing.T) {
	const want = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
	if got := digest.SHA256Ref(nil); got != want {
		t.Errorf("SHA256Ref(nil) = %q, want %q", got, want)
	}
}
