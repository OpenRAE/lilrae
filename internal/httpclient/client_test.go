package httpclient_test

import (
	"context"
	"crypto/tls"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/httpclient"
)

func options() httpclient.Options {
	return httpclient.Options{
		TLS:     &tls.Config{MinVersion: tls.VersionTLS12},
		Timeout: time.Minute, PhaseTimeout: 30 * time.Second,
		MaxHeaderBytes: 1 << 20, MaxBodyBytes: 1 << 20,
	}
}

func TestHTTPStatusesAndStreaming(t *testing.T) {
	for _, status := range []int{200, 204, 401, 403, 500} {
		t.Run(http.StatusText(status), func(t *testing.T) { checkHTTPStatus(t, status) })
	}
}

func checkHTTPStatus(t *testing.T, status int) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-Response", "value")
		w.WriteHeader(status)
		if status != http.StatusNoContent {
			writeText(t, w, "not JSON")
		}
	}))
	t.Cleanup(server.Close)
	response := request(t, newClient(t, options()), http.MethodGet, server.URL, http.NoBody)
	if response.Category != httpclient.HTTPResponse || response.StatusCode != status || response.Err != nil {
		t.Fatalf("response = %v, want HTTP %d", response, status)
	}
	body, err := io.ReadAll(response)
	if err != nil {
		t.Fatal(err)
	}
	want := "not JSON"
	if status == http.StatusNoContent {
		want = ""
	}
	if string(body) != want || response.Header().Get("X-Response") != "value" || response.URL().String() != server.URL {
		t.Error("response body, headers, or identity did not survive")
	}
}

func writeText(t *testing.T, w io.Writer, text string) {
	t.Helper()
	if _, err := io.WriteString(w, text); err != nil {
		t.Error(err)
	}
}

func makeRequest(ctx context.Context, t *testing.T, method, endpoint string, body io.Reader) *http.Request {
	t.Helper()
	req, err := http.NewRequestWithContext(ctx, method, endpoint, body)
	if err != nil {
		t.Fatal(err)
	}
	return req
}

func closeResponse(t *testing.T, response *httpclient.Response) {
	t.Helper()
	if err := response.Close(); err != nil {
		t.Error(err)
	}
}

// A consumer owns the interface; the foundation returns a concrete client.
type requester interface {
	Do(ctx context.Context, req *http.Request) *httpclient.Response
}

var _ requester = (*httpclient.Client)(nil)
