//go:build windows

package securefile

import (
	"context"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"unsafe"

	"golang.org/x/sys/windows"
)

func TestRestrictToOwnerSetsAProtectedReadOnlyList(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "key", "secret")
	if err := d.RestrictToOwner("key"); err != nil {
		t.Fatal(err)
	}
	sd, err := windows.GetNamedSecurityInfo(filepath.Join(root, "key"), windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		t.Fatal(err)
	}
	control, _, err := sd.Control()
	if err != nil {
		t.Fatal(err)
	}
	if control&windows.SE_DACL_PROTECTED == 0 {
		t.Errorf("the access list %s inherits entries, want a protected list", sd)
	}
	dacl, _, err := sd.DACL()
	if err != nil {
		t.Fatal(err)
	}
	if dacl.AceCount != 1 {
		t.Fatalf("the access list %s has %d entries, want 1", sd, dacl.AceCount)
	}
	var ace *windows.ACCESS_ALLOWED_ACE
	if aceErr := windows.GetAce(dacl, 0, &ace); aceErr != nil {
		t.Fatal(aceErr)
	}
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		t.Fatal(err)
	}
	sid := (*windows.SID)(unsafe.Pointer(&ace.SidStart)) //nolint:gosec // G103: the Win32 layout of an access entry puts its SID at SidStart.
	// FILE_GENERIC_READ is the right that icacls grants with R.
	if ace.Header.AceType != windows.ACCESS_ALLOWED_ACE_TYPE || ace.Mask != windows.FILE_GENERIC_READ || !sid.Equals(user.User.Sid) {
		t.Errorf("the access list is %s, want one entry that lets only the current user read", sd)
	}
	if got, err := d.ReadFile("key"); err != nil || string(got) != "secret" {
		t.Errorf("ReadFile() = %q, %v, want the owner to read the key", got, err)
	}
}

func TestModesSetTheReadOnlyAttribute(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "f", "x")
	tests := []struct {
		perm fs.FileMode
		want fs.FileMode
	}{{0o444, 0o444}, {0o644, 0o666}, {0o400, 0o444}, {0o600, 0o666}}
	for _, tt := range tests {
		if err := d.Chmod("f", tt.perm); err != nil {
			t.Fatal(err)
		}
		info, err := os.Stat(filepath.Join(root, "f"))
		if err != nil {
			t.Fatal(err)
		}
		if got := info.Mode().Perm(); got != tt.want {
			t.Errorf("Chmod(%v) gave the mode %v, want %v", tt.perm, got, tt.want)
		}
	}
	if err := d.Replace("g", []byte("x"), 0o444); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(filepath.Join(root, "g"))
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != 0o444 {
		t.Errorf("Replace(0444) gave the mode %v, want the read-only attribute", got)
	}
}

func TestRefusesAJunction(t *testing.T) {
	root, d := newTree(t)
	writeFile(t, root, "real/f", "data")
	junction, target := filepath.Join(root, "junction"), filepath.Join(root, "real")
	out, err := exec.CommandContext(context.Background(), "cmd", "/c", "mklink", "/J", junction, target).CombinedOutput() //nolint:gosec // G204: fixed program; the arguments are paths in the temporary directory of the test.
	if err != nil {
		t.Fatalf("mklink /J: %v: %s", err, out)
	}
	_, err = d.ReadFile("junction/f")
	wantReason(t, err, ReasonSymlink)
	_, err = d.Subdir("junction")
	wantReason(t, err, ReasonSymlink)
	wantReason(t, d.RemoveAll("junction"), ReasonSymlink)
	if got := readFile(t, root, "real/f"); got != "data" {
		t.Errorf("the junction target holds %q, want data", got)
	}
}
