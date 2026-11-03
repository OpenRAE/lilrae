package httpclient

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
)

// Response holds safe outcome metadata and a bounded raw response stream.
// Header and URL explicitly expose sensitive values; formatting does not.
// Read and Close must not run concurrently.
//
//nolint:recvcheck // Formatting must protect copied values; stream methods need pointer receivers to preserve ownership.
type Response struct {
	Category     Category
	StatusCode   int
	Err          error `json:"-"`
	header       http.Header
	url          *url.URL
	body         io.ReadCloser
	remaining    int64
	contextError func() error
	cancel       context.CancelFunc
}

// String returns only the category and HTTP status.
func (r Response) String() string {
	return fmt.Sprintf("httpclient: %s (HTTP %d)", r.Category, r.StatusCode)
}

// GoString keeps Go-syntax formatting free of response secrets.
func (r Response) GoString() string { return r.String() }

// Header returns a copy of the response headers. Values can contain secrets.
func (r *Response) Header() http.Header { return r.header.Clone() }

// URL returns a copy of the final URL for caller-owned response admission.
// It must not be used as a diagnostic value.
func (r *Response) URL() *url.URL {
	if r.url == nil {
		return nil
	}
	u := *r.url
	return &u
}

// Read streams at most the configured body limit. It never silently truncates.
// EOF, overflow, and read errors close the body and release the operation budget.
func (r *Response) Read(p []byte) (int, error) {
	if len(p) == 0 {
		return 0, nil
	}
	if r.body == nil {
		if r.Err != nil {
			return 0, r.Err
		}
		return 0, io.EOF
	}
	if err := r.contextFailure(); err != nil {
		return 0, r.finish(err)
	}
	if r.remaining == 0 {
		return r.checkEnd()
	}
	n, err := r.body.Read(p[:min(int64(len(p)), r.remaining)])
	r.remaining -= int64(n)
	return n, r.readError(err)
}

func (r *Response) checkEnd() (int, error) {
	var extra [1]byte
	n, err := r.body.Read(extra[:])
	if n > 0 {
		return 0, r.finish(ErrResponseLimit)
	}
	return 0, r.readError(err)
}

func (r *Response) readError(err error) error {
	if contextErr := r.contextFailure(); contextErr != nil {
		return r.finish(contextErr)
	}
	if err == nil {
		return nil
	}
	if errors.Is(err, io.EOF) {
		if closeErr := r.finish(nil); closeErr != nil {
			return closeErr
		}
		return io.EOF
	}
	return r.finish(ErrResponseRead)
}

func (r *Response) contextFailure() error {
	if errors.Is(r.contextError(), context.DeadlineExceeded) {
		return ErrRequestTimeout
	}
	if errors.Is(r.contextError(), context.Canceled) {
		return context.Canceled
	}
	return nil
}

// Close releases the response without draining it. It is safe to call repeatedly.
func (r *Response) Close() error { return r.finish(nil) }

func (r *Response) finish(err error) error {
	if r.body != nil {
		if closeErr := r.body.Close(); closeErr != nil && err == nil {
			err = ErrResponseRead
		}
		r.body = nil
	}
	if r.cancel != nil {
		r.cancel()
	}
	return err
}
