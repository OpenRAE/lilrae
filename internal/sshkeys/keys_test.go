package sshkeys

import (
	"bytes"
	"context"
	"encoding/json/v2"
	"encoding/pem"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/securefile"
)

func TestClientKeyFiles(t *testing.T) {
	project, home := t.TempDir(), filepath.Join(t.TempDir(), ".ssh")
	pair, err := EnsureControlPlane(t.Context(), project, home)
	if err != nil || !pair.Generated {
		t.Fatalf("create control-plane key: %v", err)
	}
	if pivotErr := EnsurePivots(t.Context(), project, pair); pivotErr != nil {
		t.Fatal(pivotErr)
	}
	control := checkKeyFiles(t, filepath.Join(home, "aptl_lab_key"), "aptl-local-lab")
	kali := checkKeyFiles(t, filepath.Join(project, "config", "lab-ssh", "kali_pivot_key"), "aptl-kali-pivot")
	workstation := checkKeyFiles(t, filepath.Join(project, "config", "lab-ssh", "workstation_pivot_key"), "aptl-workstation-pivot")
	for name, want := range map[string]string{
		"aptl_lab_key.pub": control, "authorized_keys": control,
		"target_authorized_keys": control + kali, "victim_authorized_keys": control + kali + workstation,
	} {
		path := filepath.Join(project, "keys", name)
		if string(readFixture(t, path)) != want {
			t.Errorf("wrong authorization contents in %s", name)
		}
		checkMode(t, path, 0o644)
	}
	again, err := EnsureControlPlane(t.Context(), project, home)
	if err != nil || again.Generated || !bytes.Equal(pair.Signer.PublicKey().Marshal(), again.Signer.PublicKey().Marshal()) {
		t.Fatalf("reuse changed the identity: %v", err)
	}
}

func TestIncompletePairRefusesReuse(t *testing.T) {
	dir, err := securefile.OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	if _, err := EnsurePair(t.Context(), dir, "key", "example"); err != nil {
		t.Fatal(err)
	}
	if err := dir.Remove("key.pub"); err != nil {
		t.Fatal(err)
	}
	if _, err := EnsurePair(t.Context(), dir, "key", "example"); err == nil {
		t.Fatal("reused a private key with no corresponding public key")
	}
}

