import base64, gzip, hashlib, re

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import lock

PAGE = "<html><body>SECRET-MARKER market_cap_cr RELIANCE</body></html>"


def decrypt(locked, password, salt=lock.SALT):
    raw = base64.b64decode(re.search(r'const P="([^"]+)"', locked).group(1))
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, lock.ITERATIONS, dklen=32)
    return gzip.decompress(AESGCM(key).decrypt(raw[:12], raw[12:], None)).decode()


def test_locked_page_hides_content_and_round_trips():
    locked = lock.lock_html(PAGE, "a long enough passphrase")
    assert "SECRET-MARKER" not in locked and "RELIANCE" not in locked and "market_cap" not in locked
    assert decrypt(locked, "a long enough passphrase") == PAGE


def test_wrong_password_fails_and_each_lock_uses_a_fresh_iv():
    locked = lock.lock_html(PAGE, "a long enough passphrase")
    with pytest.raises(InvalidTag): decrypt(locked, "another long passphrase")
    assert locked != lock.lock_html(PAGE, "a long enough passphrase")


def test_short_passwords_are_refused():
    with pytest.raises(ValueError): lock.lock_html(PAGE, "short")


def test_cli_locks_in_place_removes_audit_csv_and_refuses_twice(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8"); (tmp_path / "corporate_actions.csv").write_text("x")
    monkeypatch.setenv("SITE_PASSWORD", "a long enough passphrase")
    lock.main(str(tmp_path / "index.html"))
    assert "SECRET-MARKER" not in (tmp_path / "index.html").read_text() and not (tmp_path / "corporate_actions.csv").exists()
    with pytest.raises(SystemExit): lock.main(str(tmp_path / "index.html"))
    monkeypatch.delenv("SITE_PASSWORD")
    (tmp_path / "other.html").write_text(PAGE)
    with pytest.raises(SystemExit): lock.main(str(tmp_path / "other.html"))
