import os

import mock
import pytest

from uaclient import apt, exceptions, http, messages
from uaclient.config import (
    UA_CONFIGURABLE_KEYS,
    VALID_UA_CONFIG_KEYS,
    get_config_path,
    parse_config,
)
from uaclient.conftest import FakeNotice
from uaclient.defaults import DEFAULT_CONFIG_FILE
from uaclient.files import notices, user_config_file
from uaclient.files.notices import NoticesManager
from uaclient.util import depth_first_merge_overlay_dict
from uaclient.yaml import safe_dump

KNOWN_DATA_PATHS = (("machine-id", "machine-id"),)
M_PATH = "uaclient.entitlements."


class TestNotices:
    @pytest.mark.parametrize(
        "notices,expected",
        (
            ([], ()),
            (
                [[FakeNotice.reboot_script_failed, "a1"]],
                ["a1"],
            ),
            (
                [
                    [FakeNotice.reboot_required, "a1"],
                    [FakeNotice.reboot_script_failed, "a2"],
                ],
                [
                    "a1",
                    "a2",
                ],
            ),
            (
                [
                    [FakeNotice.reboot_required, "a1"],
                    [FakeNotice.reboot_required, "a1"],
                ],
                [
                    "a1",
                ],
            ),
        ),
    )
    def test_add_notice_avoids_duplicates(
        self,
        notices,
        expected,
    ):
        notice = NoticesManager()
        assert [] == notice.list()
        for notice_ in notices:
            notice.add(*notice_)
        if notices:
            assert expected == notice.list()
        else:
            assert [] == notice.list()

    @pytest.mark.parametrize(
        "_notices",
        (
            ([]),
            ([[FakeNotice.reboot_required]]),
            (
                [
                    [FakeNotice.reboot_required],
                    [FakeNotice.reboot_script_failed],
                ]
            ),
        ),
    )
    @mock.patch("uaclient.util.we_are_currently_root", return_value=False)
    def test_add_notice_fails_as_nonroot(
        self,
        m_we_are_currently_root,
        _notices,
    ):
        assert [] == notices.list()
        for notice_ in _notices:
            notices.add(*notice_)
        assert [] == notices.list()

    @pytest.mark.parametrize(
        "notices_,removes,expected",
        (
            ([], [FakeNotice.reboot_required], []),
            (
                [[FakeNotice.reboot_script_failed]],
                [FakeNotice.reboot_script_failed],
                [],
            ),
            (
                [
                    [FakeNotice.reboot_required],
                    [FakeNotice.reboot_script_failed],
                ],
                [FakeNotice.reboot_required],
                ["notice_a2"],
            ),
            (
                [
                    [FakeNotice.reboot_required],
                    [FakeNotice.reboot_script_failed],
                    [FakeNotice.enable_reboot_required],
                ],
                [
                    FakeNotice.reboot_required,
                    FakeNotice.reboot_script_failed,
                ],
                ["notice_b"],
            ),
        ),
    )
    def test_remove_notice_removes_matching(
        self,
        notices_,
        removes,
        expected,
    ):
        for notice_ in notices_:
            notices.add(*notice_)
        for label in removes:
            notices.remove(label)
        assert expected == notices.list()


CFG_BASE_CONTENT = """\
# Ubuntu Pro client config file.
# If you modify this file, run "pro refresh config" to ensure changes are
# picked up by Ubuntu Pro client.

contract_url: https://contracts.canonical.com
data_dir: /var/lib/ubuntu-advantage
log_file: /var/log/ubuntu-advantage.log
log_level: debug
security_url: https://ubuntu.com/security
"""

CFG_FEATURES_CONTENT = """\
# Ubuntu Pro client config file.
# If you modify this file, run "pro refresh config" to ensure changes are
# picked up by Ubuntu Pro client.

contract_url: https://contracts.canonical.com
data_dir: /var/lib/ubuntu-advantage
features:
  extra_security_params:
    hide: true
  new: 2
  show_beta: true
log_file: /var/log/ubuntu-advantage.log
log_level: debug
security_url: https://ubuntu.com/security
settings_overrides:
  c: 1
  d: 2
"""

