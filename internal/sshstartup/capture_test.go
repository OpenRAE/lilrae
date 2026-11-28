package sshstartup

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"errors"
	"testing"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/sshkeys"
)

func TestSkippedCaptureKeepsThePriorPins(t *testing.T) {
	project := t.TempDir()
	_, private, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	signer, err := ssh.NewSignerFromKey(private)
	if err != nil {
		t.Fatal(err)
	}
	expected := signer.PublicKey().Marshal()
	active := sshkeys.Endpoint{Name: "active", Host: "192.0.2.1", Port: 22, User: "test"}
	if seedErr := sshkeys.PublishPins(t.Context(), project, []sshkeys.HostPin{{Endpoint: active, Wire: expected}}); seedErr != nil {
		t.Fatal(seedErr)
	}
	got, err := Capture(t.Context(), project, []sshkeys.Endpoint{active}, nil, nil)
	if err != nil || !got.Skipped {
		t.Fatalf("missing signer: %+v, %v", got, err)
	}
	pins, err := sshkeys.ReadPins(t.Context(), project)
	if err != nil || !bytes.Equal(pins.Key(active), expected) {
		t.Fatalf("skipped capture replaced the active pin: %v", err)
	}
	result, err := Capture(t.Context(), project, []sshkeys.Endpoint{active}, signer,
		func(context.Context, sshkeys.Endpoint, ssh.Signer) ([]byte, error) {
			return nil, errors.New("test endpoint unavailable")
		})
	if err != nil || result.Skipped || len(result.Failed) != 1 || len(result.Pinned) != 0 {
		t.Fatalf("completed empty capture: %+v, %v", result, err)
	}
	pins, err = sshkeys.ReadPins(t.Context(), project)
	if err != nil || pins.Key(active) != nil {
		t.Fatalf("completed capture retained an unavailable pin: %v", err)
	}
}
