package httpclient_test

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/OpenRAE/lilrae/internal/httpclient"
)

func TestInvalidOptions(t *testing.T) {
	for _, change := range []func(*httpclient.Options){
		func(o *httpclient.Options) { o.TLS = nil },
		func(o *httpclient.Options) { o.Timeout = 0 },
		func(o *httpclient.Options) { o.Timeout = -1 },
		func(o *httpclient.Options) { o.PhaseTimeout = 0 },
		func(o *httpclient.Options) { o.MaxHeaderBytes = 0 },
		func(o *httpclient.Options) { o.MaxBodyBytes = 0 },
		func(o *httpclient.Options) { o.MaxRedirects = -1 },
		func(o *httpclient.Options) { o.MaxRedirects = 1 },
	} {
		opts := options()
		change(&opts)
		if client, err := httpclient.New(opts); err == nil || client != nil {
			t.Fatal("invalid options constructed a client")
		}
	}
}

func TestRequestAdmissionBeforeNetwork(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { calls.Add(1); w.WriteHeader(http.StatusNoContent) }))
	t.Cleanup(server.Close)
	client := newClient(t, options())
	for _, endpoint := range []string{strings.Replace(server.URL, "://", "://user:synthetic-secret@", 1), "ftp://example.test/"} {
		response := request(t, client, http.MethodGet, endpoint, nil)
		if response.Category != httpclient.CurlError || response.Err == nil {
			t.Fatalf("invalid request = %v", response)
		}
		if strings.Contains(fmt.Sprint(response.Err), "synthetic-secret") {
			t.Fatal("invalid URL leaked")
		}
	}
	for _, req := range []*http.Request{nil, {}} {
		if got := client.Do(t.Context(), req); got.Category != httpclient.CurlError || got.Err == nil {
			t.Fatal("nil request admitted")
		}
	}
	req, err := http.NewRequestWithContext(t.Context(), http.MethodGet, server.URL, http.NoBody)
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("X-Secret", "synthetic-secret\r\nInjected: header")
	if got := client.Do(t.Context(), req); got.Category != httpclient.CurlError || got.Err == nil {
		t.Fatal("invalid header admitted")
	}
	if calls.Load() != 0 {
		t.Fatal("invalid request reached the network")
	}
}

func TestResponseDiagnosticsExcludeSecrets(t *testing.T) {
	const secret = "synthetic-secret"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Set-Cookie", secret)
		if _, err := io.WriteString(w, secret); err != nil {
			t.Error(err)
		}
	}))
	t.Cleanup(server.Close)
	response := request(t, newClient(t, options()), http.MethodGet, server.URL+"/?token="+secret, nil)
	var out bytes.Buffer
	fmt.Fprintf(&out, "%v %+v %#v %s %q", response, response, response, response, response)
	fmt.Fprintf(&out, "%v %+v %#v", *response, *response, *response)
	slog.New(slog.NewJSONHandler(&out, nil)).InfoContext(t.Context(), "response", "result", response)
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatal(err)
	}
	out.Write(encoded)
	if strings.Contains(out.String(), secret) {
		t.Fatal("response diagnostics exposed a secret")
	}
	headers := response.Header()
	headers.Set("Set-Cookie", "changed")
	endpoint := response.URL()
	endpoint.RawQuery = "changed"
	if response.Header().Get("Set-Cookie") != secret || !strings.Contains(response.URL().RawQuery, secret) {
		t.Fatal("accessor mutation changed response identity")
	}
	body, err := io.ReadAll(response)
	if err != nil || string(body) != secret {
		t.Fatal("payload was not explicitly available to the consumer")
	}
}

func TestRawCompressionAndByteLimit(t *testing.T) {
	var compressed bytes.Buffer
	writer := gzip.NewWriter(&compressed)
	if _, err := io.WriteString(writer, strings.Repeat("x", 4096)); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Accept-Encoding") != "" {
			t.Error("client requested implicit decoding")
		}
		w.Header().Set("Content-Encoding", "gzip")
		if _, err := w.Write(compressed.Bytes()); err != nil {
			t.Error(err)
		}
	}))
	t.Cleanup(server.Close)
	opts := options()
	opts.MaxBodyBytes = int64(compressed.Len())
	response := request(t, newClient(t, opts), http.MethodGet, server.URL, nil)
	body, err := io.ReadAll(response)
	if err != nil || !bytes.Equal(body, compressed.Bytes()) || response.Header().Get("Content-Encoding") != "gzip" {
		t.Fatalf("raw compressed response failed: %v", err)
	}
}

func TestCloseAndCancellationStopStreaming(t *testing.T) {
	for _, cancelOperation := range []bool{false, true} {
		t.Run(fmt.Sprint("cancel=", cancelOperation), func(t *testing.T) {
			checkStreamCancellation(t, cancelOperation)
		})
	}
}

func checkStreamCancellation(t *testing.T, cancelOperation bool) {
	t.Helper()

	closed := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		if err := http.NewResponseController(w).Flush(); err != nil {
			t.Error(err)
		}
		<-r.Context().Done()
		close(closed)
	}))
	t.Cleanup(server.Close)
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, server.URL, http.NoBody)
	if err != nil {
		t.Fatal(err)
	}
	response := newClient(t, options()).Do(ctx, req)
	if cancelOperation {
		cancel()
		if _, err := io.ReadAll(response); !errors.Is(err, context.Canceled) {
			t.Fatalf("canceled body read = %v", err)
		}
	}
	if err := response.Close(); err != nil {
		t.Fatal(err)
	}
	select {
	case <-closed:
	case <-t.Context().Done():
		t.Fatal("stream did not close")
	}
}
