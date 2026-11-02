//go:build linux || darwin

package process

import (
	"errors"
	"math"
	"os"
	"syscall"

	"golang.org/x/sys/unix"
)

type child struct {
	process  *os.Process
	pid      int
	exitCode int
	reaped   bool
	owned    bool
}

func launch(req Request, files []*os.File) (*child, error) {
	p, err := os.StartProcess(req.Argv[0], req.Argv, &os.ProcAttr{Dir: req.Dir, Env: append([]string{}, req.Env...), Files: files, Sys: &syscall.SysProcAttr{Setsid: true}})
	if err != nil {
		return nil, ErrLaunch
	}
	return &child{process: p, pid: p.Pid, owned: true, exitCode: -1}, nil
}

func (c *child) stop(force bool) bool {
	if !c.owned || c.reaped {
		return false
	}
	number := unix.SIGTERM
	if force {
		number = unix.SIGKILL
	}
	// The unreaped direct child reserves this identifier. Permission denial
	// is not evidence of disappearance; membership is checked independently.
	if err := unix.Kill(-c.pid, number); err != nil {
		return false
	}
	return true
}

func (c *child) reap() bool {
	if c.reaped {
		return true
	}
	var status unix.WaitStatus
	pid, err := unix.Wait4(c.pid, &status, unix.WNOHANG, nil)
	if err != nil || pid != c.pid {
		return false
	}
	c.reaped, c.owned = true, false
	c.exitCode = status.ExitStatus()
	if status.Signaled() {
		c.exitCode = -int(status.Signal())
	}
	return true
}

func (c *child) gone() (bool, error) {
	if !c.reaped {
		return false, nil
	}
	err := unix.Kill(-c.pid, 0)
	if errors.Is(err, unix.ESRCH) {
		return true, nil
	}
	if err != nil {
		return false, ErrIO
	}
	return false, nil
}

func (c *child) close() {
	if err := c.process.Release(); err != nil {
		return
	}
}

func environmentKey(key string) string { return key }

func available(f *os.File) (count int, closed bool, err error) {
	fd := int(f.Fd())
	if fd < 0 || fd > math.MaxInt32 {
		return 0, false, ErrIO
	}
	poll := []unix.PollFd{{Fd: int32(fd), Events: unix.POLLIN}}
	if _, pollErr := unix.Poll(poll, 0); pollErr != nil {
		if errors.Is(pollErr, unix.EINTR) {
			return 0, false, nil
		}
		return 0, false, ErrIO
	}
	count, err = unix.IoctlGetInt(fd, pendingBytes)
	if err != nil {
		if errors.Is(err, unix.EINTR) {
			return 0, false, nil
		}
		return 0, false, ErrIO
	}
	return count, poll[0].Revents&unix.POLLHUP != 0, nil
}
