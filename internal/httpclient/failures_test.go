package httpclient_test

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/httpclient"
)

func TestRealTransportFailures(t *testing.T) {
	for _, reset := range []bool{false, true} {
		t.Run(fmt.Sprint("reset=", reset), func(t *testing.T) {
			checkSocketFailure(t, reset)
		})
	}
	listener, err := new(net.ListenConfig).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	endpoint := "http://" + listener.Addr().String()
	if err := listener.Close(); err != nil {
		t.Fatal(err)
	}
	if got := request(t, newClient(t, options()), http.MethodGet, endpoint, nil); got.Category != httpclient.ConnectionRefused {
		t.Fatalf("closed listener = %v", got)
	}
	plain := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }))
	t.Cleanup(plain.Close)
	if got := request(t, newClient(t, options()), http.MethodGet, strings.Replace(plain.URL, "http:", "https:", 1), nil); got.Category != httpclient.TLSHandshake {
		t.Fatalf("HTTP peer during TLS = %v", got)
	}
}

func TestRefusedProxyIsAConnectionFailure(t *testing.T) {
	listener, err := new(net.ListenConfig).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	proxyURL, err := url.Parse("http://" + listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	if err := listener.Close(); err != nil {
		t.Fatal(err)
	}
	opts := options()
	opts.Proxy = http.ProxyURL(proxyURL)
	response := request(t, newClient(t, opts), http.MethodGet, "https://127.0.0.1:1/", http.NoBody)
	if response.Category != httpclient.ConnectionRefused {
		t.Fatalf("refused proxy = %v", response)
	}
}

func TestHeaderAndBodyFailuresKeepSafeMetadata(t *testing.T) {
	for _, tc := range []streamFailureCase{
		{"exact", "abcd", 0, true, nil},
		{"chunked-over", "abcde", 0, true, httpclient.ErrResponseLimit},
		{"declared-over", "abcde", 5, false, httpclient.ErrResponseLimit},
		{"truncated", "abc", 10, false, httpclient.ErrResponseRead},
	} {
		t.Run(tc.name, func(t *testing.T) {
			checkStreamFailure(t, tc)
		})
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("X-Large", strings.Repeat("x", 8192))
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)
	opts := options()
	opts.MaxHeaderBytes = 1024
	response := request(t, newClient(t, opts), http.MethodGet, server.URL, nil)
	if response.Category != httpclient.CurlError || response.Err == nil {
		t.Fatalf("header limit = %v", response)
	}
}

func TestMalformedRedirectStillHasHTTPStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Location", "://bad%url")
		w.WriteHeader(http.StatusFound)
		if _, err := io.WriteString(w, "redirect-body"); err != nil {
			t.Error(err)
		}
	}))
	t.Cleanup(server.Close)
	response := request(t, newClient(t, options()), http.MethodGet, server.URL, nil)
	body, err := io.ReadAll(response)
	if response.StatusCode != http.StatusFound || response.Category != httpclient.HTTPResponse || err != nil || string(body) != "redirect-body" {
		t.Fatalf("malformed redirect = %v, read error %v", response, err)
	}
}

func TestCallerCancellationAndEarlierDeadline(t *testing.T) {
	client := newClient(t, options())
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:1", http.NoBody)
	if err != nil {
		t.Fatal(err)
	}
	response := client.Do(ctx, req)
	if response.Category != httpclient.CurlError || !errors.Is(response.Err, context.Canceled) {
		t.Fatalf("canceled request = %v, error %v", response, response.Err)
	}
	ctx, cancel = context.WithDeadline(t.Context(), time.Now().Add(-time.Second))
	defer cancel()
	response = client.Do(ctx, req)
	if response.Category != httpclient.RequestTimeout || !errors.Is(response.Err, context.DeadlineExceeded) {
		t.Fatalf("expired caller deadline = %v, error %v", response, response.Err)
	}
}

func TestRedirectRejectionsAndSameOrigin(t *testing.T) {
	ca := newCA(t)
	var hits atomic.Int32
	server := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		switch r.URL.Path {
		case "/loop":
			http.Redirect(w, r, "/loop", http.StatusFound)
		case "/downgrade":
			http.Redirect(w, r, "http://127.0.0.1:1/", http.StatusFound)
		case "/userinfo":
			http.Redirect(w, r, "https://user:secret@127.0.0.1:1/", http.StatusFound)
		case "/start":
			http.Redirect(w, r, "/end", http.StatusFound)
		default:
			if r.Header.Get("X-Api-Key") != "secret" || r.Header.Get("Referer") != "" {
				t.Error("same-origin header policy failed")
			}
			w.WriteHeader(http.StatusNoContent)
		}
	}))
	opts := options()
	opts.TLS.RootCAs = ca.pool()
	opts.MaxRedirects = 2
	opts.AdmitRedirect = func(*url.URL) bool { return true }
	client := newClient(t, opts)
	for _, path := range []string{"/loop", "/downgrade", "/userinfo"} {
		before := hits.Load()
		response := request(t, client, http.MethodGet, server.URL+path, nil)
		wantHits := int32(1)
		if path == "/loop" {
			wantHits = 3
		}
		if response.StatusCode != http.StatusFound || hits.Load()-before != wantHits {
			t.Fatalf("redirect %s = %v", path, response)
		}
	}
	req := makeRequest(t.Context(), t, http.MethodGet, server.URL+"/start", http.NoBody)
	req.Header.Set("X-Api-Key", "secret")
	req.Header.Set("Referer", "https://secret.example/path?token=secret")
	response := client.Do(t.Context(), req)
	closeResponse(t, response)
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("same-origin response = %v", response)
	}
	opts.AdmitRedirect = func(*url.URL) bool { return false }
	response = request(t, newClient(t, opts), http.MethodGet, server.URL+"/start", nil)
	if response.StatusCode != http.StatusFound {
		t.Fatalf("unadmitted redirect = %v", response)
	}
}

