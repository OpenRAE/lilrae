package sshkeys

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

func TestCaptureReplacesPins(t *testing.T) {
	project := t.TempDir()
	first := sampleHostKey(t)
	second := sampleHostKey(t)
	fixed := Endpoint{Name: "fixed", Host: "192.0.2.1", Port: 22, User: "labadmin"}
	alternate := Endpoint{Name: "alternate", Host: "192.0.2.2", Port: 2027, User: "labadmin"}
	target := filepath.Join(project, ".aptl", "known_hosts")
	if err := PublishPins(t.Context(), project, []HostPin{{fixed, first.wire}, {alternate, first.wire}}); err != nil {
		t.Fatal(err)
	}
	lines := strings.Split(strings.TrimSpace(string(readFixture(t, target))), "\n")
	if len(lines) != 2 || !strings.HasPrefix(lines[0], "192.0.2.1 ssh-ed25519 ") ||
		!strings.HasPrefix(lines[1], "[192.0.2.2]:2027 ssh-ed25519 ") {
		t.Fatal("pin file has the wrong endpoint forms")
	}
	checkMode(t, filepath.Dir(target), 0o700)
	checkMode(t, target, 0o644)

	if err := PublishPins(t.Context(), project, []HostPin{{fixed, second.wire}}); err != nil {
		t.Fatal(err)
	}
	pins, err := ReadPins(t.Context(), project)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(pins.Key(fixed), second.wire) || pins.Key(alternate) != nil {
		t.Fatal("a completed capture did not replace the prior pins")
	}

	checkEmptyCapture(t, project, target)
}

func checkEmptyCapture(t *testing.T, project, target string) {
	t.Helper()
	if err := PublishPins(t.Context(), project, nil); err != nil {
		t.Fatal(err)
	}
	if len(readFixture(t, target)) != 0 {
		t.Fatal("an empty capture kept old pins")
	}
}

func TestMalformedPinsRejectWholeFile(t *testing.T) {
	key := sampleHostKey(t).line
	first := "192.0.2.1 " + key
	for _, invalid := range []string{"missing-fields\n", "*.example " + key, "@revoked 192.0.2.2 " + key,
		"192.0.2.2,192.0.2.3 " + key, "192.0.2.2 ssh-rsa " + strings.TrimPrefix(key, "ssh-ed25519 "), "[192.0.2.2]:22 " + key,
		"192.0.2.1 " + sampleHostKey(t).line} {
		project := t.TempDir()
		target := filepath.Join(project, ".aptl")
		if err := os.Mkdir(target, 0o700); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(target, "known_hosts"), []byte(first+invalid), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := ReadPins(t.Context(), project); err == nil {
			t.Error("accepted malformed pin file with a valid entry")
		}
	}
}

type hostFixture struct {
	wire []byte
	line string
}

func sampleHostKey(t *testing.T) hostFixture {
	t.Helper()
	dir, err := securefile.OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	pair, err := EnsurePair(t.Context(), dir, "key", "host")
	if err != nil {
		t.Fatal(err)
	}
	key := pair.Signer.PublicKey()
	return hostFixture{wire: key.Marshal(), line: string(ssh.MarshalAuthorizedKey(key))}
}

func TestEndpointNamesAreLiteral(t *testing.T) {
	for _, tc := range []struct {
		host string
		port int
		pin  string
	}{
		{"Host.example", 22, "Host.example"},
		{"host_name-9", 1, "[host_name-9]:1"},
		{"::1", 22, "::1"},
		{"fe80::7%eth0", 65535, "[fe80::7%eth0]:65535"},
		{"1.2.3.4", 0, ""},
		{"1.2.3.4", 65536, ""},
		{"example.org\n", 22, ""},
		{"example.org ", 22, ""},
		{"*.example.org", 22, ""},
		{"[::1]", 22, ""},
		{"::1%?", 22, ""},
		{"name%zone", 22, ""},
		{"", 22, ""},
		{strings.Repeat("x", 253), 22, strings.Repeat("x", 253)},
		{strings.Repeat("x", 254), 22, ""},
	} {
		ep := Endpoint{Host: tc.host, Port: tc.port, User: "labadmin"}
		if got := ep.pinName(); got != tc.pin {
			t.Errorf("pin for %q port %d is %q, want %q", tc.host, tc.port, got, tc.pin)
		}
		if _, err := ep.Address(); (err != nil) != (tc.pin == "") {
			t.Errorf("unexpected dial address result for %q port %d: %v", tc.host, tc.port, err)
		}
	}
}

