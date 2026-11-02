package process

import (
	"os"
)

type output struct {
	file   *os.File
	closed bool
	data   []byte
}

type exchange struct {
	input     *os.File
	children  []*os.File
	stdout    output
	stderr    output
	remaining int
	inputDone chan struct{}
}

func openExchange(limit int) (*exchange, error) {
	x := &exchange{remaining: limit}
	for i := range 3 {
		r, w, err := os.Pipe()
		if err != nil {
			x.closeChildFiles()
			x.close()
			return nil, ErrIO
		}
		switch i {
		case 0:
			x.children = append(x.children, r)
			x.input = w
		case 1:
			x.stdout.file = r
			x.children = append(x.children, w)
		case 2:
			x.stderr.file = r
			x.children = append(x.children, w)
		}
	}
	return x, nil
}

func (x *exchange) childFiles() []*os.File { return x.children }

func (x *exchange) closeChildFiles() {
	for _, f := range x.children {
		closeFile(f)
	}
	x.children = nil
}

func (x *exchange) sendInput(data []byte) {
	x.inputDone = make(chan struct{})
	go func() {
		// os.File.Write handles short writes. Early stdin closure is allowed,
		// and every other end of this pipe is owned by the supervisor.
		if _, err := x.input.Write(data); err != nil {
			close(x.inputDone)
			return
		}
		closeFile(x.input)
		close(x.inputDone)
	}()
}

func (x *exchange) stopInput() {
	closeFile(x.input)
	if x.inputDone != nil {
		<-x.inputDone
		x.inputDone = nil
	}
}

func (x *exchange) pump(capture, snapshot bool) error {
	for _, out := range []*output{&x.stdout, &x.stderr} {
		if out.closed {
			continue
		}
		count, closed, err := available(out.file)
		if err != nil {
			return ErrIO
		}
		if count == 0 && closed {
			out.closed = true
			continue
		}
		if !snapshot {
			count = min(count, 65536)
		}
		if err := x.take(out, count, capture); err != nil {
			return err
		}
	}
	return nil
}

func (x *exchange) take(out *output, count int, capture bool) error {
	var buf [65536]byte
	for count > 0 {
		n, err := out.file.Read(buf[:min(count, len(buf))])
		if err != nil {
			return ErrIO
		}
		if n == 0 {
			return ErrIO
		}
		count -= n
		if capture {
			admitted := min(n, x.remaining)
			out.data = append(out.data, buf[:admitted]...)
			x.remaining -= admitted
			if admitted < n {
				return ErrOverflow
			}
		}
	}
	return nil
}

func (x *exchange) discard() {
	if err := x.pump(false, false); err != nil {
		// A failed pipe observation is not EOF. Leave it open so the bounded
		// release phase reports uncertainty instead of a successful cleanup.
		return
	}
}

func (x *exchange) close() {
	x.stopInput()
	closeFile(x.stdout.file)
	closeFile(x.stderr.file)
}

func closeFile(f *os.File) {
	if f != nil {
		// Closing an already closed pipe is harmless. All observable holders
		// are reported separately before the final close.
		if err := f.Close(); err != nil {
			return
		}
	}
}
