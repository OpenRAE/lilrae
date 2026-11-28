// Package sshkeys owns the OpenSSH client key files, public authorization
// projections, and project host key pins.
package sshkeys

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/filelock"
	"github.com/OpenRAE/lilrae/internal/projectstate"
	"github.com/OpenRAE/lilrae/internal/securefile"
)

const (
	controlKey = "aptl_lab_key"
	kaliKey    = "kali_pivot_key"
	victimKey  = "workstation_pivot_key"
	keysDir    = "keys"
	publicMode = 0o644
)

var errPublicKey = errors.New("invalid SSH public key")

// Pair holds the signer and public projection of one client identity.
type Pair struct {
	Signer    ssh.Signer
	Public    []byte
	Generated bool
}

// String keeps private key material out of formatted diagnostics.
func (p Pair) String() string { return "SSH client key pair" }

// GoString keeps private key material out of Go-syntax diagnostics.
func (p Pair) GoString() string { return p.String() }

// EnsureControlPlane provisions the host client key and copies its public
// half into the project's control-plane authorization files.
func EnsureControlPlane(ctx context.Context, projectRoot, sshHome string) (pair Pair, err error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return Pair{}, fmt.Errorf("prepare control-plane SSH key: %w", ctxErr)
	}
	project, err := projectstate.OpenProjectRoot(projectRoot)
	if err != nil {
		return Pair{}, errors.New("open SSH project root")
	}
	defer func() { err = errors.Join(err, closeDir(project)) }()
	home, err := securefile.OpenDir(filepath.Dir(sshHome))
	if err != nil {
		return Pair{}, errors.New("open host SSH parent")
	}
	defer func() { err = errors.Join(err, closeDir(home)) }()
	dir, err := openOwnedSubdir(home, filepath.Base(sshHome), home.MakeSubdir)
	if err != nil {
		return Pair{}, errors.New("open host SSH directory")
	}
	defer func() { err = errors.Join(err, closeDir(dir)) }()
	pair, err = EnsurePair(ctx, dir, controlKey, "aptl-local-lab")
	if err != nil {
		return Pair{}, err
	}
	keys, err := openOwnedSubdir(project, keysDir, project.MakeSubdir)
	if err != nil {
		return Pair{}, err
	}
	defer func() { err = errors.Join(err, closeDir(keys)) }()
	if err := writePublic(keys, controlKey+".pub", pair.Public); err != nil {
		return Pair{}, err
	}
	if err := writePublic(keys, "authorized_keys", pair.Public); err != nil {
		return Pair{}, err
	}
	return pair, nil
}

// EnsurePivots provisions the two project identities and writes the two
// target authorization files. Startup calls it after EnsureControlPlane for
// in-tree scenarios. Pack realization supplies its own authorization layout.
func EnsurePivots(ctx context.Context, projectRoot string, control Pair) (err error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return fmt.Errorf("prepare project SSH keys: %w", ctxErr)
	}
	project, err := projectstate.OpenProjectRoot(projectRoot)
	if err != nil {
		return errors.New("open SSH project root")
	}
	defer func() { err = errors.Join(err, closeDir(project)) }()
	if !matchingPublic(control.Signer, control.Public) {
		return errors.New("invalid operator SSH public key")
	}
	config, err := openOwnedSubdir(project, "config", project.MakeSubdir)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeDir(config)) }()
	pivot, err := openOwnedSubdir(config, "lab-ssh", config.MakeSubdir)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeDir(pivot)) }()
	keys, err := openOwnedSubdir(project, keysDir, project.MakeSubdir)
	if err != nil {
		return err
	}
	defer func() { err = errors.Join(err, closeDir(keys)) }()
	return provisionPivots(ctx, pivot, keys, control.Public)
}

func provisionPivots(ctx context.Context, pivot, keys *securefile.Dir, control []byte) error {
	kali, err := EnsurePair(ctx, pivot, kaliKey, "aptl-kali-pivot")
	if err != nil {
		return err
	}
	workstation, err := EnsurePair(ctx, pivot, victimKey, "aptl-workstation-pivot")
	if err != nil {
		return err
	}
	target := bytes.Join([][]byte{publicLine(control), kali.Public}, nil)
	if err := writePublic(keys, "target_authorized_keys", target); err != nil {
		return err
	}
	return writePublic(keys, "victim_authorized_keys", append(target, workstation.Public...))
}

// EnsurePair securely creates an Ed25519 key pair or reuses a matching
// existing identity in an owner-selected directory.
func EnsurePair(ctx context.Context, dir *securefile.Dir, name, comment string) (pair Pair, err error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return Pair{}, fmt.Errorf("prepare SSH key pair: %w", ctxErr)
	}
	if pathErr := securefile.CheckPath(name); pathErr != nil || strings.Contains(name, "/") {
		return Pair{}, errors.New("invalid SSH private key location")
	}
	if !validComment(comment) {
		return Pair{}, errors.New("invalid SSH key comment")
	}

	if dir.CheckWriteOwner() != nil {
		return Pair{}, errors.New("SSH key directory allows untrusted changes")
	}
	lock, err := dir.OpenLockFile("." + name + ".lock")
	if err != nil {
		return Pair{}, errors.New("open SSH key lock")
	}
	defer func() { err = errors.Join(err, closeKeyFile(lock)) }()
	if err := filelock.Lock(ctx, lock, filelock.Exclusive, 10*time.Second); err != nil {
		return Pair{}, errors.New("acquire SSH key lock")
	}
	return preparePair(dir, name, comment)
}

