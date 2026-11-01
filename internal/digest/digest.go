// Package digest gives the SHA-256 digest spellings that records store and
// compare.
package digest

import (
	"crypto/sha256"
	"encoding/hex"
)

// SHA256Hex returns the SHA-256 digest of data in lower-case hex.
func SHA256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// SHA256Ref returns the SHA-256 digest of data as "sha256:" followed by
// lower-case hex.
func SHA256Ref(data []byte) string {
	return "sha256:" + SHA256Hex(data)
}
