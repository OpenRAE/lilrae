# Installation

The supported first-time path installs the released package in an isolated
pipx environment. Check the [prerequisites](prerequisites.md) first.

## Install The Released Package

Install pipx through your operating system or the
[official pipx instructions](https://pipx.pypa.io/stable/installation/), then
install LilRAE. LilRAE was formerly named APTL. It is published as the
`lilrae` package and provides the `aptl` command
([ADR-062](../adrs/adr-062-lilrae-name-and-naming-convention.md)):

```shell
pipx install lilrae
aptl --version
```

`lilrae` requires Python 3.12 or newer. On macOS, if pipx is bound to the
Command Line Tools Python 3.9, ask pipx to fetch a supported interpreter:

```shell
pipx install --python 3.12 --fetch-missing-python lilrae
```

pipx keeps the CLI outside the system Python environment, avoiding the PEP 668
system-`pip` restriction on current Debian, Ubuntu, and WSL2 hosts.

## Create A Lab Project

Materialize the released lab assets into a new project directory:

```shell
aptl lab init my-lab
cd my-lab
```

The wheel includes the Compose topology, configuration templates, container
build contexts, MCP sources, and web sources. The installed environment-pack
distribution supplies released scenarios. You do not need to clone the source
repository.

`aptl lab init` creates the durable project files. The first `aptl lab start`
creates private runtime state such as `.env`, `.mcp.json`, keys, and `.aptl/`
artifacts. Do not publish or attach those files to support reports.

Continue with [Run your first lab](quick-start.md).

## Upgrade

Upgrade the isolated installation, then initialize a new project when you want
the complete asset set from the new release:

```shell
pipx upgrade lilrae
aptl lab init my-new-lab
```

Do not copy generated credentials or state between project directories.

## Move From aptl-labs To lilrae

`aptl-labs` 7.0.0 was the last `aptl-labs` release. Releases publish to PyPI
as [`lilrae`](https://pypi.org/project/lilrae/) from version 8.0.0. The import
package, the `aptl` and `aptl-misp-suricata-sync` commands, the configuration,
and the project state do not change. `pipx upgrade aptl-labs` does not move
you to `lilrae`.

Both distributions install the same `aptl` package and the same commands. If
you install one over the other, the second installation overwrites the files of
the first. If you then remove either one, you can remove shared files. Always
remove the installed distribution before you install the other one.

`lilrae` requires Python 3.12 or newer, the same as `aptl-labs`.

### Migrate A pipx Installation

1. Remove the legacy package:

    ```shell
    pipx uninstall aptl-labs
    ```

2. Install the new package. Add `--python 3.12` if pipx uses an older
   interpreter. If you installed extras, add the same extras, for example
   `pipx install "lilrae[s3]"`:

    ```shell
    pipx install lilrae
    ```

3. Make sure that the command comes from the new installation:

    ```shell
    aptl --version
    pipx list --short
    ```

### Migrate A pip Virtual Environment

1. Write down the extras that you installed, for example `[s3]` or `[parquet]`.
2. Remove the legacy package:

    ```shell
    python -m pip uninstall aptl-labs
    ```

3. Install the new package with the same extras:

    ```shell
    python -m pip install "lilrae[s3]"
    ```

4. Make sure that only `lilrae` is installed:

    ```shell
    python -m pip show lilrae
    python -m pip show aptl-labs
    ```

    The second command must report that the package is not found.

### Keep Your Lab Projects

Your lab project directories, `aptl.json`, the `.aptl/` state, keys, run
records, and Docker volumes stay where they are. Do not delete them during the
migration. Run `aptl lab status` in an existing project to confirm that the new
installation finds it.

### Roll Back

To return to the legacy package, remove `lilrae` first, then install the last
legacy release:

```shell
pipx uninstall lilrae
pipx install "aptl-labs==7.0.0"
```

In a pip virtual environment, use `python -m pip uninstall lilrae`, then
`python -m pip install "aptl-labs==7.0.0"`. All earlier `aptl-labs` releases
stay available on PyPI.

## Source Install For Contributors

A source checkout is a development path, not a prerequisite for operating the
released lab. Contributors should follow the repository's
[development setup](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md#development-setup),
which creates a virtual environment and uses an editable install.
