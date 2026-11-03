package httpclient

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
)

// Category is the outcome vocabulary shared with the Python curl wrapper.
type Category string

const (
	// HTTPResponse means that a final HTTP status arrived.
	HTTPResponse Category = "http_response"
	// ConnectionRefused reports a typed connection failure, excluding DNS and timeouts.
	ConnectionRefused Category = "connection_refused"
	// Timeout reports a phase timeout before the operation deadline.
	Timeout Category = "timeout"
	// TLSHandshake reports failed negotiation, excluding certificate verification.
	TLSHandshake Category = "tls_handshake"
	// EmptyReply reports EOF before final HTTP headers.
	EmptyReply Category = "empty_reply"
	// ConnectionReset reports a receive failure before final HTTP headers.
	ConnectionReset Category = "connection_reset"
	// CurlError reports other native failures; its spelling preserves compatibility.
	CurlError Category = "curl_error"
	// RequestTimeout reports expiration of the encompassing operation budget.
	RequestTimeout Category = "request_timeout"
	// CurlUnavailable preserves the vocabulary only. Native HTTP starts no executable.
	CurlUnavailable Category = "curl_unavailable"
)

var (
	// ErrRequestTimeout also matches the context deadline error through error inspection.
	ErrRequestTimeout = fmt.Errorf("httpclient: request timeout: %w", context.DeadlineExceeded)
	// ErrResponseLimit reports a body that exceeds the caller's byte limit.
	ErrResponseLimit = errors.New("httpclient: response body exceeds limit")
	// ErrResponseRead reports an incomplete response without retaining its raw cause.
	ErrResponseRead = errors.New("httpclient: response body incomplete")
	errTransport    = errors.New("httpclient: transport failed")
)

func classify(ctx context.Context, err error, handshake bool) (Category, error) {
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return RequestTimeout, ErrRequestTimeout
	}
	if errors.Is(ctx.Err(), context.Canceled) || errors.Is(err, context.Canceled) {
		return CurlError, context.Canceled
	}
	return transportCategory(err, handshake), errTransport
}

func transportCategory(err error, handshake bool) Category {
	var network net.Error
	if errors.As(err, &network) && network.Timeout() {
		return Timeout
	}
	var certificate *tls.CertificateVerificationError
	var unknown x509.UnknownAuthorityError
	var invalid x509.CertificateInvalidError
	var hostname x509.HostnameError
	var dns *net.DNSError
	if errors.As(err, &certificate) || errors.As(err, &unknown) || errors.As(err, &invalid) || errors.As(err, &hostname) || errors.As(err, &dns) {
		return CurlError
	}
	if handshake {
		return TLSHandshake
	}
	if operation, ok := errors.AsType[*net.OpError](err); ok {
		if operation.Op == "dial" || operation.Op == "proxyconnect" {
			return ConnectionRefused
		}
		return ConnectionReset
	}
	if errors.Is(err, io.EOF) {
		return EmptyReply
	}
	if errors.Is(err, io.ErrUnexpectedEOF) {
		return ConnectionReset
	}
	return CurlError
}
