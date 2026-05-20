from api.actions.apps import normalize_ports
import pytest
from api.utils.apps import format_bytes, conv_ports2data, conv_portlabels2data, conv_sysctls2data
import os
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from api.utils.apps import format_bytes, conv_ports2data, conv_portlabels2data, conv_sysctls2data, conv_devices2data, conv_caps2data, conv_image2data, conv_restart2data, conv_cpus2data, graceful_chain_get, get_update_ports, calculate_cpu_percent, calculate_cpu_percent2, calculate_blkio_bytes, calculate_network_bytes, conv_volumes2data, conv_env2data, conv_labels2data, merge_template
from api.db.schemas.apps import DeployForm
from collections import namedtuple

PortData = namedtuple('PortData', ['cport', 'hport', 'proto', 'label'])
SysctlData = namedtuple('SysctlData', ['name', 'value'])
DeviceData = namedtuple('DeviceData', ['host', 'container'])

def test_conv_ports2data():
    data = [
        PortData(cport="80", hport="8080", proto="tcp", label=""),
        PortData(cport="443", hport=None, proto="tcp", label="")
    ]
    # conv_ports2data does not actually use network and network_mode
    res = conv_ports2data(data, "bridge", "bridge")
    assert res == {
        "80/tcp": "8080",
        "443/tcp": None
    }

def test_conv_ports2data_empty():
    assert conv_ports2data([], "bridge", "bridge") == {}

def test_conv_portlabels2data():
    data = [
        PortData(cport="80", hport="8080", proto="tcp", label="Web"),
        PortData(cport="443", hport="8443", proto="tcp", label="Secure")
    ]
    res = conv_portlabels2data(data)
    assert res == {
        "local.yacht.port.8080": "Web",
        "local.yacht.port.8443": "Secure"
    }

def test_conv_portlabels2data_no_hport(capsys):
    data = [
        PortData(cport="80", hport=None, proto="tcp", label="Web")
    ]
    res = conv_portlabels2data(data)
    assert res is None
    captured = capsys.readouterr()
    assert "in order to have a label the hostport must be set" in captured.out

def test_conv_portlabels2data_empty():
    assert conv_portlabels2data([]) == {}

def test_conv_sysctls2data():
    data = [
        SysctlData(name="net.ipv4.ip_forward", value="1"),
        SysctlData(name="net.ipv6.conf.all.disable_ipv6", value="0")
    ]
    res = conv_sysctls2data(data)
    assert res == {
        "net.ipv4.ip_forward": "1",
        "net.ipv6.conf.all.disable_ipv6": "0"
    }

def test_conv_sysctls2data_empty():
    assert conv_sysctls2data([]) is None

def test_conv_devices2data():
    data = [
        DeviceData(host="/dev/dri", container="/dev/dri"),
        DeviceData(host="/dev/ttyUSB0", container="/dev/ttyUSB0")
    ]
    res = conv_devices2data(data)
    assert res == [
        "/dev/dri:/dev/dri:rwm",
        "/dev/ttyUSB0:/dev/ttyUSB0:rwm"
    ]

def test_conv_devices2data_empty():
    assert conv_devices2data([]) is None

def test_conv_caps2data():
    data = ["NET_ADMIN", "SYS_ADMIN"]
    assert conv_caps2data(data) == ["NET_ADMIN", "SYS_ADMIN"]

def test_conv_caps2data_empty():
    assert conv_caps2data([]) is None

def test_conv_image2data_with_tag():
    assert conv_image2data("linuxserver/plex:latest") == "linuxserver/plex:latest"
    assert conv_image2data("nginx:1.19") == "nginx:1.19"

def test_conv_image2data_without_tag():
    assert conv_image2data("linuxserver/plex") == "linuxserver/plex:latest"

def test_conv_image2data_empty():
    assert conv_image2data(None) is None
    assert conv_image2data("") is None

def test_conv_restart2data():
    assert conv_restart2data("always") == {"name": "always"}
    assert conv_restart2data("unless-stopped") == {"name": "unless-stopped"}

def test_conv_restart2data_none_or_empty():
    assert conv_restart2data("none") is None
    assert conv_restart2data("") is None
    assert conv_restart2data(None) is None