USER_CFG_DICT = {
    "apt_http_proxy": None,
    "apt_https_proxy": None,
    "apt_news": True,
    "apt_news_url": "https://motd.ubuntu.com/aptnews.json",
    "global_apt_http_proxy": None,
    "global_apt_https_proxy": None,
    "ua_apt_http_proxy": None,
    "ua_apt_https_proxy": None,
    "http_proxy": None,
    "https_proxy": None,
    "update_messaging_timer": 21600,
    "metering_timer": 14400,
    "vulnerability_data_url_prefix": "https://security-metadata.canonical.com/oval/",  # noqa
    "lxd_guest_attach": user_config_file.LXDGuestAttachEnum.OFF,
}


class TestUserConfigKeys:
    @pytest.mark.parametrize("attr_name", UA_CONFIGURABLE_KEYS)
    @mock.patch("uaclient.config.user_config_file.user_config.write")
    def test_user_configurable_keys_set_user_config(
        self, write, attr_name, tmpdir, FakeConfig
    ):
        """Getters and settings are available fo UA_CONFIGURABLE_KEYS."""
        cfg = FakeConfig()
        assert USER_CFG_DICT[attr_name] == getattr(cfg, attr_name, None)
        cfg_non_members = ("apt_http_proxy", "apt_https_proxy")
        if attr_name not in cfg_non_members:
            setattr(cfg, attr_name, attr_name + "value")
            assert attr_name + "value" == getattr(cfg, attr_name)
            assert attr_name + "value" == getattr(cfg.user_config, attr_name)


