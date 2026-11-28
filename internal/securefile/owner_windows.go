package securefile

import (
	"errors"
	"fmt"
	"os"
	"unsafe"

	"golang.org/x/sys/windows"
)

func checkOwnedFile(file windows.Handle) error {
	var info windows.ByHandleFileInformation
	if err := windows.GetFileInformationByHandle(file, &info); err != nil {
		return fmt.Errorf("read file link count: %w", err)
	}
	if info.NumberOfLinks != 1 {
		return errors.New("file has more than one link")
	}
	sd, err := windows.GetSecurityInfo(file, windows.SE_FILE_OBJECT, windows.OWNER_SECURITY_INFORMATION)
	if err != nil {
		return fmt.Errorf("read file security descriptor: %w", err)
	}
	owner, _, err := sd.Owner()
	if err != nil {
		return fmt.Errorf("read file owner: %w", err)
	}
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		return fmt.Errorf("read current user: %w", err)
	}
	if owner.Equals(user.User.Sid) {
		return nil
	}
	// An elevated token can use Administrators as its default file owner.
	var tokenOwner struct {
		sid     *windows.SID
		storage [68]byte // SECURITY_MAX_SID_SIZE
	}
	var size uint32
	err = windows.GetTokenInformation(windows.GetCurrentProcessToken(), windows.TokenOwner,
		(*byte)(unsafe.Pointer(&tokenOwner)), uint32(unsafe.Sizeof(tokenOwner)), &size) //nolint:gosec // G103: TokenOwner fills the native pointer and in-buffer SID.
	if err != nil {
		return fmt.Errorf("read default file owner: %w", err)
	}
	if !owner.Equals(tokenOwner.sid) {
		return errors.New("file belongs to another user")
	}
	return nil
}

func (h dirHandle) createOwnerRead(op, path string, parts []string, data []byte) (err error) {
	parent, leaf, err := h.walkParent(op, path, parts, ruleCreate)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, parent.close()) }()
	dir, err := parent.root.Open(".")
	if err != nil {
		return failure(op, path, err)
	}
	defer func() { err = errors.Join(err, failure(op, path, dir.Close())) }()
	return failure(op, path, publishOwnerRead(windows.Handle(dir.Fd()), leaf, data))
}

func publishOwnerRead(dir windows.Handle, leaf string, data []byte) (err error) {
	file, err := newOwnerTemp(dir, leaf)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	handle := windows.Handle(file.Fd())
	if _, err = file.Write(data); err == nil {
		err = file.Sync()
	}
	if err == nil {
		err = setOwnerOnlyACL(handle)
	}
	if err == nil {
		err = renameOwnerTemp(handle, dir, leaf)
	}
	if err == nil {
		return nil
	}
	// The original handle retains delete access after the DACL changes.
	remove := byte(1) // FILE_DISPOSITION_INFORMATION.DeleteFile
	removeErr := windows.NtSetInformationFile(handle, &windows.IO_STATUS_BLOCK{}, &remove, 1,
		windows.FileDispositionInformation)
	return errors.Join(err, ntError(removeErr))
}

func newOwnerTemp(dir windows.Handle, leaf string) (*os.File, error) {
	const createAccess = windows.FILE_GENERIC_READ | windows.FILE_GENERIC_WRITE | windows.WRITE_DAC | windows.DELETE
	acl, err := currentUserACL(createAccess)
	if err != nil {
		return nil, err
	}
	sd, err := windows.NewSecurityDescriptor()
	if err != nil {
		return nil, fmt.Errorf("create private file security descriptor: %w", err)
	}
	if err := sd.SetDACL(acl, true, false); err != nil {
		return nil, fmt.Errorf("set private file DACL: %w", err)
	}
	if err := sd.SetControl(windows.SE_DACL_PROTECTED, windows.SE_DACL_PROTECTED); err != nil {
		return nil, fmt.Errorf("protect private file DACL: %w", err)
	}
	return openRelative(dir, tempName(leaf), createAccess, windows.FILE_CREATE, sd)
}

func renameOwnerTemp(file, dir windows.Handle, leaf string) error {
	name, err := windows.UTF16FromString(leaf)
	if err != nil {
		return fmt.Errorf("encode private file name: %w", err)
	}
	// FILE_RENAME_INFORMATION for an in-directory rename, with replacement
	// disabled. Use the still-open file handle, which retains DELETE access.
	info := struct {
		ReplaceIfExists uint32
		RootDirectory   windows.Handle
		FileNameLength  uint32
		FileName        [windows.MAX_PATH]uint16
	}{RootDirectory: dir}
	if len(name) > len(info.FileName) {
		return windows.ERROR_FILENAME_EXCED_RANGE
	}
	copy(info.FileName[:], name)
	info.FileNameLength = uint32((len(name) - 1) * 2) //nolint:gosec // G115: the native name includes a terminator and is bounded by MAX_PATH above.
	size := uint32(unsafe.Sizeof(info))
	return ntError(windows.NtSetInformationFile(file, &windows.IO_STATUS_BLOCK{},
		(*byte)(unsafe.Pointer(&info)), size, windows.FileRenameInformation)) //nolint:gosec // G103: NtSetInformationFile reads the native FILE_RENAME_INFORMATION layout.
}