func TestFingerprintVector(t *testing.T) {
	var vector struct {
		Cases []struct {
			ID    string `json:"id"`
			Input struct {
				PublicKey string `json:"public_key"`
			} `json:"input"`
			Expect struct {
				Text   string `json:"text"`
				Reject string `json:"reject"`
			} `json:"expect"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(readFixture(t, "../../conformance/testdata/vectors/ssh-key-fingerprint.json"), &vector); err != nil {
		t.Fatal(err)
	}
	if len(vector.Cases) == 0 {
		t.Fatal("empty fingerprint vector")
	}
	for _, tc := range vector.Cases {
		t.Run(tc.ID, func(t *testing.T) {
			got, err := Fingerprint(tc.Input.PublicKey)
			if got != tc.Expect.Text || (err != nil) != (tc.Expect.Reject != "") {
				t.Fatal("fingerprint outcome differs from the vector")
			}
		})
	}
}

func checkKeyFiles(t *testing.T, name, comment string) string {
	t.Helper()
	private := readFixture(t, name)
	block, _ := pem.Decode(private)
	if block == nil || block.Type != "OPENSSH PRIVATE KEY" {
		t.Fatal("wrong private key format")
	}
	if !bytes.Contains(block.Bytes, []byte(comment)) {
		t.Fatal("wrong private key comment")
	}
	signer, err := ssh.ParsePrivateKey(private)
	if err != nil {
		t.Fatal("could not parse private key")
	}
	public := readFixture(t, name+".pub")
	key, got, _, _, err := ssh.ParseAuthorizedKey(public)
	if err != nil || key.Type() != ssh.KeyAlgoED25519 || got != comment || !bytes.Equal(signer.PublicKey().Marshal(), key.Marshal()) {
		t.Fatal("wrong public key format, comment, or identity")
	}
	checkMode(t, name, 0o600)
	checkMode(t, name+".pub", 0o644)
	return string(public)
}

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile(name) //nolint:gosec // G304: only test fixture paths and t.TempDir files are read.
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func checkMode(t *testing.T, name string, want os.FileMode) {
	t.Helper()
	if runtime.GOOS == "windows" {
		return
	}
	info, err := os.Stat(name)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != want {
		t.Errorf("%s mode %o, want %o", filepath.Base(name), info.Mode().Perm(), want)
	}
}

func closeTestDir(t *testing.T, dir *securefile.Dir) {
	t.Helper()
	if err := dir.Close(); err != nil {
		t.Error(err)
	}
}

func TestReuseRejectsMismatchedPublicKey(t *testing.T) {
	dir, err := securefile.OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	if _, keyErr := EnsurePair(t.Context(), dir, "first", "first"); keyErr != nil {
		t.Fatal(keyErr)
	}
	other, err := EnsurePair(t.Context(), dir, "second", "second")
	if err != nil {
		t.Fatal(err)
	}
	if err := dir.Replace("first.pub", other.Public, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadPair(t.Context(), dir, "first"); err == nil {
		t.Fatal("accepted a mismatched public key")
	}
}

func TestInvalidPublicKeyRecords(t *testing.T) {
	key := sampleHostKey(t).line
	for _, value := range []string{" " + strings.Repeat("x", 4097),
		"no-pty " + key, strings.TrimSpace(key) + "\n" + key,
		"ssh-rsa " + strings.TrimPrefix(key, "ssh-ed25519 "), strings.TrimSpace(key) + "\x00"} {
		if _, err := Fingerprint(value); err == nil {
			t.Error("accepted an invalid Ed25519 public record")
		}
	}
}

func TestConcurrentProjectsUseOneHostIdentity(t *testing.T) {
	type outcome struct {
		pair Pair
		err  error
	}
	results := make(chan outcome, 2)
	home := filepath.Join(t.TempDir(), ".ssh")
	ctx := t.Context()
	for range 2 {
		project := t.TempDir()
		go func() {
			pair, err := EnsureControlPlane(ctx, project, home)
			results <- outcome{pair, err}
		}()
	}
	first, second := <-results, <-results
	if first.err != nil || second.err != nil {
		t.Fatalf("concurrent provision: %v, %v", first.err, second.err)
	}
	if first.pair.Generated == second.pair.Generated || !bytes.Equal(first.pair.Public, second.pair.Public) {
		t.Fatal("concurrent projects did not share the winning identity")
	}
}

func TestPublicOnlyPairIsNotReplaced(t *testing.T) {
	root := t.TempDir()
	dir, err := securefile.OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	old := []byte(sampleHostKey(t).line)
	if err := dir.Replace("key.pub", old, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := EnsurePair(t.Context(), dir, "key", "example"); err == nil {
		t.Fatal("accepted the public half of a missing identity")
	}
	if _, err := os.Stat(filepath.Join(root, "key")); !os.IsNotExist(err) {
		t.Fatalf("private key changed: %v", err)
	}
	if !bytes.Equal(readFixture(t, filepath.Join(root, "key.pub")), old) {
		t.Fatal("the original public key was replaced")
	}
}

func TestPublicAuthorizationDirectoryRejectsOtherWriters(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("native ACL behavior is covered by the securefile Windows test")
	}
	project := t.TempDir()
	home := filepath.Join(t.TempDir(), ".ssh")
	keys := filepath.Join(project, "keys")
	if err := os.Mkdir(keys, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(keys, 0o772); err != nil { //nolint:gosec // G302: the fixture deliberately grants write access to a temporary directory.
		t.Fatal(err)
	}
	if _, err := EnsureControlPlane(t.Context(), project, home); err == nil {
		t.Fatal("accepted an authorization directory with other writers")
	}
	if _, err := os.Stat(filepath.Join(keys, "authorized_keys")); !os.IsNotExist(err) {
		t.Fatalf("authorization file changed: %v", err)
	}
}

func TestReadPairRefusesAnUnprotectedPrivateFile(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows access lists are covered in the securefile Windows test")
	}
	root := t.TempDir()
	dir, err := securefile.OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	if _, err := EnsurePair(t.Context(), dir, "key", "test"); err != nil {
		t.Fatal(err)
	}
	if err := dir.Chmod("key", 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadPair(t.Context(), dir, "key"); err == nil {
		t.Fatal("accepted a private key readable by another user")
	}
}

func TestReadPairRefusesCanceledContext(t *testing.T) {
	dir, err := securefile.OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	if _, keyErr := EnsurePair(t.Context(), dir, "key", "operator"); keyErr != nil {
		t.Fatal(keyErr)
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	if _, loadErr := ReadPair(ctx, dir, "key"); !errors.Is(loadErr, context.Canceled) {
		t.Fatalf("read after cancellation: %v", loadErr)
	}
}

func TestReadPairRefusesAnUntrustedDirectory(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows directory access lists are covered by the securefile tests")
	}
	root := t.TempDir()
	dir, err := securefile.OpenDir(root)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	if _, keyErr := EnsurePair(t.Context(), dir, "key", "operator"); keyErr != nil {
		t.Fatal(keyErr)
	}
	if chmodErr := os.Chmod(root, 0o770); chmodErr != nil { //nolint:gosec // G302: a temporary fixture needs an additional writer.
		t.Fatal(chmodErr)
	}
	if _, loadErr := ReadPair(t.Context(), dir, "key"); loadErr == nil {
		t.Fatal("loaded a pair from a directory with another writer")
	}
}

func TestReadBoundedFileSize(t *testing.T) {
	dir, err := securefile.OpenDir(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { closeTestDir(t, dir) })
	for _, contents := range []string{"abcd", "abcde"} {
		if writeErr := dir.Replace("fixture", []byte(contents), 0o600); writeErr != nil {
			t.Fatal(writeErr)
		}
		file, openErr := dir.Open("fixture")
		if openErr != nil {
			t.Fatal(openErr)
		}
		got, readErr := readBounded(file, 4)
		if (readErr != nil) != (len(contents) > 4) || (readErr == nil && string(got) != contents) {
			t.Fatalf("size %d: %v", len(contents), readErr)
		}
	}
}

func TestPublicKeyAndCommentSizeLimits(t *testing.T) {
	line := strings.TrimSpace(sampleHostKey(t).line)
	exact := line + " " + strings.Repeat("c", maxPublicKey-1-len(line))
	if _, err := Fingerprint(exact); err != nil {
		t.Fatalf("public record exactly at limit: %v", err)
	}
	if _, err := Fingerprint(exact + "c"); err == nil {
		t.Fatal("accepted a public record beyond the limit")
	}
	if !validComment(strings.Repeat("c", 1024)) || validComment(strings.Repeat("c", 1025)) {
		t.Fatal("wrong SSH comment length limit")
	}
}
