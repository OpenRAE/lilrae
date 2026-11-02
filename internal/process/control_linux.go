package process

import (
	"errors"
	"io/fs"
	"os"
	"strconv"
	"strings"

	"golang.org/x/sys/unix"
)

const pendingBytes = unix.TIOCINQ

func (c *child) exited() (bool, error) {
	var info unix.Siginfo
	if err := unix.Waitid(unix.P_PID, c.pid, &info, unix.WEXITED|unix.WNOHANG|unix.WNOWAIT, nil); err != nil {
		if errors.Is(err, unix.EINTR) {
			return false, nil
		}
		if errors.Is(err, unix.ECHILD) {
			c.owned = false
		}
		return false, ErrIO
	}
	return info.Signo != 0, nil
}

func (c *child) members() (bool, error) {
	exited, err := c.exited()
	if err != nil {
		return true, err
	}
	if !exited {
		return true, nil
	}
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return true, ErrIO
	}
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil || pid == c.pid {
			continue
		}
		data, err := os.ReadFile("/proc/" + entry.Name() + "/stat")
		if errors.Is(err, fs.ErrNotExist) {
			continue
		}
		if err != nil {
			return true, ErrIO
		}
		member, err := liveGroupMember(data, c.pid)
		if err != nil || member {
			return true, err
		}
	}
	return false, nil
}

func liveGroupMember(data []byte, group int) (bool, error) {
	// comm can contain spaces and parentheses. Fields after its last ')'
	// start with state, parent PID, and process group ID.
	i := strings.LastIndex(string(data), ") ")
	if i < 0 {
		return false, ErrIO
	}
	parts := strings.Fields(string(data[i+2:]))
	if len(parts) < 3 {
		return false, ErrIO
	}
	pgid, err := strconv.Atoi(parts[2])
	if err != nil {
		return false, ErrIO
	}
	return pgid == group && parts[0] != "Z" && parts[0] != "X", nil
}
