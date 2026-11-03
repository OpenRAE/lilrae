package httpclient

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"
)

type errorReader struct{ err error }

func (r errorReader) Read([]byte) (int, error) { return 0, r.err }

func TestStreamFailureProjection(t *testing.T) {
	for _, tc := range []struct {
		name              string
		readErr, closeErr error
	}{
		{"read", errors.New("synthetic-secret"), nil},
		{"close-after-eof", io.EOF, errors.New("synthetic-secret")},
		{"read-and-close", io.ErrUnexpectedEOF, errors.New("synthetic-secret")},
	} {
		t.Run(tc.name, func(t *testing.T) {
			body := &trackedBody{reader: errorReader{tc.readErr}, closeErr: tc.closeErr}
			response := &Response{Category: HTTPResponse, StatusCode: http.StatusOK, body: body, remaining: 10, contextError: func() error { return nil }}
			_, err := io.ReadAll(response)
			if !errors.Is(err, ErrResponseRead) || !body.closed {
				t.Fatalf("read error %v, closed %v", err, body.closed)
			}
			if closeErr := response.Close(); closeErr != nil {
				t.Fatal(closeErr)
			}
		})
	}
}

func TestExplicitCloseFailureAndZeroReads(t *testing.T) {
	body := &trackedBody{reader: strings.NewReader("body"), closeErr: errors.New("synthetic-secret")}
	response := &Response{body: body, remaining: 4}
	if n, err := response.Read(nil); n != 0 || err != nil || body.closed {
		t.Fatal("zero read changed the stream")
	}
	if err := response.Close(); !errors.Is(err, ErrResponseRead) || !body.closed {
		t.Fatalf("close error = %v", err)
	}
	if n, err := response.Read(make([]byte, 1)); n != 0 || !errors.Is(err, io.EOF) {
		t.Fatal("closed stream remains readable")
	}
	response = &Response{Err: errTransport}
	if _, err := response.Read(make([]byte, 1)); !errors.Is(err, errTransport) || response.URL() != nil {
		t.Fatal("failure metadata lost")
	}
}

func TestAdditionalTypedFailures(t *testing.T) {
	for _, tc := range []struct {
		name  string
		cause error
		want  Category
	}{
		{"protocol", errors.New("synthetic-secret"), CurlError},
		{"unexpected-eof", io.ErrUnexpectedEOF, ConnectionReset},
		{"caller-cancellation", context.Canceled, CurlError},
		{"write", &net.OpError{Op: "write", Err: errors.New("synthetic-secret")}, ConnectionReset},
	} {
		t.Run(tc.name, func(t *testing.T) {
			client := &Client{timeout: time.Minute, transport: roundTripFunc(func(*http.Request) (*http.Response, error) { return nil, tc.cause })}
			req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "https://example.test/", http.NoBody)
			if err != nil {
				t.Fatal(err)
			}
			response := client.Do(t.Context(), req)
			if response.Category != tc.want || response.Err == nil {
				t.Fatalf("response = %v", response)
			}
		})
	}
}

func TestExpiredBudgetRejectsBufferedBody(t *testing.T) {
	body := &trackedBody{reader: strings.NewReader("buffered secret")}
	response := &Response{body: body, remaining: 100, contextError: func() error { return context.DeadlineExceeded }}
	bytes, err := io.ReadAll(response)
	if len(bytes) != 0 || !errors.Is(err, ErrRequestTimeout) || !body.closed {
		t.Fatalf("expired stream read %d bytes, error %v, closed %v", len(bytes), err, body.closed)
	}
}
