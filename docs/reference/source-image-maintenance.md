# Maintain source-image entries

The [catalog reference](../source-image-catalog.md) defines selection authority, compatibility, diagnostics, provenance, and readback limits.
Use existing reviewed distributions and pins.
Registry sources must stay within the approved service boundary.

## Update the existing catalog

1. Identify the exact source/version selector and its existing semantic profile.
2. When you add an alias for a profile, reuse its existing pin.
3. Edit `src/aptl/backends/_lilrae_source_image_catalog.py` for an approved new source record.
4. Keep the immutable reference, compatibility selector, and provenance inputs.
5. Keep the release fixture consistent with the release under verification.
6. Update the existing cases in `tests/test_lilrae_source_image_catalog.py` for uncovered behavior.
7. Run that targeted test path in CI or an approved isolated VM.
8. Let CI do full suites and clean lifecycle qualification.

Do tests for unknown, ambiguous, incompatible, and unverified-source failures as well as successful selection.
Do not add runtime permissions merely to make an image selection succeed.
