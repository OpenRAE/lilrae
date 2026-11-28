package securefile

import (
	"encoding/binary"
	"errors"
	"fmt"
	"slices"
	"syscall"
	"unsafe"

	"golang.org/x/sys/unix"
)

// Darwin's kauth_filesec layout holds a 44-byte header and up to 128
// 24-byte access list entries. See sys/kauth.h.
const (
	darwinACLHeader = 44
	darwinACEBytes  = 24
	darwinMaxACEs   = 128
)

type darwinSecurity struct {
	Size     uint32
	Offset   int32
	Length   uint32
	Security [darwinACLHeader + darwinMaxACEs*darwinACEBytes]byte
}

// checkExtendedACL asks Darwin for the extended security of the retained file.
// A public file or directory can have read grants. A private file cannot.
func checkExtendedACL(fd int, forbidden uint32) error {
	attrs := unix.Attrlist{Bitmapcount: unix.ATTR_BIT_MAP_COUNT, Commonattr: unix.ATTR_CMN_EXTENDED_SECURITY}
	var result darwinSecurity
	_, _, errno := syscall.Syscall6(syscall.SYS_FGETATTRLIST, uintptr(fd),
		uintptr(unsafe.Pointer(&attrs)), uintptr(unsafe.Pointer(&result)), unsafe.Sizeof(result), 0, 0) //nolint:gosec // G103: native attrlist and bounded response buffer.
	if errno != 0 {
		return fmt.Errorf("read Darwin extended security: %w", errno)
	}
	return result.check(forbidden == groupOrOtherAccess)
}

func (result *darwinSecurity) check(private bool) error {
	// The 4-byte size precedes an 8-byte attrreference. The offset is
	// relative to that reference, so its payload starts 8 bytes later.
	const dataStart = 12
	if result.Size < dataStart {
		return errors.New("incomplete Darwin extended security")
	}
	if result.Length == 0 {
		return nil
	}
	if result.Offset != 8 || result.Length > uint32(len(result.Security)) ||
		result.Size < dataStart+result.Length {
		return errors.New("invalid Darwin extended security")
	}
	return checkDarwinACL(result.Security[:result.Length], private)
}

func checkDarwinACL(security []byte, private bool) error {
	const kauthFilesecMagic = 0x012cc16d
	if len(security) < darwinACLHeader || binary.NativeEndian.Uint32(security) != kauthFilesecMagic {
		return errors.New("invalid Darwin access list")
	}
	count := binary.NativeEndian.Uint32(security[36:40])
	if count == ^uint32(0) { // KAUTH_FILESEC_NOACL, for owner or group metadata only.
		count = 0
	}
	if count > darwinMaxACEs || int64(len(security)) != darwinACLHeader+int64(count)*darwinACEBytes {
		return errors.New("invalid Darwin access list size")
	}
	if private && count != 0 {
		return errors.New("extended access list prevents owner-only verification")
	}
	for entry := range slices.Chunk(security[darwinACLHeader:], darwinACEBytes) {
		if !readonlyDarwinACE(entry) {
			return errors.New("extended access list can grant write access")
		}
	}
	return nil
}

func readonlyDarwinACE(entry []byte) bool {
	const (
		kindMask = 0xf
		permit   = 1
		deny     = 2
		// Read data, search or execute, read attributes, read extended
		// attributes, read security, sync, and generic read or execute.
		readOnly = 1<<1 | 1<<3 | 1<<7 | 1<<9 | 1<<11 | 1<<20 | 1<<22 | 1<<24
	)
	kind := binary.NativeEndian.Uint32(entry[16:20]) & kindMask
	rights := binary.NativeEndian.Uint32(entry[20:24])
	return kind == deny || kind == permit && rights&^readOnly == 0
}
