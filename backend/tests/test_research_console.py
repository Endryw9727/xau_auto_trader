"""Backend tests for Research Console API (read-only external proxy contract).

Contract under test (iteration 4):
- All synthetic/mock generation has been REMOVED.
- /api/instruments and /api/edge/* and /api/bot/* are pure read-only proxies
  to the external API_BASE_URL. If the external API is unreachable they
  MUST return HTTP 503 with detail 'API OFFLINE — nessun dato' and never
  fall back to synthetic data.
- Endpoints /api/data/synthetic, /api/data/upload-csv, /api/data/fetch-yahoo
  have been removed entirely and MUST return 404/405.
- The hard safety constraint (live_armed=false, allow_real_live=false) is
  immutable and there is no arming endpoint.
"""
import os
import uuid
import pytest
import requests

OFFLINE_DETAIL = "API OFFLINE — nessun dato"
OFFLINE_COMBOS = {"HIGH_VOL", "LOW_VOL", "RANGE", "TREND_UP", "BREAKOUT", "MEAN_REVERSION"}

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break


def _env_from_backend(key: str, default: str = "") -> str:
    val = os.environ.get(key)
    if val:
        return val
    try:
        with open("/app/backend/.env") as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        pass
    return default


ADMIN_EMAIL = _env_from_backend("ADMIN_EMAIL", "admin@research.console")
ADMIN_PASSWORD = _env_from_backend("ADMIN_PASSWORD")
assert ADMIN_PASSWORD, "ADMIN_PASSWORD must be set in environment or /app/backend/.env"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def external_reachable(api):
    """Detect whether the external API is reachable. If not, data endpoints
    must return 503 — that is the PASS condition under the new contract."""
    r = api.get(f"{BASE_URL}/api/health")
    return bool(r.status_code == 200 and r.json().get("external_api_reachable"))


def _assert_offline(resp):
    assert resp.status_code == 503, f"expected 503 OFFLINE, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body.get("detail") == OFFLINE_DETAIL, f"unexpected detail: {body}"


def _no_invented_combos(payload):
    """Walk JSON looking for any invented combo string the app must not produce."""
    if isinstance(payload, dict):
        for v in payload.values():
            _no_invented_combos(v)
    elif isinstance(payload, list):
        for v in payload:
            _no_invented_combos(v)
    elif isinstance(payload, str):
        assert payload not in OFFLINE_COMBOS, f"invented combo leaked: {payload}"


# ---------- health / safety ----------
class TestPublic:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("live_armed") is False
        assert "external_api_reachable" in data, "health must expose external_api_reachable"
        assert isinstance(data["external_api_reachable"], bool)

    def test_safety(self, api):
        r = api.get(f"{BASE_URL}/api/safety")
        assert r.status_code == 200
        data = r.json()
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False
        assert data["read_only"] is True

    def test_instruments_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/instruments")
        assert r.status_code == 401


# ---------- auth ----------
class TestAuth:
    def test_login_success(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body and isinstance(body["token"], str)
        assert body["user"]["email"] == ADMIN_EMAIL
        assert body["user"]["role"] == "admin"

    def test_login_wrong_password(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": "wrong-pass-xxx"})
        assert r.status_code == 401

    def test_me_with_bearer(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token(self):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_self_register(self, api):
        email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
        r = api.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "Pass1234!", "name": "TEST User"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "token" in body
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "analyst"


# ---------- httpOnly cookie auth ----------
class TestCookieAuth:
    def test_login_sets_httponly_cookie(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "access_token" in s.cookies
        set_cookie = r.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie

    def test_logout_clears_cookie(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert s.get(f"{BASE_URL}/api/auth/me").status_code == 200
        lr = s.post(f"{BASE_URL}/api/auth/logout")
        assert lr.status_code in (200, 204)
        r = s.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401


# ---------- instruments: external-only, offline=503 ----------
class TestInstruments:
    def test_instruments(self, auth_headers, external_reachable):
        r = requests.get(f"{BASE_URL}/api/instruments", headers=auth_headers)
        if not external_reachable:
            _assert_offline(r)
            return
        # If external is online: must be 200, must not contain TESTSYN*/TEST_CSV
        assert r.status_code == 200, r.text
        data = r.json()
        assert "instruments" in data
        symbols = [i.get("symbol", "") for i in data["instruments"]]
        for s in symbols:
            assert not s.startswith("TESTSYN"), f"TESTSYN* leaked: {s}"
            assert s != "TEST_CSV", "TEST_CSV leaked"


# ---------- REMOVED endpoints must be 404/405 ----------
class TestRemovedDataEndpoints:
    def test_synthetic_removed(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/data/synthetic", headers=auth_headers,
                          json={"symbol": "TESTSYNX", "rows": 50})
        assert r.status_code in (404, 405), f"expected 404/405, got {r.status_code}"

    def test_upload_csv_removed(self, admin_token):
        files = {"file": ("TEST_CSV.csv", "Date,Open,High,Low,Close,Volume\n", "text/csv")}
        r = requests.post(f"{BASE_URL}/api/data/upload-csv",
                          headers={"Authorization": f"Bearer {admin_token}"}, files=files)
        assert r.status_code in (404, 405), f"expected 404/405, got {r.status_code}"

    def test_fetch_yahoo_removed(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/data/fetch-yahoo", headers=auth_headers,
                          json={"symbol": "XAUUSD"})
        assert r.status_code in (404, 405), f"expected 404/405, got {r.status_code}"


# ---------- edge lab: offline=503, no invented combos ----------
class TestEdgeLab:
    @pytest.mark.parametrize("path", [
        "/api/edge/session-scan", "/api/edge/ny-conditional",
        "/api/edge/overnight", "/api/edge/significance-audit",
    ])
    def test_edge_offline_or_no_invented(self, auth_headers, external_reachable, path):
        r = requests.post(f"{BASE_URL}{path}", headers=auth_headers,
                          json={"symbols": ["XAUUSD"]}, timeout=60)
        if not external_reachable:
            _assert_offline(r)
            return
        assert r.status_code == 200, r.text
        _no_invented_combos(r.json())


# ---------- bot diagnostics: offline=503, no invented combos ----------
class TestBot:
    @pytest.mark.parametrize("path", [
        "/api/bot/rejection-taxonomy", "/api/bot/market-structure",
        "/api/bot/quality-review", "/api/bot/demo-readiness",
    ])
    def test_bot_offline_or_no_invented(self, auth_headers, external_reachable, path):
        r = requests.get(f"{BASE_URL}{path}", headers=auth_headers)
        if not external_reachable:
            _assert_offline(r)
            return
        assert r.status_code == 200, r.text
        _no_invented_combos(r.json())


# ---------- safety constraint ----------
class TestSafetyConstraint:
    def test_no_arm_endpoint(self, auth_headers):
        for path in ("/api/arm", "/api/live/arm", "/api/safety/arm", "/api/live-arm"):
            r = requests.post(f"{BASE_URL}{path}", headers=auth_headers,
                              json={"allow_real_live": True})
            assert r.status_code in (404, 405)

    def test_safety_immutable(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/safety", headers=auth_headers,
                          json={"live_armed": True, "allow_real_live": True})
        assert r.status_code in (404, 405)
        r2 = requests.get(f"{BASE_URL}/api/safety")
        assert r2.json()["live_armed"] is False
        assert r2.json()["allow_real_live"] is False


# ---------- AI Research (real LLM, report-only) ----------
class TestAI:
    def test_ai_config(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/config", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["report_only"] is True
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False