class TestProcessConfig:
    @pytest.mark.parametrize(
        [
            "http_proxy",
            "https_proxy",
            "snap_is_snapd_installed",
            "snap_http_val",
            "snap_https_val",
            "livepatch_enabled",
            "livepatch_http_val",
            "livepatch_https_val",
            "snap_livepatch_msg",
            "global_https",
            "global_http",
            "ua_https",
            "ua_http",
            "apt_https",
            "apt_http",
            "lxd_guest_attach",
            "is_attached",
        ],
        [
            (
                "http",
                "https",
                False,
                None,
                None,
                False,
                None,
                None,
                "",
                None,
                None,
                None,
                None,
                None,
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                "http",
                "https",
                True,
                None,
                None,
                False,
                None,
                None,
                "",
                None,
                None,
                None,
                None,
                "apt_https",
                "apt_http",
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                "http",
                "https",
                False,
                None,
                None,
                True,
                None,
                None,
                "",
                "global_https",
                "global_http",
                None,
                None,
                None,
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                "http",
                "https",
                True,
                None,
                None,
                True,
                None,
                None,
                "",
                None,
                None,
                "ua_https",
                "ua_http",
                None,
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                True,
                None,
                None,
                True,
                None,
                None,
                "",
                "global_https",
                "global_http",
                None,
                None,
                "apt_https",
                "apt_http",
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                True,
                "one",
                None,
                True,
                None,
                None,
                "snap",
                "global_https",
                "global_http",
                "ua_https",
                "ua_http",
                "apt_https",
                "apt_http",
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                True,
                "one",
                "two",
                True,
                None,
                None,
                "snap",
                None,
                "global_http",
                None,
                None,
                None,
                "apt_http",
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                True,
                "one",
                "two",
                True,
                "three",
                None,
                "snap, livepatch",
                "global_htttps",
                None,
                "ua_https",
                None,
                "apt_https",
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                True,
                "one",
                "two",
                True,
                "three",
                "four",
                "snap, livepatch",
                "global_https",
                None,
                None,
                "ua_http",
                None,
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                True,
            ),
            (
                None,
                None,
                False,
                None,
                None,
                True,
                "three",
                "four",
                "livepatch",
                None,
                None,
                None,
                None,
                None,
                None,
                user_config_file.LXDGuestAttachEnum.OFF,
                False,
            ),
        ],
    )
    @mock.patch("uaclient.api.u.pro.status.is_attached.v1._is_attached")
    @mock.patch("uaclient.config.state_files.lxd_pro_config_file.write")
    @mock.patch(
        "uaclient.api.u.pro.status.enabled_services.v1._enabled_services"
    )
    @mock.patch("uaclient.http.validate_proxy")
    @mock.patch("uaclient.livepatch.get_config_option_value")
    @mock.patch("uaclient.livepatch.configure_livepatch_proxy")
    @mock.patch("uaclient.snap.get_config_option_value")
    @mock.patch("uaclient.snap.configure_snap_proxy")
    @mock.patch("uaclient.snap.is_snapd_installed")
    @mock.patch("uaclient.apt.setup_apt_proxy")
    @mock.patch("uaclient.config.user_config_file.user_config.write")
    def test_process_config(
        self,
        m_write,
        m_apt_configure_proxy,
        m_snap_is_snapd_installed,
        m_snap_configure_proxy,
        m_snap_get_config_option,
        m_livepatch_configure_proxy,
        m_livepatch_get_config_option,
        m_validate_proxy,
        m_enabled_services,
        m_lxd_pro_config_file_write,
        m_is_attached,
        http_proxy,
        https_proxy,
        snap_is_snapd_installed,
        snap_http_val,
        snap_https_val,
        livepatch_enabled,
        livepatch_http_val,
        livepatch_https_val,
        snap_livepatch_msg,
        global_https,
        global_http,
        ua_https,
        ua_http,
        apt_https,
        apt_http,
        lxd_guest_attach,
        is_attached,
        capsys,
        tmpdir,
        FakeConfig,
    ):
        m_snap_is_snapd_installed.return_value = snap_is_snapd_installed
        m_snap_get_config_option.side_effect = [snap_http_val, snap_https_val]
        m_is_attached.return_value = is_attached

        _m_livepatch = mock.MagicMock()
        type(_m_livepatch).name = mock.PropertyMock(return_value="livepatch")
        m_enabled_services.return_value = mock.MagicMock(
            enabled_services=[_m_livepatch]
        )

        m_livepatch_get_config_option.side_effect = [
            livepatch_http_val,
            livepatch_https_val,
        ]
        cfg = FakeConfig({"data_dir": tmpdir.strpath})
        cfg.user_config.apt_http_proxy = apt_http
        cfg.user_config.apt_https_proxy = apt_https
        cfg.user_config.global_apt_https_proxy = global_https
        cfg.user_config.global_apt_http_proxy = global_http
        cfg.user_config.ua_apt_https_proxy = ua_https
        cfg.user_config.ua_apt_http_proxy = ua_http
        cfg.user_config.http_proxy = http_proxy
        cfg.user_config.https_proxy = https_proxy
        cfg.user_config.update_messaging_timer = 21600
        cfg.user_config.metering_timer = 0
        cfg.user_config.lxd_guest_attach = lxd_guest_attach

        if global_https is None and apt_https is not None:
            global_https = apt_https
        if global_http is None and apt_http is not None:
            global_http = apt_http

        exc = False
        if global_https or global_http:
            if ua_https or ua_http:
                exc = True
                with pytest.raises(
                    exceptions.UbuntuProError,
                    match=messages.E_INVALID_PROXY_COMBINATION.msg,
                ):
                    cfg.process_config()
        if exc is False:
            cfg.process_config()

            assert [
                mock.call(
                    "http", global_http, http.PROXY_VALIDATION_APT_HTTP_URL
                ),
                mock.call(
                    "https", global_https, http.PROXY_VALIDATION_APT_HTTPS_URL
                ),
                mock.call("http", ua_http, http.PROXY_VALIDATION_APT_HTTP_URL),
                mock.call(
                    "https", ua_https, http.PROXY_VALIDATION_APT_HTTPS_URL
                ),
                mock.call(
                    "http", http_proxy, http.PROXY_VALIDATION_SNAP_HTTP_URL
                ),
                mock.call(
                    "https", https_proxy, http.PROXY_VALIDATION_SNAP_HTTPS_URL
                ),
            ] == m_validate_proxy.call_args_list

            if global_http or global_https:
                assert [
                    mock.call(
                        global_http, global_https, apt.AptProxyScope.GLOBAL
                    )
                ] == m_apt_configure_proxy.call_args_list
            elif ua_http or ua_https:
                assert [
                    mock.call(ua_http, ua_https, apt.AptProxyScope.UACLIENT)
                ] == m_apt_configure_proxy.call_args_list
            else:
                assert [] == m_apt_configure_proxy.call_args_list

            if snap_is_snapd_installed:
                assert [
                    mock.call(http_proxy, https_proxy)
                ] == m_snap_configure_proxy.call_args_list

            if livepatch_enabled:
                assert [
                    mock.call(http_proxy, https_proxy)
                ] == m_livepatch_configure_proxy.call_args_list

            expected_out = ""
            if snap_livepatch_msg:
                expected_out = messages.PROXY_DETECTED_BUT_NOT_CONFIGURED.format(  # noqa: E501
                    services=snap_livepatch_msg
                )

            out, err = capsys.readouterr()
            expected_out = """
                Using deprecated "{apt}" config field.
                Please migrate to using "{global_}"
            """
            if apt_http and not global_http:
                assert (
                    expected_out.format(
                        apt=apt_http, global_=global_http
                    ).strip()
                    == out.strip()
                )
            if apt_https and not global_https:
                assert (
                    expected_out.format(
                        apt=apt_https, global_=global_https
                    ).strip()
                    == out.strip()
                )
            assert "" == err
            if (
                lxd_guest_attach != user_config_file.LXDGuestAttachEnum.OFF
                or is_attached
            ):
                assert m_lxd_pro_config_file_write.call_args_list == [
                    mock.call(mock.ANY)
                ]

    def test_process_config_errors_for_wrong_timers(self, FakeConfig):
        cfg = FakeConfig()
        cfg.user_config.update_messaging_timer = "wrong"

        with pytest.raises(
            exceptions.UbuntuProError,
            match=(
                "Cannot set update_messaging_timer to wrong: <value> for "
                "interval must be a positive integer."
            ),
        ):
            cfg.process_config()


