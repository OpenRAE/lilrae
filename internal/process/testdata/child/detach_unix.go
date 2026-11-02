//go:build linux || darwin

package main

import (
	"os"
	"os/exec"
	"syscall"
)

func detach(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }

func selfSignal() { check(syscall.Kill(os.Getpid(), syscall.SIGTERM)) }
