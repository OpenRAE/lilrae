"""A fresh checkout starts the released pack without a hand-created .env (#1700)."""

import tests.test_lab as lab_tests
from tests.test_lab import _env_key


class TestReleasedPackStart:
    """Reuse the generic start-orchestration patches with the released pack."""

    _make_env_vars = lab_tests.TestOrchestrateLabStart._make_env_vars
    _make_config = lab_tests.TestOrchestrateLabStart._make_config
    _patch_all_steps = lab_tests.TestOrchestrateLabStart._patch_all_steps

    def test_orchestrate_hydrates_missing_env(
        self, mocker, tmp_path, released_techvault_bundle
    ):
        """A fresh checkout can start without a hand-created .env."""
        from aptl.core.env import find_placeholder_env_values, load_dotenv
        from aptl.core.lab import orchestrate_lab_start

        mocks = self._patch_all_steps(mocker, tmp_path)
        mocks["resolve_bundle"].return_value = released_techvault_bundle
        (tmp_path / ".env").unlink()

        result = orchestrate_lab_start(tmp_path)
        env = load_dotenv(tmp_path / ".env")

        assert result.success is True
        assert find_placeholder_env_values(env) == []
        assert env[_env_key("INDEXER", "PASSWORD")]
        assert env[_env_key("API", "PASSWORD")]
        mocks["dashboard_creds"].assert_called_once()
        assert (
            mocks["dashboard_creds"].call_args.args[1]
            == env[_env_key("API", "PASSWORD")]
        )
        assert mocks["manager_creds"].call_args.args[1]
