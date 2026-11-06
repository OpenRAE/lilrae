<a id="installation"></a>

# Install LilRAE

Use this guide to install the released CLI and create a project.
First complete [host preparation](prerequisites.md) on an approved isolated lab machine.
Use pipx with a [supported Python interpreter](host-requirements.md#tools-and-resources) from an approved package source.
Do not run lab commands or behavior tests on the developer workstation.

## Install The Released Package

Install the CLI in its own pipx environment:

```shell
pipx install --python 3.14 lilrae
lilrae --version
```

Expected result: `lilrae --version` prints the installed version.
If the command is unavailable, run `pipx ensurepath` and open a new terminal.
If Python 3.14 is missing, install it through your approved source first.
Where your policy permits pipx to fetch Python, use:

```shell
pipx install --python 3.14 --fetch-missing-python lilrae
```

Do not install the CLI into an externally managed system Python.

## Create A Lab Project

Create a new project directory:

```shell
lilrae lab init my-lab
cd my-lab
```

Expected result: the directory contains released assets and a default `aptl.json`.
The wheel includes configuration, container build contexts, MCP sources, web sources, and the full participant profile.
The environment-pack dependency supplies released scenarios.
For the desktop-seat tutorial, follow [Workshop setup](../workshop/setup.md).
The historical reduced fixture needs separate checkout inputs.

A new project has no selected scenario identity.
Continue with [Run your first lab](quick-start.md) to select TechVault and verify startup.
Keep generated `.env`, `.mcp.json`, keys, and `.aptl/` artifacts private.
Do not attach them to support reports.

## Upgrade

Upgrade the installed package:

```shell
pipx upgrade lilrae
```

To obtain the new release's full asset set, create a new project:

```shell
lilrae lab init my-new-lab
```

Expected result: a separate project with the new assets and no copied runtime credentials.
Select its scenario before startup.
Do not copy generated credentials or runtime state between projects.

## Move From The aptl Command

Replace deprecated command names in scripts, CI jobs, and shell aliases.
Keep existing configuration and state identifiers unchanged.
See the [command compatibility reference](installation-reference.md#command-compatibility) for the alias lifetime and notice.

### Update Your Scripts

1. Run `pipx upgrade lilrae`.
2. Run `lilrae --version` to check the new command.
3. Replace command invocations of `aptl` with `lilrae`.
4. Replace `aptl-misp-suricata-sync` invocations with `lilrae-misp-suricata-sync`.
5. If you use shell completion, run `lilrae --install-completion`.

Do not rename `aptl.json`, `.aptl/`, Python imports, or `APTL_*` settings.
Expected result: scripts use the supported command with their existing options.

### Hide The Notice

For a script that cannot change yet, set `LILRAE_SUPPRESS_APTL_DEPRECATION=1` in its environment.
Only the value `1` suppresses the notice.
Prefer updating the script before the alias is removed.

### When The Alias Is Removed

Replace older seat images and scripts before upgrading to LilRAE 10.0.0.
That release removes the deprecated commands.
See [command compatibility](installation-reference.md#command-compatibility).

## Move From aptl-labs To lilrae

Record the installed extras before removing the legacy distribution.
Both distributions install the same Python package.
Remove one before installing the other to prevent shared-file damage.
`pipx upgrade aptl-labs` does not migrate the distribution name.

### Migrate A pipx Installation

```shell
pipx uninstall aptl-labs
pipx install --python 3.14 lilrae
lilrae --version
pipx list --short
```

If you used extras, install the matching requirement, for example `"lilrae[s3]"`.
Expected result: pipx lists LilRAE and the new command prints its version.

### Migrate A pip Virtual Environment

Activate the dedicated environment first.
Record its extras, then replace the distribution:

```shell
python -m pip uninstall aptl-labs
python -m pip install "lilrae[s3]"
python -m pip show lilrae
python -m pip show aptl-labs
```

Replace `[s3]` with your recorded extras or omit it.
Expected result: the legacy package is absent and LilRAE is installed.

### Keep Your Lab Projects

Retain project directories, keys, run records, and Docker volumes during package migration.
Run `lilrae lab status` from an existing project to check project discovery.
If its configuration uses retired topology booleans, follow [configuration migration](../reference/configuration-migration.md).

### Roll Back

Remove LilRAE before reinstalling the last legacy distribution:

```shell
pipx uninstall lilrae
pipx install "aptl-labs==7.0.0"
```

For a dedicated pip environment, uninstall `lilrae`, then install `aptl-labs==7.0.0`.
The legacy release provides only the `aptl` command.
Check compatibility with your project before starting an older runtime.

## Source Install For Contributors

Follow the [development setup](https://github.com/OpenRAE/lilrae/blob/dev/CONTRIBUTING.md#development-setup) for an editable installation.
Use the checkout as its project; do not initialize released assets over it.
Run behavior tests and lab operations only in CI or an approved isolated VM.
