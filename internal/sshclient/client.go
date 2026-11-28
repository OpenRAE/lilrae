// Package sshclient establishes SSH connections to admitted lab endpoints.
package sshclient

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"slices"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/sshkeys"
)

var (
	// ErrPinFile reports that the project trust file could not be read.
	ErrPinFile = errors.New("load host key pins")
	// ErrUnknownHost reports that the exact endpoint has no pin.
	ErrUnknownHost = errors.New("find host key pin")
	// ErrChangedHostKey reports that the server key differs from its pin.
	ErrChangedHostKey = errors.New("verify host key: key changed")
)

// Dial establishes a session connection with the project's exact endpoint
// pin. Authentication starts only after the key matches.
func Dial(ctx context.Context, project string, endpoint sshkeys.Endpoint, signer ssh.Signer) (*ssh.Client, error) {
	address, err := endpoint.Address()
	if err != nil {
		return nil, err
	}
	pins, err := sshkeys.ReadPins(ctx, project)
	if err != nil {
		if ctx.Err() != nil {
			return nil, failed(address, ctx.Err())
		}
		return nil, failed(address, ErrPinFile)
	}
	want := pins.Key(endpoint)
	if want == nil {
		return nil, failed(address, ErrUnknownHost)
	}
	key, err := ssh.ParsePublicKey(want)
	if err != nil {
		return nil, failed(address, ErrPinFile)
	}
	algorithms := hostAlgorithms(key.Type())
	if len(algorithms) == 0 {
		return nil, failed(address, errors.New("negotiate pinned host key algorithm"))
	}
	verify := func(_ string, _ net.Addr, presented ssh.PublicKey) error {
		if !bytes.Equal(want, presented.Marshal()) {
			return ErrChangedHostKey
		}
		return nil
	}
	return connect(ctx, address, endpoint.User, signer, verify, algorithms)
}

func hostAlgorithms(keyType string) []string {
	switch keyType {
	case ssh.KeyAlgoRSA:
		return []string{ssh.KeyAlgoRSASHA512, ssh.KeyAlgoRSASHA256}
	case ssh.CertAlgoRSAv01:
		return []string{ssh.CertAlgoRSASHA512v01, ssh.CertAlgoRSASHA256v01}
	default:
		if slices.Contains(ssh.SupportedAlgorithms().HostKeys, keyType) {
			return []string{keyType}
		}
		return nil
	}
}

// Probe captures a host key during startup. Only an authenticated probe
// returns a key to the startup pin writer.
func Probe(ctx context.Context, endpoint sshkeys.Endpoint, signer ssh.Signer) ([]byte, error) {
	address, err := endpoint.Address()
	if err != nil {
		return nil, err
	}
	var first []byte
	observe := func(_ string, _ net.Addr, key ssh.PublicKey) error {
		if first == nil {
			first = key.Marshal()
			return nil
		}
		if !bytes.Equal(first, key.Marshal()) {
			return ErrChangedHostKey
		}
		return nil
	}
	conn, err := handshake(ctx, address, endpoint.User, signer, observe, nil)
	if err != nil {
		return nil, err
	}
	if closeErr := closeTransport(conn.conn); closeErr != nil {
		return nil, failed(address, closeErr)
	}
	return first, nil
}

type connection struct {
	conn     ssh.Conn
	channels <-chan ssh.NewChannel
	requests <-chan *ssh.Request
}

func connect(ctx context.Context, addr, user string, signer ssh.Signer, verify ssh.HostKeyCallback, algorithms []string) (*ssh.Client, error) {
	result, err := handshake(ctx, addr, user, signer, verify, algorithms)
	if err != nil {
		return nil, err
	}
	return ssh.NewClient(result.conn, result.channels, result.requests), nil
}

func handshake(ctx context.Context, addr, user string, signer ssh.Signer, verify ssh.HostKeyCallback, algorithms []string) (connection, error) {
	if signer == nil {
		return connection{}, failed(addr, errors.New("load client authentication key"))
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	dialer := net.Dialer{}
	socket, err := dialer.DialContext(ctx, "tcp", addr)
	if err != nil {
		return connection{}, failed(addr, checkFailure(ctx, errors.New("connect TCP")))
	}
	result, err := authenticate(ctx, socket, addr, &ssh.ClientConfig{
		User: user, Auth: []ssh.AuthMethod{ssh.PublicKeys(signer)}, HostKeyCallback: verify,
		HostKeyAlgorithms: algorithms,
	})
	if err != nil {
		return connection{}, failed(addr, errors.Join(err, closeTransport(socket)))
	}
	return result, nil
}

func authenticate(ctx context.Context, socket net.Conn, addr string, config *ssh.ClientConfig) (connection, error) {
	deadline, _ := ctx.Deadline()
	if err := socket.SetDeadline(deadline); err != nil {
		return connection{}, errors.New("set SSH handshake deadline")
	}
	closed := make(chan error, 1)
	stop := context.AfterFunc(ctx, func() { closed <- closeTransport(socket) })
	conn, channels, requests, err := ssh.NewClientConn(socket, addr, config)
	if !stop() {
		return connection{}, errors.Join(checkFailure(ctx, errors.New("cancel SSH handshake")), <-closed)
	}
	if ctx.Err() != nil {
		return connection{}, checkFailure(ctx, errors.New("cancel SSH handshake"))
	}
	if err != nil {
		if errors.Is(err, ErrChangedHostKey) {
			return connection{}, ErrChangedHostKey
		}
		return connection{}, checkFailure(ctx, errors.New("authenticate SSH connection"))
	}
	if err := socket.SetDeadline(time.Time{}); err != nil {
		return connection{}, errors.New("clear SSH handshake deadline")
	}
	return connection{conn, channels, requests}, nil
}

func checkFailure(ctx context.Context, check error) error {
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("SSH connection interrupted: %w", err)
	}
	return check
}

func closeTransport(conn interface{ Close() error }) error {
	if err := conn.Close(); err != nil && !errors.Is(err, net.ErrClosed) {
		return errors.New("close SSH transport")
	}
	return nil
}

func failed(addr string, check error) error {
	return fmt.Errorf("SSH %s: %w", addr, check)
}
