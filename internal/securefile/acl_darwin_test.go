package securefile

import (
	"context"
	"encoding/binary"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func TestDarwinACLResponseAtSupportedSizes(t *testing.T) {
	for _, count := range []uint32{0, 128} {
		length := uint32(darwinACLHeader) + count*darwinACEBytes
		result := darwinSecurity{Size: 12 + length, Offset: 8, Length: length}
		binary.NativeEndian.PutUint32(result.Security[:4], 0x012cc16d)
		binary.NativeEndian.PutUint32(result.Security[36:40], count)
		for i := range count {
			// A full access list of deny entries grants no access.
			flags := darwinACLHeader + i*darwinACEBytes + 16
			binary.NativeEndian.PutUint32(result.Security[flags:flags+4], 2)
		}
		if err := result.check(false); err != nil {
			t.Errorf("valid extended ACL with %d entries: %v", count, err)
		}
	}
}

func TestInheritedACLRefusesPrivateKeyPublication(t *testing.T) {
	root, dir := newTree(t)
	addDarwinACL(t, root, "group:everyone allow read,file_inherit")
	if err := dir.CreateOwnerRead("key", []byte("test material")); err == nil {
		t.Fatal("published a file with an inherited read grant")
	}
	if _, err := os.Stat(filepath.Join(root, "key")); !errors.Is(err, fs.ErrNotExist) {
		t.Fatalf("a rejected key was left behind: %v", err)
	}
	if got := names(t, root, "."); len(got) != 0 {
		t.Fatalf("private staging file remained: %v", got)
	}
}

func TestExistingACLRefusesPrivateKeyRead(t *testing.T) {
	root, dir := newTree(t)
	if err := dir.CreateOwnerRead("key", []byte("test material")); err != nil {
		t.Fatal(err)
	}
	addDarwinACL(t, filepath.Join(root, "key"), "group:everyone allow read")
	file, err := dir.OpenOwned("key", true)
	if file != nil {
		closeOnCleanup(t, file)
		t.Fatal("readable handle for private key with an extended ACL")
	}
	wantReason(t, err, ReasonNotPrivate)
}

func TestPublicDirectoryACLChecksWriteGrants(t *testing.T) {
	root, dir := newTree(t)
	t.Cleanup(func() {
		ctx, cancel := context.WithTimeout(context.WithoutCancel(t.Context()), 5*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "/bin/chmod", "-N", root) //nolint:gosec // G204: chmod is fixed and root is the test directory.
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Errorf("remove fixture ACL: %v: %s", err, out)
		}
	})
	addDarwinACL(t, root, "group:everyone deny delete")
	addDarwinACL(t, root, "group:everyone allow list,search")
	if err := dir.CheckWriteOwner(); err != nil {
		t.Fatalf("deny and read entries should allow owner control: %v", err)
	}
	addDarwinACL(t, root, "group:everyone allow add_file,file_inherit")
	wantReason(t, dir.CheckWriteOwner(), ReasonNotPrivate)
}

func addDarwinACL(t *testing.T, path, acl string) {
	t.Helper()
	cmd := exec.CommandContext(t.Context(), "/bin/chmod", "+a", acl, path) //nolint:gosec // G204: chmod and its option are fixed, and the remaining arguments are test fixtures.
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("set fixture ACL: %v: %s", err, out)
	}
}