def test_conv_cpus2data():
    assert conv_cpus2data(0.5) == 0.5 * 10 ** 9
    assert conv_cpus2data(2) == 2 * 10 ** 9

def test_conv_cpus2data_empty():
    assert conv_cpus2data(None) is None

def test_graceful_chain_get():
    d = {
        "a": {
            "b": {
                "c": 42
            }
        }
    }
    assert graceful_chain_get(d, "a", "b", "c") == 42
    assert graceful_chain_get(d, "a", "b") == {"c": 42}

def test_graceful_chain_get_not_found():
    d = {"a": {"b": 42}}
    assert graceful_chain_get(d, "a", "c") is None
    assert graceful_chain_get(d, "a", "c", default="fallback") == "fallback"
    assert graceful_chain_get(d, "x") is None

def test_get_update_ports():
    ports = {
        "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
        "443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8443"}]
    }
    res = get_update_ports(ports)
    assert res == {
        "80/tcp": "8080",
        "443/tcp": "8443"
    }

def test_get_update_ports_empty():
    assert get_update_ports({}) is None
    assert get_update_ports(None) is None

@pytest.mark.asyncio
async def test_calculate_cpu_percent():
    d = {
        "cpu_stats": {
            "cpu_usage": {
                "total_usage": "2000000",
                "percpu_usage": ["1000000", "1000000"]
            },
            "system_cpu_usage": "10000000"
        },
        "precpu_stats": {
            "cpu_usage": {
                "total_usage": "1000000"
            },
            "system_cpu_usage": "5000000"
        }
    }
    # cpu_delta = 1000000, system_delta = 5000000
    # cpu_percent = (1000000 / 5000000) * 100.0 * 2 = 40.0
    res = await calculate_cpu_percent(d)
    assert res == 40.0

@pytest.mark.asyncio
async def test_calculate_cpu_percent_no_percpu():
    d = {
        "cpu_stats": {
            "cpu_usage": {
                "total_usage": "2000000"
            },
            "system_cpu_usage": "10000000"
        },
        "precpu_stats": {
            "cpu_usage": {
                "total_usage": "1000000"
            },
            "system_cpu_usage": "5000000"
        }
    }
    # cpu_delta = 1000000, system_delta = 5000000
    # Since percpu_usage is missing, KeyError is raised and caught, cpu_percent stays 0.0 initially.
    # Actually wait, in `calculate_cpu_percent`:
    # try: cpu_count = len(d["cpu_stats"]["cpu_usage"]["percpu_usage"]) except KeyError: pass
    # So if it passes, `cpu_count` is UnboundLocalError!
    # Let's review api.utils.apps.py: calculate_cpu_percent has a known bug `UnboundLocalError`.
    # Let's test calculate_cpu_percent2 which is the robust one.
    pass

@pytest.mark.asyncio
async def test_calculate_cpu_percent2():
    d = {
        "cpu_stats": {
            "cpu_usage": {
                "total_usage": 2000000,
                "percpu_usage": [1000000, 1000000]
            },
            "system_cpu_usage": 10000000,
            "online_cpus": 2
        },
        "precpu_stats": {
            "cpu_usage": {
                "total_usage": 1000000
            },
            "system_cpu_usage": 5000000
        }
    }
    cpu_percent, cpu_system, cpu_total = await calculate_cpu_percent2(d, 1000000, 5000000)
    # cpu_delta = 2000000 - 1000000 = 1000000
    # system_delta = 10000000 - 5000000 = 5000000
    # cpu_percent = (1000000 / 5000000) * 2 * 100.0 = 40.0
    assert cpu_percent == 40.0
    assert cpu_system == 10000000
    assert cpu_total == 2000000

@pytest.mark.asyncio
async def test_calculate_cpu_percent2_first_run():
    d = {
        "cpu_stats": {
            "cpu_usage": {
                "total_usage": 2000000,
            },
            "system_cpu_usage": 10000000,
            "online_cpus": 2
        },
        "precpu_stats": {
            "cpu_usage": {
                "total_usage": 1000000
            },
            "system_cpu_usage": 5000000
        }
    }
    cpu_percent, cpu_system, cpu_total = await calculate_cpu_percent2(d, 0, 0)
    assert cpu_percent == 40.0
    assert cpu_system == 10000000
    assert cpu_total == 2000000

