package process

import (
	"os"

	"golang.org/x/sys/unix"
)

// Darwin's FIONREAD is _IOR('f', 127, int). x/sys does not export its name.
const pendingBytes = 0x4004667f

// XNU's SZOMB means that the child awaits collection by its parent.
const zombie = 5

func (c *child) exited() (bool, error) {
	info, err := unix.SysctlKinfoProc("kern.proc.pid", c.pid)
	if err != nil || int(info.Proc.P_pid) != c.pid || int(info.Eproc.Ppid) != os.Getpid() {
		c.owned = false
		return false, ErrIO
	}
	return info.Proc.P_stat == zombie, nil
}

func (c *child) members() (bool, error) {
	exited, err := c.exited()
	if err != nil {
		return true, err
	}
	if !exited {
		return true, nil
	}
	group, err := unix.SysctlKinfoProcSlice("kern.proc.pgrp", c.pid)
	if err != nil {
		return true, ErrIO
	}
	for i := range group {
		if int(group[i].Proc.P_pid) != c.pid && group[i].Proc.P_stat != zombie {
			return true, nil
		}
	}
	return false, nil
}
