//go:build windows

package securefile

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/sys/windows"
)

// The prefixes of a final path name. Python removes them, so Resolve does.
const (
	longPrefix    = `\\?\`
	longUNCPrefix = `\\?\UNC\`
)

// resolve applies the rules of ntpath.realpath with strict=False: it
// normalizes the path, reads the final path of the longest leading part
// that exists, and joins the rest as written.
func resolve(path string) (string, error) {
	abs, err := filepath.Abs(path)
	if err != nil {
		return "", failure("resolve", path, err)
	}
	var tail []string
	for current := abs; ; {
		if final, err := finalPath(current); err == nil {
			return filepath.Join(append([]string{final}, tail...)...), nil
		}
		// The system cannot open a link with a missing target, so Python
		// follows the link itself.
		if linked := readlinkDeep(current); linked != current {
			return filepath.Join(append([]string{linked}, tail...)...), nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			return abs, nil
		}
		tail = append([]string{filepath.Base(current)}, tail...)
		current = parent
	}
}

// readlinkDeep follows the chain of links at path, as ntpath._readlink_deep
// of Python does. It stops at a loop, at an entry that is not a link, and at
// a relative target of a reparse point that is not a symbolic link.
func readlinkDeep(path string) string {
	seen := map[string]bool{}
	for !seen[strings.ToLower(path)] {
		seen[strings.ToLower(path)] = true
		target, err := os.Readlink(path)
		if err != nil {
			break
		}
		if !filepath.IsAbs(target) {
			info, err := os.Lstat(path)
			if err != nil || info.Mode()&fs.ModeSymlink == 0 {
				break
			}
			target = filepath.Join(filepath.Dir(path), target)
		}
		path = target
	}
	return path
}

// finalPath returns the final path of the existing file or directory path,
// with each link and junction resolved.
func finalPath(path string) (final string, err error) {
	name, err := windows.UTF16PtrFromString(path)
	if err != nil {
		return "", failure("resolve", path, err)
	}
	// FILE_FLAG_BACKUP_SEMANTICS opens a directory. No access right is
	// needed to read the name.
	handle, err := windows.CreateFile(name, 0, windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE|windows.FILE_SHARE_DELETE,
		nil, windows.OPEN_EXISTING, windows.FILE_FLAG_BACKUP_SEMANTICS, 0)
	if err != nil {
		return "", failure("resolve", path, err)
	}
	defer func() {
		if closeErr := windows.CloseHandle(handle); err == nil {
			err = failure("resolve", path, closeErr)
		}
	}()
	// A result that does not fit gives the size that it needs.
	for size := uint32(windows.MAX_PATH); ; {
		buf := make([]uint16, size)
		// The flags 0 are FILE_NAME_NORMALIZED and VOLUME_NAME_DOS.
		n, err := windows.GetFinalPathNameByHandle(handle, &buf[0], size, 0)
		if err != nil {
			return "", failure("resolve", path, err)
		}
		if n < size {
			return trimLongPrefix(windows.UTF16ToString(buf[:n])), nil
		}
		size = n
	}
}

// trimLongPrefix removes the \\?\ prefix of a final path name, and gives a
// UNC path its \\ form.
func trimLongPrefix(path string) string {
	if rest, ok := strings.CutPrefix(path, longUNCPrefix); ok {
		return `\\` + rest
	}
	return strings.TrimPrefix(path, longPrefix)
}