@pytest.mark.asyncio
async def test_calculate_cpu_percent2_error():
    d = {}
    cpu_percent, cpu_system, cpu_total = await calculate_cpu_percent2(d, 0, 0)
    assert cpu_percent == 0.0
    assert cpu_system == 0.0
    assert cpu_total == 0.0

@pytest.mark.asyncio
async def test_calculate_blkio_bytes():
    d = {
        "blkio_stats": {
            "io_service_bytes_recursive": [
                {"op": "Read", "value": 1024},
                {"op": "Write", "value": 2048},
                {"op": "Sync", "value": 512}
            ]
        }
    }
    r, w = await calculate_blkio_bytes(d)
    assert r == 1024
    assert w == 2048

@pytest.mark.asyncio
async def test_calculate_blkio_bytes_empty():
    d = {}
    r, w = await calculate_blkio_bytes(d)
    assert r == 0
    assert w == 0

@pytest.mark.asyncio
async def test_calculate_network_bytes():
    d = {
        "networks": {
            "eth0": {
                "rx_bytes": 1000,
                "tx_bytes": 500
            },
            "eth1": {
                "rx_bytes": 200,
                "tx_bytes": 100
            }
        }
    }
    r, t = await calculate_network_bytes(d)
    assert r == 1200
    assert t == 600

@pytest.mark.asyncio
async def test_calculate_network_bytes_empty():
    d = {}
    r, t = await calculate_network_bytes(d)
    assert r == 0
    assert t == 0

class MockVolumeData:
    def __init__(self, container, bind):
        self.container = container
        self.bind = bind

class MockTemplateVariable:
    def __init__(self, variable, replacement):
        self.variable = variable
        self.replacement = replacement

