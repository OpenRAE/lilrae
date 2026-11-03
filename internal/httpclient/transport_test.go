package httpclient_test

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"errors"
	"io"
	"log/slog"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/OpenRAE/lilrae/internal/httpclient"
)

type testCA struct {
	cert *x509.Certificate
	key  *ecdsa.PrivateKey
}

func newCA(t *testing.T) testCA {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "test CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour),
		IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return testCA{cert, key}
}

func (ca testCA) pool() *x509.CertPool {
	pool := x509.NewCertPool()
	pool.AddCert(ca.cert)
	return pool
}

func (ca testCA) server(t *testing.T, wrongHost, expired bool, handler http.Handler) *httptest.Server {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	cert := &x509.Certificate{
		SerialNumber: big.NewInt(2), NotBefore: time.Now().Add(-time.Hour),
		NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		IPAddresses: []net.IP{net.ParseIP("127.0.0.1")},
	}
	if wrongHost {
		cert.IPAddresses = nil
		cert.DNSNames = []string{"other.example.test"}
	}
	if expired {
		cert.NotAfter = time.Now().Add(-time.Minute)
	}
	der, err := x509.CreateCertificate(rand.Reader, cert, ca.cert, &key.PublicKey, ca.key)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewUnstartedServer(handler)
	server.Config.ErrorLog = slog.NewLogLogger(slog.DiscardHandler, slog.LevelError)
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS12, Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: key}}}
	server.StartTLS()
	t.Cleanup(server.Close)
	return server
}

func request(t *testing.T, client *httpclient.Client, method, endpoint string, body io.Reader) *httpclient.Response {
	t.Helper()
	req, err := http.NewRequestWithContext(t.Context(), method, endpoint, body)
	if err != nil {
		t.Fatal(err)
	}
	response := client.Do(t.Context(), req)
	t.Cleanup(func() {
		if err := response.Close(); err != nil {
			t.Error(err)
		}
	})
	return response
}

func newClient(t *testing.T, opts httpclient.Options) *httpclient.Client {
	t.Helper()
	client, err := httpclient.New(opts)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func TestCallerTrust(t *testing.T) {
	ca := newCA(t)
	for _, tc := range []struct {
		name               string
		roots              *x509.CertPool
		wrongHost, expired bool
		want               httpclient.Category
	}{
		{"trusted", ca.pool(), false, false, httpclient.HTTPResponse},
		{"empty", x509.NewCertPool(), false, false, httpclient.CurlError},
		{"unrelated", newCA(t).pool(), false, false, httpclient.CurlError},
		{"system", nil, false, false, httpclient.CurlError},
		{"hostname", ca.pool(), true, false, httpclient.CurlError},
		{"expired", ca.pool(), false, true, httpclient.CurlError},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := ca.server(t, tc.wrongHost, tc.expired, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) }))
			opts := options()
			opts.TLS.RootCAs = tc.roots
			response := request(t, newClient(t, opts), http.MethodGet, server.URL, nil)
			if response.Category != tc.want {
				t.Fatalf("category = %s, want %s", response.Category, tc.want)
			}
		})
	}
}

func TestTrustCopiesAndInsecureIsolation(t *testing.T) {
	ca := newCA(t)
	server := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) }))
	opts := options()
	opts.TLS.RootCAs = x509.NewCertPool()
	verified := newClient(t, opts)
	opts.TLS.RootCAs.AddCert(ca.cert)
	opts.TLS.InsecureSkipVerify = true
	insecure := newClient(t, opts)
	if got := request(t, insecure, http.MethodGet, server.URL, nil); got.Category != httpclient.HTTPResponse {
		t.Fatalf("explicit insecure request = %v", got)
	}
	if got := request(t, verified, http.MethodGet, server.URL, nil); got.Category != httpclient.CurlError {
		t.Fatalf("caller mutation changed verified trust: %v", got)
	}
}

func TestOperationAndPhaseTimeouts(t *testing.T) {
	for _, tc := range []struct {
		name          string
		body, overall bool
	}{
		{"headers-phase", false, false}, {"headers-operation", false, true}, {"body-operation", true, true},
	} {
		t.Run(tc.name, func(t *testing.T) { checkTimeout(t, tc.body, tc.overall) })
	}
}

func checkTimeout(t *testing.T, body, overall bool) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if body {
			w.WriteHeader(http.StatusOK)
			flush(t, w)
		}
		<-r.Context().Done()
	}))
	t.Cleanup(server.Close)
	opts := options()
	want := httpclient.Timeout
	opts.PhaseTimeout = 100 * time.Millisecond
	if overall {
		opts.Timeout = 100 * time.Millisecond
		opts.PhaseTimeout = time.Minute
		want = httpclient.RequestTimeout
	}
	response := request(t, newClient(t, opts), http.MethodGet, server.URL, http.NoBody)
	if !body {
		if response.Category != want {
			t.Fatalf("category = %s, want %s", response.Category, want)
		}
		return
	}
	if _, err := io.ReadAll(response); !errors.Is(err, httpclient.ErrRequestTimeout) || response.Category != httpclient.HTTPResponse || response.StatusCode != http.StatusOK {
		t.Fatalf("body result = %v, error %v", response, err)
	}
}

func flush(t *testing.T, w http.ResponseWriter) {
	t.Helper()
	if err := http.NewResponseController(w).Flush(); err != nil {
		t.Error(err)
	}
}

