package securefile

import (
	"errors"
	"fmt"
	"os"
	"unsafe"

	"golang.org/x/sys/windows"
)

func (h dirHandle) checkWriteOwner() (err error) {
	file, err := h.root.Open(".")
	if err != nil {
		return fmt.Errorf("open directory for owner access: %w", err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	if err := checkDACL(windows.Handle(file.Fd()), false); err != nil {
		return &Error{Op: "check directory owner access", Path: ".", Reason: ReasonNotPrivate, Err: err}
	}
	return nil
}

func checkOwnedAccess(file *os.File, private bool) error {
	handle := windows.Handle(file.Fd())
	if err := checkOwnedFile(handle); err != nil {
		return err
	}
	return checkDACL(handle, private)
}

func checkDACL(file windows.Handle, private bool) error {
	sd, err := windows.GetSecurityInfo(file, windows.SE_FILE_OBJECT, windows.DACL_SECURITY_INFORMATION|windows.OWNER_SECURITY_INFORMATION)
	if err != nil {
		return fmt.Errorf("read file access list: %w", err)
	}
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		return fmt.Errorf("read effective file user: %w", err)
	}
	owner, _, err := sd.Owner()
	if err != nil {
		return fmt.Errorf("read owner SID: %w", err)
	}
	if !trustedSID(owner, user.User.Sid) {
		return errors.New("unsafe file owner")
	}
	dacl, _, err := sd.DACL()
	if err != nil || dacl == nil {
		return errors.New("missing file access list")
	}
	return checkAccessList(dacl, user.User.Sid, private)
}

func checkAccessList(acl *windows.ACL, user *windows.SID, private bool) error {
	for i := range uint32(acl.AceCount) {
		var ace *windows.ACCESS_ALLOWED_ACE
		if err := windows.GetAce(acl, i, &ace); err != nil {
			return fmt.Errorf("read access list entry: %w", err)
		}
		switch ace.Header.AceType {
		case windows.ACCESS_DENIED_ACE_TYPE:
			continue
		case windows.ACCESS_ALLOWED_ACE_TYPE:
			if checkAllowedACE(ace, user, private) {
				continue
			}
		}
		return errors.New("unsafe file access list entry")
	}
	return nil
}

func checkAllowedACE(ace *windows.ACCESS_ALLOWED_ACE, user *windows.SID, private bool) bool {
	sid := (*windows.SID)(unsafe.Pointer(&ace.SidStart)) //nolint:gosec // G103: an allow ACE embeds its SID at SidStart.
	if private {
		return sid.Equals(user) && ace.Mask&^windows.FILE_GENERIC_READ == 0
	}
	const fileDeleteChild = 0x0040 // WinNT FILE_DELETE_CHILD.
	const writeRights = windows.FILE_WRITE_DATA | windows.FILE_APPEND_DATA | windows.FILE_WRITE_EA |
		windows.FILE_WRITE_ATTRIBUTES | fileDeleteChild | windows.DELETE | windows.WRITE_DAC |
		windows.WRITE_OWNER | windows.GENERIC_WRITE | windows.GENERIC_ALL
	return ace.Mask&writeRights == 0 || trustedSID(sid, user) ||
		ace.Header.AceFlags&windows.INHERIT_ONLY_ACE != 0 && sid.IsWellKnown(windows.WinCreatorOwnerSid)
}

func trustedSID(sid, user *windows.SID) bool {
	return sid != nil && (sid.Equals(user) || sid.IsWellKnown(windows.WinBuiltinAdministratorsSid) ||
		sid.IsWellKnown(windows.WinLocalSystemSid))
}
