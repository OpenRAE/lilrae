package process

import (
	"errors"
	"math"
	"os"
	"slices"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
	"unsafe"

	"golang.org/x/sys/windows"
)

type child struct {
	process  windows.Handle
	job      windows.Handle
	pid      int
	groupID  uint32
	exitCode int
	reaped   bool
}

// The Windows SDK defines ProcThreadAttributeValue(JobList, FALSE, TRUE, FALSE).
const jobListAttribute = 0x0002000d

func launch(req Request, files []*os.File) (*child, error) {
	job, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return nil, ErrLaunch
	}
	c := &child{job: job, exitCode: -1}
	if configureErr := configureJob(job); configureErr != nil {
		c.close()
		return nil, configureErr
	}
	handles, err := inheritPipes(files)
	if err != nil {
		c.close()
		return nil, err
	}
	defer closeHandles(handles)
	attrs, err := windows.NewProcThreadAttributeList(2)
	if err != nil {
		c.close()
		return nil, ErrLaunch
	}
	defer attrs.Delete()
	if jobErr := attrs.Update(jobListAttribute, unsafe.Pointer(&job), unsafe.Sizeof(job)); jobErr != nil { //nolint:gosec // G103: the job-list attribute receives one live HANDLE with its exact size.
		c.close()
		return nil, ErrLaunch
	}
	if handleErr := attrs.Update(windows.PROC_THREAD_ATTRIBUTE_HANDLE_LIST, unsafe.Pointer(&handles[0]), uintptr(len(handles))*unsafe.Sizeof(handles[0])); handleErr != nil { //nolint:gosec // G103: this live three-HANDLE slice has the exact byte count required by the API.
		c.close()
		return nil, ErrLaunch
	}
	info, err := createProcess(req, handles, attrs)
	if err != nil {
		c.close()
		return nil, err
	}
	c.process, c.pid, c.groupID = info.Process, int(info.ProcessId), info.ProcessId
	closeHandles([]windows.Handle{info.Thread})
	return c, nil
}

func configureJob(job windows.Handle) error {
	limits := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	limits.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	if _, err := windows.SetInformationJobObject(job, windows.JobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&limits)), uint32(unsafe.Sizeof(limits))); err != nil { //nolint:gosec // G103: the SDK-defined limits structure remains live for this synchronous call.
		return ErrLaunch
	}
	return nil
}

func inheritPipes(files []*os.File) ([]windows.Handle, error) {
	handles := make([]windows.Handle, 0, len(files))
	for _, f := range files {
		var handle windows.Handle
		if err := windows.DuplicateHandle(windows.CurrentProcess(), windows.Handle(f.Fd()), windows.CurrentProcess(), &handle, 0, true, windows.DUPLICATE_SAME_ACCESS); err != nil {
			closeHandles(handles)
			return nil, ErrLaunch
		}
		handles = append(handles, handle)
	}
	return handles, nil
}

func createProcess(req Request, handles []windows.Handle, attrs *windows.ProcThreadAttributeListContainer) (windows.ProcessInformation, error) {
	info := windows.ProcessInformation{}
	for _, value := range append(append([]string{req.Dir}, req.Argv...), req.Env...) {
		if !utf8.ValidString(value) {
			return info, ErrLaunch
		}
	}
	application, err := windows.UTF16PtrFromString(req.Argv[0])
	if err != nil {
		return info, ErrLaunch
	}
	command, err := windows.UTF16PtrFromString(windows.ComposeCommandLine(req.Argv))
	if err != nil {
		return info, ErrLaunch
	}
	dir, err := windows.UTF16PtrFromString(req.Dir)
	if err != nil {
		return info, ErrLaunch
	}
	env := slices.Clone(req.Env)
	slices.SortFunc(env, func(a, b string) int { return strings.Compare(strings.ToUpper(a), strings.ToUpper(b)) })
	block := utf16.Encode([]rune(strings.Join(env, "\x00") + "\x00\x00"))
	startup := windows.StartupInfoEx{ProcThreadAttributeList: attrs.List()}
	startup.Cb = uint32(unsafe.Sizeof(startup))
	startup.Flags = windows.STARTF_USESTDHANDLES
	startup.StdInput, startup.StdOutput, startup.StdErr = handles[0], handles[1], handles[2]
	flags := uint32(windows.EXTENDED_STARTUPINFO_PRESENT | windows.CREATE_UNICODE_ENVIRONMENT | windows.CREATE_NEW_PROCESS_GROUP)
	err = windows.CreateProcess(application, command, nil, nil, true, flags, &block[0], dir, &startup.StartupInfo, &info)
	if err != nil {
		return info, ErrLaunch
	}
	return info, nil
}