class TestParseConfig:
    @mock.patch("uaclient.config.os.path.exists", return_value=False)
    @mock.patch("uaclient.contract.get_available_resources")
    def test_parse_config_uses_defaults_when_no_config_present(
        self, _m_resources, m_exists
    ):
        with mock.patch.dict("uaclient.config.os.environ", values={}):
            config, _ = parse_config()
        expected_calls = [
            mock.call("/etc/ubuntu-advantage/uaclient.conf"),
        ]
        assert expected_calls == m_exists.call_args_list
        expected_default_config = {
            "contract_url": "https://contracts.canonical.com",
            "security_url": "https://ubuntu.com/security",
            "data_dir": "/var/lib/ubuntu-advantage",
            "log_file": "/var/log/ubuntu-advantage.log",
            "log_level": "debug",
        }
        assert expected_default_config == config

    @pytest.mark.parametrize(
        "config_dict,expected_invalid_keys",
        (
            ({"contract_url": "http://abc", "security_url": "http:xyz"}, []),
            (
                {"contract_urs": "http://abc", "security_url": "http:xyz"},
                ["contract_urs"],
            ),
        ),
    )
    def test_parse_config_returns_invalid_keys(
        self, config_dict, expected_invalid_keys, tmpdir
    ):
        config_file = tmpdir.join("uaclient.conf")
        config_file.write(safe_dump(config_dict))
        env_vars = {"UA_CONFIG_FILE": config_file.strpath}
        with mock.patch.dict("uaclient.config.os.environ", values=env_vars):
            cfg, invalid_keys = parse_config(config_file.strpath)
        assert set(expected_invalid_keys) == invalid_keys
        for key, value in config_dict.items():
            if key in VALID_UA_CONFIG_KEYS:
                assert config_dict[key] == cfg[key]

    @pytest.mark.parametrize(
        "envvar_name,envvar_val,field,expected_val",
        [
            # not on allowlist
            (
                "UA_CONTRACT_URL",
                "https://contract",
                "contract_url",
                "https://contracts.canonical.com",
            ),
            # on allowlist
            (
                "UA_security_URL",
                "https://security",
                "security_url",
                "https://security",
            ),
            (
                "ua_data_dir",
                "~/somedir",
                "data_dir",
                "{}/somedir".format(os.path.expanduser("~")),
            ),
            ("Ua_LoG_FiLe", "some.log", "log_file", "some.log"),
            ("UA_LOG_LEVEL", "debug", "log_level", "debug"),
        ],
    )
    @mock.patch("uaclient.config.os.path.exists", return_value=False)
    @mock.patch("uaclient.contract.get_available_resources")
    def test_parse_config_scrubs_user_environ_values(
        self,
        _m_resources,
        m_exists,
        envvar_name,
        envvar_val,
        field,
        expected_val,
    ):
        user_values = {envvar_name: envvar_val}
        with mock.patch.dict("uaclient.config.os.environ", values=user_values):
            config, _ = parse_config()
        assert expected_val == config[field]

    @mock.patch("uaclient.config.os.path.exists", return_value=False)
    def test_parse_config_scrubs_user_environ_values_features(self, m_exists):
        user_values = {
            "UA_FEATURES_X_Y_Z": "XYZ_VAL",
            "UA_FEATURES_A_B_C": "ABC_VAL",
        }
        with mock.patch.dict("uaclient.config.os.environ", values=user_values):
            config, _ = parse_config()
        expected_config = {
            "features": {"a_b_c": "ABC_VAL", "x_y_z": "XYZ_VAL"}
        }
        assert expected_config["features"] == config["features"]

    @pytest.mark.parametrize(
        "env_var,env_value", [("UA_SECURITY_URL", "ht://security")]
    )
    @mock.patch("uaclient.config.os.path.exists", return_value=False)
    def test_parse_raises_errors_on_invalid_urls(
        self, _m_exists, env_var, env_value
    ):
        user_values = {env_var: env_value}  # no acceptable url scheme
        with mock.patch.dict("uaclient.config.os.environ", values=user_values):
            with pytest.raises(exceptions.UbuntuProError) as excinfo:
                parse_config()
        expected_msg = "Invalid url in config. {}: {}".format(
            env_var.replace("UA_", "").lower(), env_value
        )
        assert expected_msg == excinfo.value.msg

    @mock.patch("uaclient.config.os.path.exists")
    @mock.patch("uaclient.system.load_file")
    def test_parse_reads_yaml_from_environ_values(
        self, m_load_file, m_path_exists
    ):
        m_load_file.return_value = "test: true\nfoo: bar"
        m_path_exists.side_effect = [False, True]

        user_values = {"UA_FEATURES_TEST": "test.yaml"}
        with mock.patch.dict("uaclient.config.os.environ", values=user_values):
            cfg, _ = parse_config()

        assert {"test": True, "foo": "bar"} == cfg["features"]["test"]

    @mock.patch("uaclient.config.os.path.exists")
    def test_parse_raise_exception_when_environ_yaml_file_does_not_exist(
        self, m_path_exists
    ):
        m_path_exists.return_value = False
        user_values = {"UA_FEATURES_TEST": "test.yaml"}
        with mock.patch.dict("uaclient.config.os.environ", values=user_values):
            with pytest.raises(exceptions.UbuntuProError) as excinfo:
                parse_config()

        expected_msg = "Could not find yaml file: test.yaml"
        assert expected_msg == excinfo.value.msg.strip()


