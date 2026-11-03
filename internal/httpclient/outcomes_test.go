package httpclient

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"os"
	"strings"
	"syscall"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }

func TestSharedOutcomeCases(t *testing.T) {
	data, err := os.ReadFile("../../conformance/testdata/http-outcomes.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []outcomeCase
	if err := json.Unmarshal(data, &cases, json.RejectUnknownMembers(true)); err != nil {
		t.Fatal(err)
	}
	for _, tc := range cases {
		t.Run(tc.ID, func(t *testing.T) {
			checkOutcomeCase(t, tc)
		})
	}
}

func nativeCause(id string) error {
	switch id {
	case "refused":
		return &net.OpError{Op: "dial", Err: syscall.ECONNREFUSED}
	case "timeout":
		return &net.DNSError{IsTimeout: true}
	case "handshake":
		return io.EOF
	case "empty":
		return io.EOF
	case "reset":
		return &net.OpError{Op: "read", Err: syscall.ECONNRESET}
	case "certificate":
		return &tls.CertificateVerificationError{Err: x509.UnknownAuthorityError{}}
	case "other":
		return &net.DNSError{Err: "synthetic-secret"}
	case "request-timeout":
		return context.DeadlineExceeded
	default:
		return errors.New("synthetic-secret")
	}
}

type trackedBody struct {
	reader   io.Reader
	closed   bool
	closeErr error
}

func (b *trackedBody) Read(p []byte) (int, error) {
	n, err := b.reader.Read(p)
	if err != nil {
		return n, fmt.Errorf("test body: %w", err)
	}
	return n, nil
}
func (b *trackedBody) Close() error { b.closed = true; return b.closeErr }

func TestStreamBoundsAndClosure(t *testing.T) {
	for _, tc := range []struct {
		name, body string
		wantErr    error
	}{
		{"empty", "", nil}, {"below", "abc", nil}, {"exact", "abcd", nil},
		{"above", "abcde", ErrResponseLimit},
	} {
		t.Run(tc.name, func(t *testing.T) {
			body := &trackedBody{reader: strings.NewReader(tc.body)}
			client := &Client{timeout: time.Minute, maxBody: 4, transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
				return &http.Response{StatusCode: http.StatusOK, Request: req, Body: body}, nil
			})}
			req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, "https://example.test/", http.NoBody)
			if err != nil {
				t.Fatal(err)
			}
			response := client.Do(t.Context(), req)
			got, err := io.ReadAll(response)
			if !errors.Is(err, tc.wantErr) || len(got) > 4 || !body.closed || response.StatusCode != http.StatusOK || response.Category != HTTPResponse {
				t.Fatalf("read %d bytes, error %v, closed %v, response %v", len(got), err, body.closed, response)
			}
			if err := response.Close(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestOriginIncludesSchemeHostAndEffectivePort(t *testing.T) {
	for _, tc := range []struct {
		a, b string
		want bool
	}{
		{"https://EXAMPLE.test/a", "https://example.test:443/b", true},
		{"http://example.test", "http://example.test:80", true},
		{"https://example.test", "https://example.test:444", false},
		{"https://example.test", "https://sub.example.test", false},
		{"https://example.test", "http://example.test", false},
	} {
		a, err := url.Parse(tc.a)
		if err != nil {
			t.Fatal(err)
		}
		b, err := url.Parse(tc.b)
		if err != nil {
			t.Fatal(err)
		}
		if got := sameOrigin(a, b); got != tc.want {
			t.Errorf("sameOrigin(%q, %q) = %v, want %v", tc.a, tc.b, got, tc.want)
		}
	}
}

type outcomeCase struct {
	ID       string   `json:"id"`
	Exit     *int     `json:"exit"`
	Status   int      `json:"status"`
	Failure  string   `json:"failure"`
	Category Category `json:"category"`
}

func checkOutcomeCase(t *testing.T, tc outcomeCase) {
	t.Helper()

	// There is no executable startup in native HTTP. Keep the spelling
	// for compatibility, and prove every native producer below excludes it.
	if tc.ID == "unavailable" {
		if tc.Category != CurlUnavailable || tc.Exit != nil {
			t.Fatal("invalid unavailable compatibility case")
		}
		return
	}
	cause := nativeCause(tc.ID)
	client := &Client{timeout: time.Minute, maxBody: 1024, transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
		if tc.Status != 0 {
			return &http.Response{StatusCode: tc.Status, Request: req, Body: io.NopCloser(strings.NewReader("{}"))}, nil
		}
		if tc.ID == "handshake" {
			httptrace.ContextClientTrace(req.Context()).TLSHandshakeDone(tls.ConnectionState{}, cause)
		}
		return nil, &url.Error{Op: "request", URL: "https://example.test/?token=synthetic-secret", Err: cause}
	})}
	ctx := t.Context()
	if tc.ID == "request-timeout" {
		var cancel context.CancelFunc
		ctx, cancel = context.WithDeadline(ctx, time.Now().Add(-time.Second))
		defer cancel()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://example.test/", http.NoBody)
	if err != nil {
		t.Fatal(err)
	}
	response := client.Do(ctx, req)
	if err := response.Close(); err != nil {
		t.Fatal(err)
	}
	if response.Category != tc.Category || response.StatusCode != tc.Status || response.Category == CurlUnavailable {
		t.Fatalf("response = %v, want %s, HTTP %d", response, tc.Category, tc.Status)
	}
	if strings.Contains(fmt.Sprintf("%v %#v %+v", response, response, response.Err), "synthetic-secret") {
		t.Fatal("response exposed a raw cause")
	}
}
