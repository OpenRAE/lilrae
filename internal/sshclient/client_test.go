package sshclient

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rsa"
	"errors"
	"net"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/sshkeys"
)

func TestDialRequiresExactHostKeyBeforeAuthentication(t *testing.T) {
	clientKey, serverKey := signer(t), signer(t)
	hits := &atomic.Int32{}
	endpoint := peer(t, serverKey, clientKey.PublicKey(), hits)

	for _, tc := range []struct {
		name string
		key  ssh.PublicKey
		port int
		want error
	}{
		{"missing", nil, 0, ErrPinFile},
		{"unknown", serverKey.PublicKey(), otherPort(endpoint.Port), ErrUnknownHost},
		{"changed", signer(t).PublicKey(), endpoint.Port, ErrChangedHostKey},
		{"match", serverKey.PublicKey(), endpoint.Port, nil},
	} {
		t.Run(tc.name, func(t *testing.T) {
			project := t.TempDir()
			if tc.key != nil {
				writePin(t, project, endpoint, tc.port, tc.key)
			}
			before := hits.Load()
			client, err := Dial(t.Context(), project, endpoint, clientKey)
			checkDial(t, client, err, tc.want, hits.Load() > before)
		})
	}
}

func checkDial(t *testing.T, client *ssh.Client, err, want error, authenticated bool) {
	t.Helper()
	if !errors.Is(err, want) {
		t.Fatalf("unexpected dial outcome: %v", err)
	}
	if want != nil {
		if client != nil || authenticated {
			t.Fatal("a rejected connection reached client authentication")
		}
		return
	}
	if client == nil || !authenticated {
		t.Fatal("matched pin did not establish an authenticated connection")
	}
	closeTestTransport(t, client)
}

func TestProbeAuthenticatesAndReturnsHostKey(t *testing.T) {
	operator, host := signer(t), signer(t)
	endpoint := peer(t, host, operator.PublicKey(), &atomic.Int32{})
	key, err := Probe(t.Context(), endpoint, operator)
	if err != nil || !bytes.Equal(key, host.PublicKey().Marshal()) {
		t.Fatalf("authenticated startup probe: %v", err)
	}
	if key, err := Probe(t.Context(), endpoint, signer(t)); err == nil || key != nil {
		t.Fatal("an unauthenticated probe returned a host key")
	}
}

func TestCancellationClosesPendingHandshake(t *testing.T) {
	listener := listen(t)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	endpoint, clientKey := localEndpoint(t, listener), signer(t)
	done := make(chan error, 1)
	go func() {
		_, err := Probe(ctx, endpoint, clientKey)
		done <- err
	}()
	conn, err := listener.Accept()
	if err != nil {
		t.Fatal(err)
	}
	defer closeTestTransport(t, conn)
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("canceled handshake: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("a canceled handshake did not stop")
	}
}

func writePin(t *testing.T, project string, endpoint sshkeys.Endpoint, port int, key ssh.PublicKey) {
	t.Helper()
	endpoint.Port = port
	err := sshkeys.PublishPins(t.Context(), project, []sshkeys.HostPin{{Endpoint: endpoint, Wire: key.Marshal()}})
	if err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(filepath.Join(project, ".aptl", "known_hosts"))
	if err != nil || info.Size() == 0 {
		t.Fatal("test pin missing")
	}
}

func otherPort(port int) int {
	if port == 65535 {
		return port - 1
	}
	return port + 1
}

func listen(t *testing.T) *net.TCPListener {
	t.Helper()
	listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestTransport(t, listener) })
	return listener
}

func localEndpoint(t *testing.T, listener *net.TCPListener) sshkeys.Endpoint {
	t.Helper()
	addr, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		t.Fatal("test listener lacks a TCP address")
	}
	return sshkeys.Endpoint{Host: "127.0.0.1", Port: addr.Port, User: "labadmin"}
}

func peer(t *testing.T, host ssh.Signer, allowed ssh.PublicKey, hits *atomic.Int32, extra ...ssh.Signer) sshkeys.Endpoint {
	t.Helper()
	listener := listen(t)
	server := &ssh.ServerConfig{PublicKeyCallback: func(_ ssh.ConnMetadata, key ssh.PublicKey) (*ssh.Permissions, error) {
		hits.Add(1)
		if ssh.FingerprintSHA256(key) != ssh.FingerprintSHA256(allowed) {
			return nil, errors.New("unrecognized test key")
		}
		return &ssh.Permissions{}, nil
	}}
	server.AddHostKey(host)
	for _, alternate := range extra {
		server.AddHostKey(alternate)
	}
	closed := make(chan struct{})
	go func() {
		defer close(closed)
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			serve(t, conn, server)
		}
	}()
	t.Cleanup(func() {
		closeTestTransport(t, listener)
		<-closed
	})
	return localEndpoint(t, listener)
}

