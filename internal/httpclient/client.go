// Package httpclient sends bounded HTTP requests with caller-supplied trust.
// Consumers own authentication, destination authority, retries, and decoding.
package httpclient

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"strings"
	"sync/atomic"
	"time"
)

// Options selects one client's trust, limits, and network policy.
type Options struct {
	// TLS is required. Nil RootCAs explicitly selects system trust.
	TLS            *tls.Config
	Timeout        time.Duration
	PhaseTimeout   time.Duration
	MaxHeaderBytes int64
	MaxBodyBytes   int64
	// Proxy is nil for direct requests. Environment proxies require an explicit callback.
	Proxy func(*http.Request) (*url.URL, error)
	// MaxRedirects is zero to return redirects. Positive values require AdmitRedirect.
	MaxRedirects  int
	AdmitRedirect func(*url.URL) bool
}

var (
	errOptions = errors.New("httpclient: invalid options")
	errRequest = errors.New("httpclient: invalid request")
)

// Client sends requests under one immutable transport policy.
// Construct it with New. Each response must be closed by its consumer.
type Client struct {
	transport     http.RoundTripper
	maxRedirects  int
	admitRedirect func(*url.URL) bool
	timeout       time.Duration
	maxBody       int64
}

// New constructs a client without reading configuration or making a request.
// Timeout, PhaseTimeout, MaxHeaderBytes, and MaxBodyBytes must be positive.
func New(opts Options) (*Client, error) {
	if opts.TLS == nil || opts.Timeout <= 0 || opts.PhaseTimeout <= 0 || opts.MaxHeaderBytes <= 0 || opts.MaxBodyBytes <= 0 || opts.MaxRedirects < 0 || (opts.MaxRedirects > 0 && opts.AdmitRedirect == nil) {
		return nil, errOptions
	}
	tlsConfig := opts.TLS.Clone()
	if tlsConfig.RootCAs != nil {
		tlsConfig.RootCAs = tlsConfig.RootCAs.Clone()
	}
	protocols := new(http.Protocols)
	protocols.SetHTTP1(true)
	transport := &http.Transport{
		Proxy:                  opts.Proxy,
		DialContext:            (&net.Dialer{Timeout: opts.PhaseTimeout}).DialContext,
		TLSClientConfig:        tlsConfig,
		TLSHandshakeTimeout:    opts.PhaseTimeout,
		ResponseHeaderTimeout:  opts.PhaseTimeout,
		MaxResponseHeaderBytes: opts.MaxHeaderBytes,
		DisableCompression:     true,
		// A fresh HTTP/1 connection prevents the transport's stale-connection replay.
		DisableKeepAlives: true,
		Protocols:         protocols,
	}
	return &Client{
		transport: transport, maxRedirects: opts.MaxRedirects, admitRedirect: opts.AdmitRedirect,
		timeout: opts.Timeout, maxBody: opts.MaxBodyBytes,
	}, nil
}

// Do sends an admitted request. ctx bounds the whole operation, including reads.
// Any final HTTP status is HTTPResponse, independent of body completion.
// It retains no raw transport error or diagnostic URL.
func (c *Client) Do(ctx context.Context, req *http.Request) *Response {
	if req == nil || req.URL == nil || req.URL.User != nil {
		return &Response{Category: CurlError, Err: errRequest}
	}
	ctx, cancel := context.WithTimeout(ctx, c.timeout)
	var handshake atomic.Bool
	trace := &httptrace.ClientTrace{TLSHandshakeDone: func(_ tls.ConnectionState, err error) {
		handshake.Store(err != nil)
	}}
	original := req.Clone(httptrace.WithClientTrace(ctx, trace))
	request := original
	for followed := 0; ; followed++ {
		handshake.Store(false)
		response, err := c.transport.RoundTrip(request)
		if err != nil {
			category, safeErr := classify(ctx, err, handshake.Load())
			cancel()
			return &Response{Category: category, Err: safeErr}
		}
		result := &Response{
			Category: HTTPResponse, StatusCode: response.StatusCode,
			header: response.Header.Clone(), url: request.URL,
			body: response.Body, remaining: c.maxBody, contextError: ctx.Err, cancel: cancel,
		}
		next := c.nextRequest(original, response, followed)
		if next == nil {
			return result
		}
		// Close the intermediate body without cancelling the shared hop budget.
		if err := response.Body.Close(); err != nil {
			cancel()
			return &Response{Category: HTTPResponse, StatusCode: response.StatusCode, Err: ErrResponseRead}
		}
		request = next
	}
}

func (c *Client) nextRequest(original *http.Request, response *http.Response, followed int) *http.Request {
	if followed >= c.maxRedirects || !redirectStatus(response.StatusCode) || original.URL.Scheme != "https" || differentAuthority(original) || (original.Body != nil && original.Body != http.NoBody) || (original.Method != http.MethodGet && original.Method != http.MethodHead) {
		return nil
	}
	destination, err := response.Location()
	if err != nil || destination.User != nil || destination.Scheme != "https" {
		return nil
	}
	// Give the admission callback a copy so it cannot rewrite the destination.
	admitted := *destination
	if !c.admitRedirect(&admitted) {
		return nil
	}
	req := original.Clone(original.Context())
	req.URL = destination
	if !sameOrigin(original.URL, destination) {
		req.Header = make(http.Header)
	}
	req.Header.Del("Referer")
	req.Host = ""
	return req
}

func differentAuthority(req *http.Request) bool {
	return req.Host != "" && !strings.EqualFold(req.Host, req.URL.Host)
}

func redirectStatus(status int) bool {
	return status == 301 || status == 302 || status == 303 || status == 307 || status == 308
}

func sameOrigin(a, b *url.URL) bool {
	return a.Scheme == b.Scheme && strings.EqualFold(a.Hostname(), b.Hostname()) && effectivePort(a) == effectivePort(b)
}

func effectivePort(u *url.URL) string {
	if port := u.Port(); port != "" {
		return port
	}
	if u.Scheme == "https" {
		return "443"
	}
	return "80"
}
