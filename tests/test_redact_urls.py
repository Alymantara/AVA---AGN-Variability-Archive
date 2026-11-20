"""C05: signed download URLs never reach the failure lists or the logs."""
import requests

from ava.lco.download import describe_error

SIGNED = ("https://archive-lco-global.s3.amazonaws.com/x/coj1m011-fa12-20261119-0042-e91.fits.fz"
          "?versionId=abc&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAXXX%2F20261120&X-Amz-Signature=deadbeef")


def test_http_error_url_redacted():
    msg = describe_error(requests.HTTPError(f"403 Client Error: Forbidden for url: {SIGNED}"))
    assert msg.startswith("HTTPError: 403 Client Error")
    assert "coj1m011-fa12-20261119-0042-e91.fits.fz?<query removed>" in msg
    assert "Signature" not in msg and "Credential" not in msg and "AKIA" not in msg


def test_connection_error_path_redacted():
    exc = requests.ConnectionError("HTTPSConnectionPool(host='archive-lco-global.s3.amazonaws.com', port=443): "
                                   "Max retries exceeded with url: /x/f.fits.fz?X-Amz-Signature=deadbeef (Caused by x)")
    msg = describe_error(exc)
    assert "deadbeef" not in msg and "(Caused by x)" in msg


def test_plain_message_unchanged():
    assert describe_error(RuntimeError("md5 mismatch")) == "RuntimeError: md5 mismatch"
