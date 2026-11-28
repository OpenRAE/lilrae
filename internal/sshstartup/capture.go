// Package sshstartup collects the SSH host pins for one admitted lab start.
package sshstartup

import (
	"context"
	"errors"
	"fmt"
	"time"

	"golang.org/x/crypto/ssh"

	"github.com/OpenRAE/lilrae/internal/sshkeys"
)

// Probe returns the wire server key after a startup connection authenticates.
type Probe func(context.Context, sshkeys.Endpoint, ssh.Signer) ([]byte, error)

// Result reports the inventory names of probed endpoints.
type Result struct {
	Pinned  []string
	Failed  []string
	Skipped bool
}

// Capture probes admitted endpoints and publishes one completed snapshot.
// The caller holds the lifecycle mutation lease.
func Capture(ctx context.Context, root string, endpoints []sshkeys.Endpoint, signer ssh.Signer, probe Probe) (Result, error) {
	if signer == nil {
		return Result{Skipped: true}, nil
	}
	if len(endpoints) > 0 && probe == nil {
		return Result{}, errors.New("missing SSH startup probe")
	}
	var result Result
	var pins []sshkeys.HostPin
	for _, ep := range endpoints {
		if err := ctx.Err(); err != nil {
			return result, fmt.Errorf("capture SSH host pins: %w", err)
		}
		wire := probeEndpoint(ctx, ep, signer, probe)
		if wire == nil {
			result.Failed = append(result.Failed, ep.Name)
			continue
		}
		pins = append(pins, sshkeys.HostPin{Endpoint: ep, Wire: wire})
		result.Pinned = append(result.Pinned, ep.Name)
	}
	return result, sshkeys.PublishPins(ctx, root, pins)
}

func probeEndpoint(ctx context.Context, ep sshkeys.Endpoint, signer ssh.Signer, probe Probe) []byte {
	if _, err := ep.Address(); err != nil {
		return nil
	}
	bounded, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	wire, err := probe(bounded, ep, signer)
	if err != nil || bounded.Err() != nil {
		return nil
	}
	if _, err := ssh.ParsePublicKey(wire); err != nil {
		return nil
	}
	return wire
}
