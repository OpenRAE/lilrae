"""Random values are made once per run, and readback checks each stored value."""

from raes_contracts.planning import PlannedResource, RuntimeDomain

from aptl.backends.raes_random_values import observe_random_value, random_values


def _flag(name: str = "ad-root-flag-value") -> PlannedResource:
    return PlannedResource(
        address=f"provision.generated-artifact.{name}",
        domain=RuntimeDomain.PROVISIONING,
        resource_type="generated-artifact",
        payload={
            "name": name,
            "scope_binding": "run:1",
            "spec": {
                "generator": "random_value",
                "random_value": {"alphabet": "hex_lower", "length": 8,
                                 "format": {"prefix": "FLAG{", "suffix": "}"}},
                "outputs": [{"name": "flag", "path": "flag.txt"}],
            },
        },
    )


def test_values_are_made_once_and_read_back_against_their_generator(tmp_path):
    flag = _flag()
    observed = observe_random_value(flag, tmp_path)
    assert not observed.realized
    first = random_values([flag], tmp_path)
    value = first[("ad-root-flag-value", "flag")]
    assert value.startswith("FLAG{") and value.endswith("}") and len(value) == 14
    assert random_values([flag], tmp_path) == first
    observed = observe_random_value(flag, tmp_path)
    assert observed.realized
    assert observed.concerns[("spec",)]["generator"] == "random_value"
    stored = next(path for path in (tmp_path / ".lilrae-generated-values").rglob("*") if path.is_file())
    for tampered in ("FLAG{0123456z}", "FLAG{01234567", "FLAG{012345678}"):
        stored.write_text(tampered, encoding="utf-8")
        assert not observe_random_value(flag, tmp_path).realized
