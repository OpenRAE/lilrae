package process_test

import (
	"errors"
	"fmt"
	"math"
	"os"

	"golang.org/x/sys/windows"
)

func independentAlive(p *os.Process) error {
	if p.Pid <= 0 || uint64(p.Pid) > math.MaxUint32 {
		return errors.New("invalid fixture PID")
	}
	handle, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(p.Pid))
	if err != nil {
		return fmt.Errorf("open independent service: %w", err)
	}
	state, waitErr := windows.WaitForSingleObject(handle, 0)
	closeErr := windows.CloseHandle(handle)
	if err := errors.Join(waitErr, closeErr); err != nil {
		return fmt.Errorf("observe independent service: %w", err)
	}
	if state != uint32(windows.WAIT_TIMEOUT) {
		return errors.New("independent service exited")
	}
	return nil
}
