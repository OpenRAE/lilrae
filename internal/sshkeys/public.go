package sshkeys

import (
	"bytes"
	"strings"

	"golang.org/x/crypto/ssh"
)

const maxPublicKey = 4096

// Fingerprint returns the OpenSSH SHA-256 fingerprint of an Ed25519 public
// key, with or without its public comment.
func Fingerprint(public string) (string, error) {
	key, err := parsePublic([]byte(public))
	if err != nil {
		return "", err
	}
	return ssh.FingerprintSHA256(key.key), nil
}

type parsedKey struct {
	key ssh.PublicKey
}

func parsePublic(public []byte) (parsedKey, error) {
	line := bytes.TrimSpace(public)
	fields := bytes.Fields(line)
	if len(line) > maxPublicKey || bytes.ContainsAny(line, "\r\n\x00") ||
		len(fields) < 2 || string(fields[0]) != ssh.KeyAlgoED25519 {
		return parsedKey{}, errPublicKey
	}
	key, _, options, rest, err := ssh.ParseAuthorizedKey(line)
	if err != nil || key.Type() != ssh.KeyAlgoED25519 || len(options) != 0 || len(rest) != 0 {
		return parsedKey{}, errPublicKey
	}
	return parsedKey{key: key}, nil
}

func publicLine(public []byte) []byte {
	line := bytes.TrimSuffix(bytes.TrimSuffix(public, []byte("\n")), []byte("\r"))
	return append(line, '\n')
}

func validComment(comment string) bool {
	return len(comment) <= 1024 && !strings.ContainsAny(comment, "\r\n\x00")
}