func preparePair(dir *securefile.Dir, name, comment string) (Pair, error) {
	err := dir.RestrictToOwner(name)
	if err == nil {
		pair, readErr := readPair(dir, name)
		if readErr != nil {
			return Pair{}, readErr
		}
		return pair, writePublic(dir, name+".pub", pair.Public)
	}
	if errors.Is(err, fs.ErrNotExist) {
		return createMissingPair(dir, name, comment)
	}
	return Pair{}, errors.New("protect SSH private key")
}

func createMissingPair(dir *securefile.Dir, name, comment string) (Pair, error) {
	if public, err := dir.Open(name + ".pub"); err == nil {
		return Pair{}, errors.Join(errors.New("SSH public key has no matching private key"), closeKeyFile(public))
	} else if !errors.Is(err, fs.ErrNotExist) {
		return Pair{}, errors.New("check SSH public key path")
	}
	return createPair(dir, name, comment)
}

func createPair(dir *securefile.Dir, name, comment string) (Pair, error) {
	_, private, err := ed25519.GenerateKey(nil)
	if err != nil {
		return Pair{}, errors.New("generate SSH private key")
	}
	block, err := ssh.MarshalPrivateKey(private, comment)
	if err != nil {
		return Pair{}, errors.New("encode SSH private key")
	}
	defer clear(block.Bytes)
	signer, err := ssh.NewSignerFromKey(private)
	if err != nil {
		return Pair{}, errors.New("create SSH signer")
	}
	data := pem.EncodeToMemory(block)
	defer clear(data)
	if err := dir.CreateOwnerRead(name, data); err != nil {
		if errors.Is(err, fs.ErrExist) {
			return readPair(dir, name)
		}
		return Pair{}, errors.New("publish SSH private key")
	}
	public := bytes.TrimSuffix(ssh.MarshalAuthorizedKey(signer.PublicKey()), []byte("\n"))
	if comment != "" {
		public = fmt.Appendf(public, " %s", comment)
	}
	public = append(public, '\n')
	if err := writePublic(dir, name+".pub", public); err != nil {
		return Pair{}, err
	}
	return Pair{Signer: signer, Public: public, Generated: true}, nil
}

func readPair(dir *securefile.Dir, name string) (Pair, error) {
	keyFile, err := dir.OpenOwned(name, true)
	if err != nil {
		return Pair{}, errors.New("open trusted SSH private key")
	}
	private, err := readBounded(keyFile, 32<<10)
	if err != nil {
		clear(private)
		return Pair{}, errors.New("read SSH private key")
	}
	defer clear(private)
	signer, err := ssh.ParsePrivateKey(private)
	if err != nil {
		return Pair{}, errors.New("parse SSH private key")
	}
	publicFile, err := dir.OpenOwned(name+".pub", false)
	if err != nil {
		return Pair{}, errors.New("open trusted SSH public key")
	}
	public, err := readBounded(publicFile, maxPublicKey)
	if err != nil {
		return Pair{}, errors.New("read SSH public key")
	}
	if !matchingPublic(signer, public) {
		return Pair{}, errors.New("SSH public key does not match private key")
	}
	return Pair{Signer: signer, Public: publicLine(public)}, nil
}

// ReadPair loads an existing, matching key pair without rewriting it.
func ReadPair(ctx context.Context, dir *securefile.Dir, name string) (Pair, error) {
	if ctxErr := ctx.Err(); ctxErr != nil {
		return Pair{}, fmt.Errorf("load SSH key pair: %w", ctxErr)
	}
	if dir.CheckWriteOwner() != nil {
		return Pair{}, errors.New("SSH key directory allows untrusted changes")
	}
	return readPair(dir, name)
}

func matchingPublic(signer ssh.Signer, public []byte) bool {
	key, err := parsePublic(public)
	return err == nil && signer != nil && bytes.Equal(key.key.Marshal(), signer.PublicKey().Marshal())
}

func writePublic(dir *securefile.Dir, name string, data []byte) error {
	if err := dir.Replace(name, data, publicMode); err != nil {
		return errors.New("write SSH public key file")
	}
	return nil
}

func readBounded(file *os.File, limit int64) (data []byte, err error) {
	defer func() { err = errors.Join(err, closeKeyFile(file)) }()
	data, err = io.ReadAll(io.LimitReader(file, limit+1))
	if int64(len(data)) > limit {
		return data, errors.New("SSH file exceeds size limit")
	}
	if err != nil {
		return data, errors.New("read SSH file contents")
	}
	return data, nil
}

func closeKeyFile(file *os.File) error {
	if err := file.Close(); err != nil {
		return errors.New("close SSH file")
	}
	return nil
}

func openOwnedSubdir(parent *securefile.Dir, name string, open func(string) (*securefile.Dir, error)) (*securefile.Dir, error) {
	if err := parent.CheckWriteOwner(); err != nil {
		return nil, errors.New("SSH parent directory allows untrusted changes")
	}
	dir, err := open(name)
	if err != nil {
		return nil, errors.New("open SSH directory")
	}
	if err := dir.CheckWriteOwner(); err != nil {
		return nil, errors.Join(errors.New("SSH directory allows untrusted changes"), closeDir(dir))
	}
	return dir, nil
}

func closeDir(dir *securefile.Dir) error {
	if err := dir.Close(); err != nil {
		return errors.New("close SSH file directory")
	}
	return nil
}