func serve(t *testing.T, conn net.Conn, config *ssh.ServerConfig) {
	t.Helper()
	defer closeTestTransport(t, conn)
	if err := conn.SetDeadline(time.Now().Add(10 * time.Second)); err != nil {
		t.Error(err)
		return
	}
	server, channels, requests, err := ssh.NewServerConn(conn, config)
	if err != nil {
		return
	}
	defer closeTestTransport(t, server)
	go ssh.DiscardRequests(requests)
	for channel := range channels {
		if rejectErr := channel.Reject(ssh.Prohibited, "test peer"); rejectErr != nil {
			t.Error(rejectErr)
		}
	}
}

type testSigner struct{ ssh.Signer }

func signer(t *testing.T) testSigner {
	t.Helper()
	_, key, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	s, err := ssh.NewSignerFromKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return testSigner{Signer: s}
}

func closeTestTransport(t *testing.T, conn interface{ Close() error }) {
	t.Helper()
	if err := closeTransport(conn); err != nil {
		t.Error(err)
	}
}

func TestDialSelectsThePinnedHostKeyOnAMultiKeyServer(t *testing.T) {
	operator := signer(t)
	private, err := rsa.GenerateKey(nil, 2048)
	if err != nil {
		t.Fatal(err)
	}
	pinned, err := ssh.NewSignerFromKey(private)
	if err != nil {
		t.Fatal(err)
	}
	ed25519Host := signer(t)
	endpoint := peer(t, ed25519Host, operator.PublicKey(), &atomic.Int32{}, pinned)
	for _, host := range []ssh.Signer{ed25519Host, pinned} {
		t.Run(host.PublicKey().Type(), func(t *testing.T) {
			project := t.TempDir()
			writePin(t, project, endpoint, endpoint.Port, host.PublicKey())
			client, dialErr := Dial(t.Context(), project, endpoint, operator)
			if dialErr != nil {
				t.Fatal(dialErr)
			}
			closeTestTransport(t, client)
		})
	}
}

func TestDialAndProbeRefuseInvalidEndpoint(t *testing.T) {
	project := t.TempDir()
	endpoint := sshkeys.Endpoint{Host: "*.example.org", Port: 22, User: "labadmin"}
	if client, err := Dial(t.Context(), project, endpoint, nil); err == nil || client != nil {
		t.Fatalf("invalid endpoint reached dial: %v", err)
	}
	if key, err := Probe(t.Context(), endpoint, nil); err == nil || key != nil {
		t.Fatalf("invalid endpoint reached probe: %v", err)
	}
}

func TestDialAndProbePreserveCancellation(t *testing.T) {
	project := t.TempDir()
	endpoint := localEndpoint(t, listen(t))
	clientKey := signer(t)
	writePin(t, project, endpoint, endpoint.Port, signer(t).PublicKey())
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if client, err := Dial(ctx, project, endpoint, clientKey); !errors.Is(err, context.Canceled) || client != nil {
		t.Fatalf("canceled dial: %v", err)
	}
	if key, err := Probe(ctx, endpoint, clientKey); !errors.Is(err, context.Canceled) || key != nil {
		t.Fatalf("canceled probe: %v", err)
	}
}

func TestDialWithPinRequiresClientIdentity(t *testing.T) {
	project := t.TempDir()
	endpoint := localEndpoint(t, listen(t))
	writePin(t, project, endpoint, endpoint.Port, signer(t).PublicKey())
	client, err := Dial(t.Context(), project, endpoint, nil)
	if err == nil || !strings.HasSuffix(err.Error(), ": load client authentication key") || client != nil {
		t.Fatalf("dial without client identity: %v", err)
	}
}

func TestPinnedAlgorithmSelection(t *testing.T) {
	for _, tc := range []struct {
		keyType string
		want    []string
	}{
		{ssh.CertAlgoRSAv01, []string{ssh.CertAlgoRSASHA512v01, ssh.CertAlgoRSASHA256v01}},
		{"unknown-algorithm", nil},
	} {
		if got := hostAlgorithms(tc.keyType); !slices.Equal(got, tc.want) {
			t.Errorf("algorithms for %s = %v, want %v", tc.keyType, got, tc.want)
		}
	}
}