func TestFailedPublicationKeepsPriorPins(t *testing.T) {
	project := t.TempDir()
	key := sampleHostKey(t)
	endpoint := Endpoint{Name: "fixed", Host: "192.0.2.1", Port: 22, User: "labadmin"}
	if err := PublishPins(t.Context(), project, []HostPin{{endpoint, key.wire}}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if err := PublishPins(ctx, project, nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled capture: %v", err)
	}
	_, loadErr := ReadPins(ctx, project)
	if !errors.Is(loadErr, context.Canceled) {
		t.Fatalf("canceled pin load: %v", loadErr)
	}
	badHost := endpoint
	badHost.Host = "*.example.org"
	for _, candidates := range [][]HostPin{
		{{endpoint, []byte("invalid wire key")}},
		{{badHost, key.wire}},
		{{endpoint, key.wire}, {endpoint, sampleHostKey(t).wire}},
	} {
		if PublishPins(t.Context(), project, candidates) == nil {
			t.Fatal("published invalid captured pins")
		}
	}
	pins, err := ReadPins(t.Context(), project)
	if err != nil || !bytes.Equal(pins.Key(endpoint), key.wire) {
		t.Fatalf("failed capture replaced the trusted pins: %v", err)
	}
}

func TestPinStorageRefusesUnavailablePaths(t *testing.T) {
	for _, tc := range []struct{ name, readError, writeError string }{
		{"project", "open SSH pin root", "open SSH pin root"},
		{"project/.aptl", "open SSH directory", "open SSH directory"},
		{"project/.aptl/known_hosts", "open trusted SSH pin file", "publish SSH pin file"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			project := filepath.Join(root, "project")
			blocked := filepath.Join(root, filepath.FromSlash(tc.name))
			blockProvisionPath(t, blocked, filepath.Base(blocked) == pinFile)
			_, loadErr := ReadPins(t.Context(), project)
			checkProvisionError(t, loadErr, tc.readError)
			checkProvisionError(t, PublishPins(t.Context(), project, nil), tc.writeError)
		})
	}
}

func TestReadPinsRejectsOversizedSnapshot(t *testing.T) {
	root := t.TempDir()
	state := filepath.Join(root, ".aptl")
	if err := os.Mkdir(state, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(state, pinFile), bytes.Repeat([]byte{'\n'}, maxPinFile+1), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err := ReadPins(t.Context(), root)
	checkProvisionError(t, err, "read SSH pin file")
}

func TestPinSnapshotSizeLimit(t *testing.T) {
	project := t.TempDir()
	key := sampleHostKey(t)
	pin := HostPin{Endpoint: Endpoint{Host: "h", Port: 22}, Wire: key.wire}
	lineSize := len(pin.Endpoint.Host) + 1 + len(key.line)
	repeats := maxPinFile/lineSize - 1
	pins := make([]HostPin, repeats+1)
	for i := range repeats {
		pins[i] = pin
	}
	remaining := maxPinFile - repeats*lineSize
	pins[repeats] = HostPin{Endpoint: Endpoint{Host: strings.Repeat("a", remaining-1-len(key.line)), Port: 22}, Wire: key.wire}
	if err := PublishPins(t.Context(), project, pins); err != nil {
		t.Fatalf("snapshot exactly at limit: %v", err)
	}
	pins[repeats].Endpoint.Host += "a"
	if err := PublishPins(t.Context(), project, pins); err == nil {
		t.Fatal("published a snapshot beyond the limit")
	}
}
