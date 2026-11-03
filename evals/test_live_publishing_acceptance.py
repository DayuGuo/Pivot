"""Live acceptance must opt in and can target only the local application."""

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "accept-live-publishing.py"
spec = importlib.util.spec_from_file_location("live_publishing", PATH)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1.evil.test",
        "file:///tmp/x",
        "http://user:password@localhost:8100",
        "http://localhost:8100/path",
        "http://localhost:8100?target=external",
        "http://localhost:8100#fragment",
        "http://0.0.0.0:8100",
    ],
)
def test_live_acceptance_refuses_nonlocal_or_credential_urls(url):
    with pytest.raises(argparse.ArgumentTypeError):
        acceptance.local_url(url)


@pytest.mark.parametrize("flags", [[], ["--live"], ["--synthetic-writes"]])
def test_both_opt_ins_required_before_any_model_or_business_call(monkeypatch, flags):
    monkeypatch.setattr(sys, "argv", ["accept-live-publishing.py", *flags])

    def forbidden(_):
        pytest.fail("No network or mutations without both explicit opt-ins")

    monkeypatch.setattr(acceptance, "accept", forbidden)
    with pytest.raises(SystemExit) as error:
        acceptance.main()
    assert error.value.code == 2