func TestRedirectCredentialBoundary(t *testing.T) {
	ca := newCA(t)
	var received atomic.Int32
	destination := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		received.Add(1)
		assertNoCredentials(t, r)
		if r.Host == "overridden.example.test" {
			t.Error("redirect retained custom Host")
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	source := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, destination.URL, http.StatusTemporaryRedirect)
	}))
	opts := options()
	opts.TLS.RootCAs = ca.pool()
	client := newClient(t, opts)
	if got := request(t, client, http.MethodGet, source.URL, nil); got.StatusCode != http.StatusTemporaryRedirect || received.Load() != 0 {
		t.Fatalf("default redirect = %v, destination calls %d", got, received.Load())
	}
	opts.MaxRedirects = 5
	opts.AdmitRedirect = func(*url.URL) bool { return true }
	client = newClient(t, opts)
	req := makeRequest(t.Context(), t, http.MethodGet, source.URL, http.NoBody)
	req.Host = req.URL.Host
	for _, name := range []string{"Authorization", "Cookie", "X-Api-Key", "Proxy-Authorization", "Referer"} {
		req.Header.Set(name, "synthetic-secret")
	}
	response := client.Do(t.Context(), req)
	closeResponse(t, response)
	if response.StatusCode != http.StatusNoContent || received.Load() != 1 || response.URL().String() != destination.URL {
		t.Fatalf("admitted redirect = %v, destination calls %d", response, received.Load())
	}
	if req.Header.Get("X-Api-Key") != "synthetic-secret" || req.Host != req.URL.Host {
		t.Error("client changed the caller request")
	}
	response = request(t, client, http.MethodPost, source.URL, strings.NewReader("secret-body"))
	if response.StatusCode != http.StatusTemporaryRedirect || received.Load() != 1 {
		t.Fatal("a mutating request was redirected")
	}
}

func TestSessionCacheCannotCrossTrustSettings(t *testing.T) {
	ca := newCA(t)
	var resumed atomic.Int32
	server := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.TLS.DidResume {
			resumed.Add(1)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	opts := options()
	opts.TLS.RootCAs = ca.pool()
	// TLS 1.2 delivers its ticket in the handshake, so cache population is deterministic.
	opts.TLS.MaxVersion = tls.VersionTLS12
	opts.TLS.ClientSessionCache = tls.NewLRUClientSessionCache(8)
	trusted := newClient(t, opts)
	for range 2 {
		if got := request(t, trusted, http.MethodGet, server.URL, http.NoBody); got.StatusCode != http.StatusNoContent {
			t.Fatalf("trusted response = %v", got)
		}
	}
	opts.TLS.RootCAs = x509.NewCertPool()
	if got := request(t, newClient(t, opts), http.MethodGet, server.URL, http.NoBody); got.Category != httpclient.CurlError {
		t.Fatalf("shared cache bypassed caller roots: %v", got)
	}
	if resumed.Load() != 1 {
		t.Fatalf("resumed %d sessions, want only the second trusted request", resumed.Load())
	}
}

func TestRedirectDoesNotChangeVirtualHostAuthority(t *testing.T) {
	ca := newCA(t)
	var forwarded atomic.Int32
	server := ca.server(t, false, false, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/start" {
			http.Redirect(w, r, "/end", http.StatusFound)
			return
		}
		forwarded.Add(1)
		w.WriteHeader(http.StatusNoContent)
	}))
	opts := options()
	opts.TLS.RootCAs = ca.pool()
	opts.MaxRedirects = 1
	opts.AdmitRedirect = func(*url.URL) bool { return true }
	req := makeRequest(t.Context(), t, http.MethodGet, server.URL+"/start", http.NoBody)
	req.Host = "tenant.example.test"
	req.Header.Set("Authorization", "synthetic-secret")
	response := newClient(t, opts).Do(t.Context(), req)
	closeResponse(t, response)
	if response.StatusCode != http.StatusFound || forwarded.Load() != 0 {
		t.Fatalf("virtual-host redirect = %v, forwarded %d", response, forwarded.Load())
	}
}

func TestDirectAndExplicitProxy(t *testing.T) {
	var proxyCalls atomic.Int32
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		proxyCalls.Add(1)
		w.WriteHeader(http.StatusNonAuthoritativeInfo)
	}))
	t.Cleanup(proxy.Close)
	t.Setenv("HTTP_PROXY", proxy.URL)
	t.Setenv("http_proxy", proxy.URL)
	opts := options()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) }))
	t.Cleanup(server.Close)
	if got := request(t, newClient(t, opts), http.MethodGet, server.URL, nil); got.StatusCode != http.StatusNoContent || proxyCalls.Load() != 0 {
		t.Fatal("direct mode consulted the environment proxy")
	}
	proxyURL, err := url.Parse(proxy.URL)
	if err != nil {
		t.Fatal(err)
	}
	opts.Proxy = http.ProxyURL(proxyURL)
	if got := request(t, newClient(t, opts), http.MethodGet, server.URL, nil); got.StatusCode != http.StatusNonAuthoritativeInfo || proxyCalls.Load() != 1 {
		t.Fatal("explicit proxy was not used")
	}
}

func assertNoCredentials(t *testing.T, r *http.Request) {
	t.Helper()
	for _, name := range []string{"Authorization", "Cookie", "X-Api-Key", "Proxy-Authorization", "Referer"} {
		if r.Header.Get(name) != "" {
			t.Errorf("cross-origin redirect sent %s", name)
		}
	}
}