func (c *child) exited() (bool, error) {
	state, err := windows.WaitForSingleObject(c.process, 0)
	if err != nil {
		return false, ErrIO
	}
	return state == windows.WAIT_OBJECT_0, nil
}

// jobAccounting matches JOBOBJECT_BASIC_ACCOUNTING_INFORMATION in the SDK.
type jobAccounting struct {
	UserTime         int64
	KernelTime       int64
	PeriodUserTime   int64
	PeriodKernelTime int64
	PageFaults       uint32
	Total            uint32
	Active           uint32
	Terminated       uint32
}

func (c *child) members() (bool, error) {
	var accounting jobAccounting
	err := windows.QueryInformationJobObject(c.job, windows.JobObjectBasicAccountingInformation, uintptr(unsafe.Pointer(&accounting)), uint32(unsafe.Sizeof(accounting)), nil) //nolint:gosec // G103: the SDK accounting layout has its exact size and remains live through the call.
	if err != nil {
		return true, ErrIO
	}
	return accounting.Active > 0, nil
}

func (c *child) stop(force bool) bool {
	if force {
		if err := windows.TerminateJobObject(c.job, 1); err != nil {
			return false
		}
		return true
	}
	// Console control is cooperative and can be unavailable in a headless
	// session. The retained job still bounds cleanup through forced stop.
	if err := windows.GenerateConsoleCtrlEvent(windows.CTRL_BREAK_EVENT, c.groupID); err != nil {
		return false
	}
	return true
}

func (c *child) reap() bool {
	if c.reaped {
		return true
	}
	exited, err := c.exited()
	if err != nil || !exited {
		return false
	}
	var code uint32
	if err := windows.GetExitCodeProcess(c.process, &code); err != nil {
		return false
	}
	c.reaped, c.exitCode = true, int(code)
	return true
}

func (c *child) gone() (bool, error) {
	members, err := c.members()
	return !members, err
}

func (c *child) close() {
	closeHandles([]windows.Handle{c.process, c.job})
	c.process, c.job = 0, 0
}

func closeHandles(handles []windows.Handle) {
	for _, handle := range handles {
		if handle == 0 {
			continue
		}
		if err := windows.CloseHandle(handle); err != nil {
			continue
		}
	}
}

func environmentKey(key string) string { return strings.ToUpper(key) }

func available(f *os.File) (count int, closed bool, err error) {
	var availableBytes uint32
	// Go's os.Pipe uses asynchronous handles. Peek never shares a handle
	// with a pending read, and only this supervisor reads these pipes.
	peek := windows.NewLazySystemDLL("kernel32.dll").NewProc("PeekNamedPipe")
	ok, _, err := peek.Call(f.Fd(), 0, 0, 0, uintptr(unsafe.Pointer(&availableBytes)), 0) //nolint:gosec // G103: PeekNamedPipe writes one DWORD to a live uint32 for this synchronous call.
	if ok == 0 {
		if errors.Is(err, windows.ERROR_BROKEN_PIPE) {
			return 0, true, nil
		}
		return 0, false, ErrIO
	}
	if uint64(availableBytes) > math.MaxInt {
		return 0, false, ErrIO
	}
	return int(availableBytes), false, nil
}
