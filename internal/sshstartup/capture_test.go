package sshstartup

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"errors"
	"testing"
	"time"

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

func TestCaptureRequiresProbeOnlyForEndpoints(t *testing.T) {
	signer := startupSigner(t)
	ep := sshkeys.Endpoint{Name: "active", Host: "localhost", Port: 22, User: "test"}
	project := t.TempDir()
	if _, err := Capture(t.Context(), project, []sshkeys.Endpoint{ep}, signer, nil); err == nil {
		t.Fatal("accepted endpoints without a probe")
	}
	if _, err := Capture(t.Context(), project, nil, signer, nil); err != nil {
		t.Fatalf("empty capture without probe: %v", err)
	}
}

func TestProbeEnforcesWindowAndRejectsBadResults(t *testing.T) {
	signer := startupSigner(t)
	ep := sshkeys.Endpoint{Name: "active", Host: "localhost", Port: 22, User: "test"}
	key := signer.PublicKey().Marshal()
	probe := func(ctx context.Context, _ sshkeys.Endpoint, _ ssh.Signer) ([]byte, error) {
		deadline, ok := ctx.Deadline()
		if !ok || time.Until(deadline) <= 9*time.Second || time.Until(deadline) > 10*time.Second {
			t.Fatal("missing startup probe time limit")
		}
		return key, nil
	}
	if got := probeEndpoint(t.Context(), ep, signer, probe); !bytes.Equal(got, key) {
		t.Fatal("discarded a valid result")
	}
	checkProbeRefusals(t, ep, key, signer)
}

func checkProbeRefusals(t *testing.T, ep sshkeys.Endpoint, key []byte, signer ssh.Signer) {
	t.Helper()
	bad := ep
	bad.Host = "*.example"
	unused := func(context.Context, sshkeys.Endpoint, ssh.Signer) ([]byte, error) {
		t.Fatal("an invalid endpoint reached the probe")
		return nil, errors.New("invalid test endpoint")
	}
	if probeEndpoint(t.Context(), bad, signer, unused) != nil {
		t.Fatal("accepted an invalid endpoint")
	}
	if probeEndpoint(t.Context(), ep, signer, func(context.Context, sshkeys.Endpoint, ssh.Signer) ([]byte, error) {
		return []byte("invalid"), nil
	}) != nil {
		t.Fatal("accepted an invalid public key")
	}
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	if probeEndpoint(ctx, ep, signer, func(context.Context, sshkeys.Endpoint, ssh.Signer) ([]byte, error) {
		cancel()
		return key, nil
	}) != nil {
		t.Fatal("accepted the result of a canceled probe")
	}
}

type testSigner struct{ ssh.Signer }

func startupSigner(t *testing.T) testSigner {
	t.Helper()
	_, private, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	signer, err := ssh.NewSignerFromKey(private)
	if err != nil {
		t.Fatal(err)
	}
	return testSigner{Signer: signer}
}
