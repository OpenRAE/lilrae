package sshkeys

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net"
	"net/netip"
	"strconv"
	"strings"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/projectstate"
	"github.com/OpenRAE/lilrae/internal/securefile"
)

const (
	pinFile    = "known_hosts"
	maxPinFile = 1 << 20
)

// Endpoint is the SSH projection of an endpoint admitted by the caller.
type Endpoint struct {
	Name string
	Host string
	Port int
	User string
}

// Address returns the exact network address used for the SSH connection.
func (e Endpoint) Address() (string, error) {
	if e.pinName() == "" || strings.TrimSpace(e.User) == "" || strings.ContainsAny(e.User, "\x00\r\n") {
		return "", errors.New("invalid SSH endpoint")
	}
	return net.JoinHostPort(e.Host, strconv.Itoa(e.Port)), nil
}

func (e Endpoint) pinName() string {
	if e.Port < 1 || e.Port > 65535 || !validHost(e.Host) {
		return ""
	}
	if e.Port == 22 {
		return e.Host
	}
	return "[" + e.Host + "]:" + strconv.Itoa(e.Port)
}

func validHost(host string) bool {
	if host == "" || len(host) > 253 {
		return false
	}
	base, zone, hasZone := strings.Cut(host, "%")
	if hasZone && !literalName(zone) {
		return false
	}
	if strings.Contains(base, ":") {
		addr, err := netip.ParseAddr(host)
		return err == nil && addr.Is6()
	}
	return !hasZone && literalName(base)
}

func literalName(name string) bool {
	const allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
	return name != "" && strings.Trim(name, allowed) == ""
}

// Pins is one read-only snapshot of the startup pins.
type Pins struct {
	keys map[string][]byte
}

// Key returns the wire encoding of the pin for the exact host and port.
// It returns nil when that pin is absent.
func (p Pins) Key(e Endpoint) []byte {
	return bytes.Clone(p.keys[e.pinName()])
}

// ReadPins reads the generated project pin file through the retained root.
func ReadPins(ctx context.Context, root string) (pins Pins, err error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return Pins{}, fmt.Errorf("load SSH host pins: %w", ctxErr)
	}
	project, err := projectstate.OpenProjectRoot(root)
	if err != nil {
		return Pins{}, errors.New("open SSH pin root")
	}
	defer func() { err = errors.Join(err, closeDir(project)) }()
	state, err := openPinDir(project, false)
	if err != nil {
		return Pins{}, err
	}
	defer func() { err = errors.Join(err, closeDir(state)) }()
	file, err := state.OpenOwned(pinFile, false)
	if err != nil {
		return Pins{}, errors.New("open trusted SSH pin file")
	}
	data, err := readBounded(file, maxPinFile)
	if err != nil {
		return Pins{}, errors.New("read SSH pin file")
	}
	return parsePins(data)
}

func parsePins(data []byte) (Pins, error) {
	pins := Pins{keys: make(map[string][]byte)}
	for line := range bytes.SplitSeq(data, []byte("\n")) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		token, key, err := parsePin(line)
		if err != nil {
			return Pins{}, err
		}
		if old := pins.keys[token]; old != nil && !bytes.Equal(old, key) {
			return Pins{}, errors.New("conflicting SSH host pins")
		}
		pins.keys[token] = key
	}
	return pins, nil
}

func parsePin(line []byte) (host string, wire []byte, err error) {
	fields := bytes.Fields(line)
	if len(fields) != 3 || !validPinName(string(fields[0])) || bytes.ContainsAny(line, "\x00\r") {
		return "", nil, errors.New("invalid SSH pin entry")
	}
	_, hosts, key, comment, rest, err := ssh.ParseKnownHosts(line)
	if err != nil || len(hosts) != 1 || comment != "" || len(rest) != 0 {
		return "", nil, errors.New("invalid SSH pin key")
	}
	return hosts[0], key.Marshal(), nil
}

func validPinName(token string) bool {
	if !strings.HasPrefix(token, "[") {
		return validHost(token)
	}
	host, port, err := net.SplitHostPort(token)
	if err != nil {
		return false
	}
	n, err := strconv.Atoi(port)
	return err == nil && (Endpoint{Host: host, Port: n}).pinName() == token
}

// HostPin is one server key collected by the startup owner.
type HostPin struct {
	Endpoint Endpoint
	Wire     []byte
}

// PublishPins writes one completed snapshot, including an empty snapshot.
func PublishPins(ctx context.Context, root string, pins []HostPin) error {
	var content bytes.Buffer
	for _, pin := range pins {
		host := pin.Endpoint.pinName()
		key, err := ssh.ParsePublicKey(pin.Wire)
		if host == "" || err != nil {
			return errors.New("invalid captured SSH pin")
		}
		content.WriteString(host)
		content.WriteByte(' ')
		content.Write(ssh.MarshalAuthorizedKey(key))
		if content.Len() > maxPinFile {
			return errors.New("SSH pin file exceeds size limit")
		}
	}
	if _, err := parsePins(content.Bytes()); err != nil {
		return err
	}
	return publishPins(ctx, root, content.Bytes())
}

// ErrPinDurability means replacement occurred but its durability could
// not be confirmed.
var ErrPinDurability = errors.New("SSH pin file replaced with uncertain durability")

func publishPins(ctx context.Context, root string, data []byte) (err error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return fmt.Errorf("publish SSH host pins: %w", ctxErr)
	}
	project, err := projectstate.OpenProjectRoot(root)
	if err != nil {
		return errors.New("open SSH pin root")
	}
	defer func() { err = errors.Join(err, closeDir(project)) }()
	state, err := openPinDir(project, true)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeDir(state)) }()
	if err := state.Replace(pinFile, data, publicMode); err != nil {
		if securefile.IsReason(err, securefile.ReasonDurability) {
			return ErrPinDurability
		}
		return errors.New("publish SSH pin file")
	}
	return nil
}

func openPinDir(project *securefile.Dir, create bool) (*securefile.Dir, error) {
	open := project.Subdir
	if create {
		open = project.PrivateSubdir
	}
	return openOwnedSubdir(project, projectstate.StateDir, open)
}
