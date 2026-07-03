"""app.py Origin 차단(CSRF 방어) 단위 테스트."""
from backend.app import origin_allowed


def test_origin_none_allowed():
    # CEP 패널(file:// 출신)은 Origin 헤더가 없음 → 허용
    assert origin_allowed(None) is True


def test_origin_null_allowed():
    assert origin_allowed("null") is True


def test_origin_file_allowed():
    assert origin_allowed("file:///Users/x/panel") is True


def test_origin_http_blocked():
    # 브라우저 웹페이지(교차 출처) → 차단
    assert origin_allowed("http://evil.example") is False
    assert origin_allowed("http://127.0.0.1:8765") is False
    assert origin_allowed("https://attacker.test") is False