class TestFeatures:
    @pytest.mark.parametrize(
        "cfg_features,expected, warnings",
        (
            ({}, {}, None),
            (None, {}, None),
            (
                "badstring",
                {},
                "Unexpected uaclient.conf features value."
                " Expected dict, but found %s",
            ),
            ({"feature1": "value1"}, {"feature1": "value1"}, None),
            (
                {"feature1": "value1", "feature2": False},
                {"feature1": "value1", "feature2": False},
                None,
            ),
        ),
    )
    @mock.patch("uaclient.config.LOG.warning")
    def test_features_are_a_property_of_uaconfig(
        self,
        m_log_warning,
        cfg_features,
        expected,
        warnings,
        FakeConfig,
    ):
        user_cfg = {"features": cfg_features}
        cfg = FakeConfig(cfg_overrides=user_cfg)
        assert expected == cfg.features
        if warnings:
            assert [
                mock.call(warnings, cfg_features)
            ] == m_log_warning.call_args_list


class TestDepthFirstMergeOverlayDict:
    @pytest.mark.parametrize(
        "base_dict, overlay_dict, expected_dict",
        [
            ({"a": 1, "b": 2}, {"c": 3}, {"a": 1, "b": 2, "c": 3}),
            (
                {"a": 1, "b": {"c": 2, "d": 3}},
                {"a": 1, "b": {"c": 10}},
                {"a": 1, "b": {"c": 10, "d": 3}},
            ),
            (
                {"a": 1, "b": {"c": 2, "d": 3}},
                {"d": {"f": 20}},
                {"a": 1, "b": {"c": 2, "d": 3}, "d": {"f": 20}},
            ),
            ({"a": 1, "b": 2}, {}, {"a": 1, "b": 2}),
            ({"a": 1, "b": 2}, {"a": "test"}, {"a": "test", "b": 2}),
            ({}, {"a": 1, "b": 2}, {"a": 1, "b": 2}),
            ({"a": []}, {"a": [1, 2, 3]}, {"a": [1, 2, 3]}),
            ({"a": [5, 6]}, {"a": [1, 2, 3]}, {"a": [1, 2, 3]}),
            ({"a": [{"b": 1}]}, {"a": [{"c": 2}]}, {"a": [{"b": 1, "c": 2}]}),
        ],
    )
    def test_depth_first_merge_dict(
        self, base_dict, overlay_dict, expected_dict
    ):
        depth_first_merge_overlay_dict(base_dict, overlay_dict)
        assert expected_dict == base_dict


