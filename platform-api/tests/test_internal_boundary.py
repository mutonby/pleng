"""A hosted site container sits on pleng_web; it must never count as internal."""
import ipaddress
import os
import tempfile

os.environ.setdefault("DATABASE_PATH", tempfile.mktemp(suffix=".db"))
os.environ.setdefault("PROJECTS_DIR", tempfile.mkdtemp())

import app as app_module


def _web(monkeypatch, nets):
    monkeypatch.setattr(app_module, "_hosted_site_nets",
                        lambda: [ipaddress.ip_network(n) for n in nets])


def test_site_on_pleng_web_is_not_internal(monkeypatch):
    _web(monkeypatch, ["172.18.0.0/16"])
    assert app_module._is_internal("172.18.0.7") is False


def test_platform_service_on_internal_network_is_internal(monkeypatch):
    _web(monkeypatch, ["172.18.0.0/16"])
    assert app_module._is_internal("172.19.0.3") is True


def test_loopback_is_internal(monkeypatch):
    _web(monkeypatch, [])
    assert app_module._is_internal("127.0.0.1") is True


def test_unknown_site_subnet_fails_closed(monkeypatch):
    _web(monkeypatch, [])
    assert app_module._is_internal("172.19.0.3") is False


def test_public_address_is_not_internal(monkeypatch):
    _web(monkeypatch, ["172.18.0.0/16"])
    assert app_module._is_internal("8.8.8.8") is False
