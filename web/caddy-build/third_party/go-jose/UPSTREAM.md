# go-jose v3 security backport

Production Go source and LICENSE copied without other changes from
`github.com/go-jose/go-jose/v3` v3.0.5, verified by the existing Go checksum:
`h1:BLLJWbC4nMZOfuPVxoZIxeYsn6Nl2r1fITaJ78UQlVQ=`.
The local module keeps only its production dependency on `golang.org/x/crypto`,
at the same version selected by the parent Caddy build.

The changes in `jwk.go`, `shared.go`, `jws.go`, and `jwe.go` backport the
security protections from upstream commit
[a0111f82742fa92bceec9ede40845e73319e6230](https://github.com/go-jose/go-jose/commit/a0111f82742fa92bceec9ede40845e73319e6230):

- Bound RSA moduli to 4096 bits and check prime sizes and consistency before
  RSA private-key validation.
- Reject private key parameters in embedded JWK/EPK headers before parsing
  private keys; preserve direct loading of trusted private JWKs.
- Populate general JWS unprotected headers before sanitizing them.
- Preserve the underlying JWE header error.

In `json/decode.go`, the four hexadecimal digits of a Unicode escape are
parsed with an explicit 16-bit bound before conversion to a rune. This makes
the existing input bound visible to CodeQL without changing accepted input.

This fixes [CVE-2026-116587 / GHSA-mgcc-cww5-fp2q](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q).
Upstream released these protections in v4.1.6 but has no patched v3 release.
Caddy's Smallstep dependencies still need the v3 API. The parent module uses
an explicit local replacement so both the build and regression tests use this
copy. No scan waiver is used.

Run `go test -v .` from `web/caddy-build` to exercise the backport through the
dependency selected by Caddy. These tests run in the web CI job as well.
Remove this directory and the replacement when the upstream v3 dependency can
be upgraded to a patched release or removed by a Caddy dependency upgrade.