class TestGetConfigPath:
    def test_get_config_path_from_env_var(self):
        with mock.patch.dict(
            "uaclient.config.os.environ", values={"UA_CONFIG_FILE": "test"}
        ):
            assert "test" == get_config_path()

    def test_get_default_config_path(self):
        with mock.patch.dict("uaclient.config.os.environ", values={}):
            assert DEFAULT_CONFIG_FILE == get_config_path()


class TestConfigShow:
    @mock.patch("uaclient.config.user_config_file.user_config.write")
    def test_redact_config_data(self, _write, FakeConfig):
        cfg = FakeConfig()

        setattr(
            cfg.user_config,
            "apt_http_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "apt_https_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "global_apt_http_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "global_apt_https_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "ua_apt_http_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "ua_apt_https_proxy",
            "http://username:password@proxy:port",
        )
        setattr(
            cfg.user_config,
            "http_proxy",
            "http://username:password@proxy:port",
        )
        setattr(cfg.user_config, "https_proxy", "https://www.example.com")

        user_config_file_object = user_config_file.UserConfigFileObject()
        redacted_config = user_config_file_object.redact_config_data(
            cfg.user_config
        )

        # Assert that proxy configurations are redacted
        assert getattr(redacted_config, "apt_http_proxy") == "<REDACTED>"
        assert getattr(redacted_config, "apt_https_proxy") == "<REDACTED>"
        assert (
            getattr(redacted_config, "global_apt_http_proxy") == "<REDACTED>"
        )
        assert (
            getattr(redacted_config, "global_apt_https_proxy") == "<REDACTED>"
        )
        assert getattr(redacted_config, "ua_apt_http_proxy") == "<REDACTED>"
        assert getattr(redacted_config, "ua_apt_https_proxy") == "<REDACTED>"
        assert getattr(redacted_config, "http_proxy") == "<REDACTED>"
        assert (
            getattr(redacted_config, "https_proxy")
            == "https://www.example.com"
        )

        # Assert that redacting multiple times does not change the result
        redacted_again = user_config_file_object.redact_config_data(
            redacted_config
        )
        assert redacted_config == redacted_again
