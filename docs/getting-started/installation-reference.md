# Installation Compatibility

This reference describes existing package and command names.
Use [Install LilRAE](installation.md) for installation and migration tasks.

## Distribution Names

`aptl-labs` 7.0.0 was the last release under that distribution name.
Releases from 8.0.0 publish as `lilrae`.
Both distributions install the `aptl` import package.
Installing them over each other can overwrite shared files; removing either can then damage the other.
Package migration does not move project data or Docker volumes.

## Command Compatibility

The release after 8.1.0 introduced `lilrae` and `lilrae-misp-suricata-sync`.
The candidate package still registers the deprecated `aptl` and `aptl-misp-suricata-sync` aliases.
Their planned removal target was 10.0.0; issue #1403 tracks removal.
Use package entry points to establish availability in a specific release.
They use the same options, stdout, JSON output, and exit status as the supported commands.
Each invocation emits a stderr notice:

```text
warning: the 'aptl' command is deprecated and will be removed in LilRAE 10.0.0. Use 'lilrae' instead. Set LILRAE_SUPPRESS_APTL_DEPRECATION=1 to hide this notice.
```

Only `LILRAE_SUPPRESS_APTL_DEPRECATION=1` hides that notice.
The rename leaves `aptl` imports, `aptl.json`, `APTL_*` variables, `.aptl/`, and existing resource names unchanged.
Generated seat commands already use `lilrae`.
