package main

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"strings"
	"testing"

	jose "github.com/go-jose/go-jose/v3"
)

// Exercise the dependency selected by Caddy's module graph, including the
// malformed RSA parameters in GHSA-mgcc-cww5-fp2q, before building the image.
func TestJWKRejectsUnboundedRSA(t *testing.T) {
	encodeInt := func(n *big.Int) string {
		return base64.RawURLEncoding.EncodeToString(n.Bytes())
	}
	odd := func(bits uint) string {
		n := new(big.Int).Lsh(big.NewInt(1), bits-1)
		return encodeInt(n.SetBit(n, 0, 1))
	}
	for _, tc := range []struct {
		name, n, p, q, wantErr string
		private                bool
	}{
		{name: "oversized public modulus", n: odd(4097), wantErr: "modulus too large"},
		{name: "oversized private modulus", n: odd(4097), p: "Aw", q: "Aw", private: true, wantErr: "modulus too large"},
		{name: "oversized prime", n: odd(2048), p: odd(16384), q: "Aw", private: true, wantErr: "p * q != n"},
		{name: "inconsistent primes", n: odd(2048), p: "Aw", q: "Aw", private: true, wantErr: "p * q != n"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			key := map[string]string{"kty": "RSA", "n": tc.n, "e": "AQAB"}
			if tc.private {
				key["d"], key["p"], key["q"] = "Aw", tc.p, tc.q
			}
			raw, err := json.Marshal(key)
			if err != nil {
				t.Fatal(err)
			}
			var jwk jose.JSONWebKey
			if err = json.Unmarshal(raw, &jwk); err == nil || !strings.Contains(err.Error(), tc.wantErr) {
				t.Fatalf("expected %q, got %v", tc.wantErr, err)
			}
		})
	}
	for _, bits := range []uint{4095, 4096} {
		raw := `{"kty":"RSA","n":"` + odd(bits) + `","e":"AQAB"}`
		var jwk jose.JSONWebKey
		if err := json.Unmarshal([]byte(raw), &jwk); err != nil {
			t.Fatalf("public modulus of %d bits must load: %v", bits, err)
		}
	}
}

func TestJWKPrivateKeysAndEmbeddedPublicKeys(t *testing.T) {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	privateJSON, err := json.Marshal(jose.JSONWebKey{Key: key})
	if err != nil {
		t.Fatal(err)
	}
	var decoded jose.JSONWebKey
	if err := json.Unmarshal(privateJSON, &decoded); err != nil {
		t.Fatalf("trusted private JWK must still load: %v", err)
	}
	publicJSON, err := json.Marshal(jose.JSONWebKey{Key: &key.PublicKey})
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name string
		key  json.RawMessage
		bad  bool
	}{
		{name: "public", key: publicJSON},
		{name: "private", key: privateJSON, bad: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			protected := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256"}`))
			withJWK := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RS256","jwk":` + string(tc.key) + `}`))
			messages := map[string]string{
				"compact":   withJWK + ".eA.eA",
				"flattened": `{"protected":"` + protected + `","header":{"jwk":` + string(tc.key) + `},"payload":"eA","signature":"eA"}`,
				"general":   `{"payload":"eA","signatures":[{"protected":"` + protected + `","header":{"jwk":` + string(tc.key) + `},"signature":"eA"}]}`,
			}
			for format, msg := range messages {
				parsed, err := jose.ParseSigned(msg)
				if tc.bad {
					if err == nil || !strings.Contains(err.Error(), "private parameters") {
						t.Fatalf("%s: embedded private key accepted or unexpected error: %v", format, err)
					}
				} else if err != nil || parsed.Signatures[0].Header.JSONWebKey == nil {
					t.Fatalf("%s: embedded public key lost: %v", format, err)
				}

			}
			jweHeaders := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"RSA-OAEP","enc":"A128GCM","jwk":` + string(tc.key) + `}`))
			if _, err := jose.ParseEncrypted(jweHeaders + ".eA.eA.eA.eA"); tc.bad {
				if err == nil || !strings.Contains(err.Error(), "private parameters") {
					t.Fatalf("JWE embedded private key accepted or unexpected error: %v", err)
				}
			} else if err != nil {
				t.Fatalf("JWE embedded public key rejected: %v", err)
			}
		})
	}
}
