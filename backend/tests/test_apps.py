import pytest
from api.utils.apps import format_bytes

def test_format_bytes_zero():
    assert format_bytes(0) == "0 B"

def test_format_bytes_negative():
    assert format_bytes(-1024) == "-1024 B"

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