func TestMutationsUseFreshConnectionsAndNoRetry(t *testing.T) {
	var calls atomic.Int32
	var connections atomic.Int32
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		calls.Add(1)
		w.WriteHeader(http.StatusNoContent)
	}))
	server.Config.ConnState = func(_ net.Conn, state http.ConnState) {
		if state == http.StateNew {
			connections.Add(1)
		}
	}
	server.Start()
	t.Cleanup(server.Close)
	client := newClient(t, options())
	for range 3 {
		if got := request(t, client, http.MethodPost, server.URL, strings.NewReader("secret")); got.StatusCode != http.StatusNoContent {
			t.Fatalf("mutation = %v", got)
		}
	}
	if calls.Load() != 3 || connections.Load() != 3 {
		t.Fatalf("calls %d, connections %d, want 3 each", calls.Load(), connections.Load())
	}
}

func TestRedirectStatusesAndBodyRules(t *testing.T) {
	ca := newCA(t)
	server := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/end" {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		status, err := strconv.Atoi(r.URL.Query().Get("status"))
		if err != nil {
			t.Error(err)
			return
		}
		http.Redirect(w, r, "/end", status)
	}))
	opts := options()
	opts.TLS.RootCAs = ca.pool()
	opts.MaxRedirects = 1
	opts.AdmitRedirect = func(destination *url.URL) bool { destination.Host = "127.0.0.1:1"; return true }
	client := newClient(t, opts)
	for _, status := range []int{301, 302, 303, 307, 308} {
		for _, method := range []string{http.MethodGet, http.MethodHead} {
			response := request(t, client, method, server.URL+"/?status="+strconv.Itoa(status), http.NoBody)
			if response.StatusCode != http.StatusNoContent {
				t.Fatalf("%s HTTP %d redirect = %v", method, status, response)
			}
		}
	}
	response := request(t, client, http.MethodGet, server.URL+"/?status=307", strings.NewReader("secret"))
	if response.StatusCode != http.StatusTemporaryRedirect {
		t.Fatal("GET body was replayed")
	}
}

func checkSocketFailure(t *testing.T, reset bool) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		closeSocket(t, w, reset)
	}))
	t.Cleanup(server.Close)
	want := httpclient.EmptyReply
	if reset {
		want = httpclient.ConnectionReset
	}
	if got := request(t, newClient(t, options()), http.MethodGet, server.URL, nil); got.Category != want {
		t.Fatalf("response = %v, want %s", got, want)
	}
}

type streamFailureCase struct {
	name, body string
	length     int
	flush      bool
	want       error
}

func checkStreamFailure(t *testing.T, tc streamFailureCase) {
	t.Helper()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if tc.length != 0 {
			w.Header().Set("Content-Length", strconv.Itoa(tc.length))
		}
		w.WriteHeader(http.StatusForbidden)
		if tc.flush {
			if err := http.NewResponseController(w).Flush(); err != nil {
				t.Error(err)
			}
		}
		if _, err := io.WriteString(w, tc.body); err != nil {
			t.Error(err)
		}
	}))
	t.Cleanup(server.Close)
	opts := options()
	opts.MaxBodyBytes = 4
	response := request(t, newClient(t, opts), http.MethodGet, server.URL, nil)
	body, err := io.ReadAll(response)
	if !errors.Is(err, tc.want) || len(body) > 4 || response.Category != httpclient.HTTPResponse || response.StatusCode != http.StatusForbidden {
		t.Fatalf("response = %v, read %d bytes, error %v, want %v", response, len(body), err, tc.want)
	}
}

func closeSocket(t *testing.T, w http.ResponseWriter, reset bool) {
	t.Helper()
	conn, _, err := http.NewResponseController(w).Hijack()
	if err != nil {
		t.Error(err)
		return
	}
	if reset {
		tcp, ok := conn.(*net.TCPConn)
		if !ok {
			t.Error("hijacked connection is not TCP")
		}
		if ok {
			if err := tcp.SetLinger(0); err != nil {
				t.Error(err)
			}
		}
	}
	if err := conn.Close(); err != nil {
		t.Error(err)
	}
}