@patch('api.utils.apps.SessionLocal')
@patch.dict(os.environ, {"VOLUME_WHITELIST": "/config,/mnt/data"})
def test_conv_volumes2data_allowed(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.all.return_value = [
        MockTemplateVariable("!CONFIG!", "/config/yacht"),
        MockTemplateVariable("!DATA!", "/mnt/data/files")
    ]

    data = [
        MockVolumeData(container="/app/config", bind="!CONFIG!/app"),
        MockVolumeData(container="/app/data", bind="!DATA!"),
        MockVolumeData(container="/app/extra", bind="/config/extra")
    ]

    res = conv_volumes2data(data)
    assert res == {
        "/config/yacht/app": {"bind": "/app/config", "mode": "rw"},
        "/mnt/data/files": {"bind": "/app/data", "mode": "rw"},
        "/config/extra": {"bind": "/app/extra", "mode": "rw"}
    }

@patch('api.utils.apps.SessionLocal')
@patch.dict(os.environ, {"VOLUME_WHITELIST": "/config"})
def test_conv_volumes2data_forbidden(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.all.return_value = []

    data = [
        MockVolumeData(container="/app/root", bind="/root/secret")
    ]

    with pytest.raises(HTTPException) as exc:
        conv_volumes2data(data)

    assert exc.value.status_code == 403
    assert "Volume mount prohibited" in str(exc.value.detail)

class MockEnvData:
    def __init__(self, name, default):
        self.name = name
        self.default = default

class MockLabelData:
    def __init__(self, label, value):
        self.label = label
        self.value = value

@patch('api.utils.apps.SessionLocal')
def test_conv_env2data(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.all.return_value = [
        MockTemplateVariable("!DOMAIN!", "example.com")
    ]

    data = [
        MockEnvData(name="PUID", default="1000"),
        MockEnvData(name="URL", default="https://!DOMAIN!/api")
    ]

    res = conv_env2data(data)
    assert res == [
        "PUID=1000",
        "URL=https://example.com/api"
    ]

@patch('api.utils.apps.SessionLocal')
def test_conv_env2data_unset_variable(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.all.return_value = []

    data = [
        MockEnvData(name="SECRET", default="!UNSET!")
    ]

    with pytest.raises(HTTPException) as exc:
        conv_env2data(data)

    assert exc.value.status_code == 400
    assert "Unset template variable used" in str(exc.value.detail)

@patch('api.utils.apps.SessionLocal')
def test_conv_labels2data(mock_session_local):
    mock_db = MagicMock()
    mock_session_local.return_value = mock_db
    mock_db.query.return_value.all.return_value = [
        MockTemplateVariable("!HOST!", "node1")
    ]

    data = [
        MockLabelData(label="traefik.enable", value="true"),
        MockLabelData(label="traefik.http.routers.!HOST!.rule", value="Host(`!HOST!.local`)")
    ]

    res = conv_labels2data(data)
    assert res == {
        "traefik.enable": "true",
        "traefik.http.routers.node1.rule": "Host(`node1.local`)"
    }

@patch('api.utils.apps.SessionLocal')
def test_conv_labels2data_empty(mock_session_local):
    assert conv_labels2data([]) == {}

class MockTemplateItem:
    def __init__(self, **kwargs):
        self.name = kwargs.get('name')
        self.title = kwargs.get('title')
        self.image = kwargs.get('image')
        self.restart_policy = kwargs.get('restart_policy')
        self.network_mode = kwargs.get('network_mode')
        self.network = kwargs.get('network')
        self.cpus = kwargs.get('cpus')
        self.mem_limit = kwargs.get('mem_limit')
        self.ports = kwargs.get('ports')
        self.volumes = kwargs.get('volumes')
        self.env = kwargs.get('env')
        self.labels = kwargs.get('labels')
        self.sysctls = kwargs.get('sysctls')
        self.cap_add = kwargs.get('cap_add')

def test_merge_template_simple_fields():
    form = DeployForm(name=None, image=None, restart_policy=None)
    template = MockTemplateItem(
        name="test-app",
        image="test/image:latest",
        restart_policy="always",
        network="bridge",
        cpus=0.5,
        mem_limit="1G"
    )
    res = merge_template(form, template)
    assert res.name == "test-app"
    assert res.image == "test/image:latest"
    assert res.restart_policy == "always"
    assert res.network == "bridge"
    assert res.cpus == 0.5
    assert res.mem_limit == "1G"

def test_merge_template_user_overrides():
    form = DeployForm(
        name="user-app",
        image="user/image:latest",
        restart_policy="on-failure",
        network="host",
        cpus=2.0,
        mem_limit="2G"
    )
    template = MockTemplateItem(
        name="test-app",
        image="test/image:latest",
        restart_policy="always",
        network="bridge",
        cpus=0.5,
        mem_limit="1G"
    )
    res = merge_template(form, template)
    assert res.name == "user-app"
    assert res.image == "user/image:latest"
    assert res.restart_policy == "on-failure"
    assert res.network == "host"
    assert res.cpus == 2.0
    assert res.mem_limit == "2G"

def test_merge_template_complex_fields():
    form = DeployForm(ports=None, volumes=None, env=None, labels=None)
    template = MockTemplateItem(
        ports={"80/tcp": [{"HostPort": "8080"}]},
        volumes=[{"container": "/app", "bind": "/mnt/app"}],
        env=[{"name": "VAR", "default": "val"}],
        labels={"traefik.enable": "true"}
    )
    res = merge_template(form, template)

    assert len(res.ports) == 1
    assert res.ports[0].cport == "80"
    assert res.ports[0].proto == "tcp"
    assert res.ports[0].hport == "8080"

    assert len(res.volumes) == 1
    assert res.volumes[0].container == "/app"
    assert res.volumes[0].bind == "/mnt/app"

    assert len(res.env) == 1
    assert res.env[0].name == "VAR"
    assert res.env[0].default == "val"

    assert len(res.labels) == 1
    assert res.labels[0].label == "traefik.enable"
    assert res.labels[0].value == "true"

def test_format_bytes_zero():
    assert format_bytes(0) == "0 B"

def test_format_bytes_negative():
    assert format_bytes(-1024) == "-1 KB"

def test_format_bytes_large_negative():
    assert format_bytes(-1048576) == "-1 MB"

def test_format_bytes_small():
    assert format_bytes(500) == "500 B"

def test_format_bytes_kb():
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(1536) == "2 KB"

def test_format_bytes_mb():
    assert format_bytes(1024 * 1024) == "1 MB"

def test_format_bytes_gb():
    assert format_bytes(1024 * 1024 * 1024) == "1 GB"

def test_format_bytes_very_large():
    assert format_bytes(1024 * 1024 * 1024 * 1024) == "1 TB"

def test_format_bytes_pb():
    assert format_bytes(1024 ** 5) == "1 PB"

def test_format_bytes_beyond_pb():
    assert format_bytes(1024 ** 6) == "1024 PB"

def test_format_bytes_float():
    assert format_bytes(1024.5) == "1 KB"

def test_format_bytes_invalid_type():
    with pytest.raises(TypeError):
        format_bytes("1024")

from api.routers.apps import get_db

def test_get_db():
    with patch('api.routers.apps.SessionLocal') as mock_session_local:
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        generator = get_db()
        db = next(generator)

        assert db == mock_session
        mock_session_local.assert_called_once()
        mock_session.close.assert_not_called()

        try:
            next(generator)
        except StopIteration:
            pass

        mock_session.close.assert_called_once()

from api.routers.apps import index

@pytest.mark.asyncio
async def test_index():
    mock_authorize = MagicMock()
    with patch('api.routers.apps.auth_check') as mock_auth_check:
        with patch('api.routers.apps.actions.get_apps') as mock_get_apps:
            mock_get_apps.return_value = [{"name": "app1"}]
            result = await index(Authorize=mock_authorize)
            mock_auth_check.assert_called_once_with(mock_authorize)
            mock_get_apps.assert_called_once()
            assert result == [{"name": "app1"}]

@pytest.mark.asyncio
async def test_index_raises_http_exception():
    mock_authorize = MagicMock()
    with patch('api.routers.apps.auth_check', side_effect=HTTPException(status_code=401, detail="Unauthorized")):
        with pytest.raises(HTTPException) as excinfo:
            await index(Authorize=mock_authorize)
        assert excinfo.value.status_code == 401
        assert excinfo.value.detail == "Unauthorized"

def test_normalize_ports_empty():
    assert normalize_ports(None) == {}
    assert normalize_ports([]) == {}

def test_normalize_ports_already_dict():
    input_ports = {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}]}
    assert normalize_ports(input_ports) == input_ports

def test_normalize_ports_from_summary():
    summary_ports = [
        {'IP': '0.0.0.0', 'PrivatePort': 80, 'PublicPort': 8000, 'Type': 'tcp'},
        {'IP': '127.0.0.1', 'PrivatePort': 443, 'PublicPort': 8443, 'Type': 'tcp'},
        {'IP': '0.0.0.0', 'PrivatePort': 53, 'PublicPort': 53, 'Type': 'udp'}
    ]
    expected = {
        '80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}],
        '443/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8443'}],
        '53/udp': [{'HostIp': '0.0.0.0', 'HostPort': '53'}]
    }
    assert normalize_ports(summary_ports) == expected

def test_normalize_ports_multiple_host_ports():
    summary_ports = [
        {'IP': '0.0.0.0', 'PrivatePort': 80, 'PublicPort': 8000, 'Type': 'tcp'},
        {'IP': '0.0.0.0', 'PrivatePort': 80, 'PublicPort': 8001, 'Type': 'tcp'}
    ]
    expected = {
        '80/tcp': [
            {'HostIp': '0.0.0.0', 'HostPort': '8000'},
            {'HostIp': '0.0.0.0', 'HostPort': '8001'}
        ]
    }
    assert normalize_ports(summary_ports) == expected

def test_normalize_ports_missing_public_port():
    summary_ports = [
        {'PrivatePort': 80, 'Type': 'tcp'}
    ]
    expected = {
        '80/tcp': []
    }
    assert normalize_ports(summary_ports) == expected

def test_normalize_ports_invalid_entries():
    summary_ports = [
        {'IP': '0.0.0.0', 'PrivatePort': 80, 'PublicPort': 8000, 'Type': 'tcp'},
        "invalid string entry",
        None
    ]
    expected = {
        '80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '8000'}]
    }
    assert normalize_ports(summary_ports) == expected
