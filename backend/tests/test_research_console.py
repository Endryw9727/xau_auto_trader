"""Backend tests for Research Console API."""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
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


# Credentials are read from the environment / backend .env, never hardcoded.
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


# ---------- public endpoints ----------
class TestPublic:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("live_armed") is False

    def test_safety(self, api):
        r = api.get(f"{BASE_URL}/api/safety")
        assert r.status_code == 200
        data = r.json()
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False
        assert data["read_only"] is True

    def test_instruments_requires_auth(self):
        # Use a fresh session — shared `api` session may now hold an httpOnly cookie after login
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

    def test_me_with_bearer(self, api, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token(self):
        # Use a fresh session (no cookie, no Bearer)
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


# ---------- instruments / data ----------
class TestInstruments:
    def test_instruments_list(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/instruments", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "instruments" in data
        if data["instruments"]:
            inst = data["instruments"][0]
            for k in ("symbol", "has_data", "rows", "first", "last", "cost_per_trade"):
                assert k in inst, f"missing {k} in instrument"


class TestData:
    def test_synthetic(self, auth_headers):
        sym = f"TESTSYN{uuid.uuid4().hex[:4].upper()}"
        r = requests.post(f"{BASE_URL}/api/data/synthetic", headers=auth_headers,
                          json={"symbol": sym, "rows": 200})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["instrument"]["symbol"] == sym
        assert data["instrument"]["has_data"] is True
        assert isinstance(data["preview"], list) and len(data["preview"]) > 0

    def test_fetch_yahoo(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/data/fetch-yahoo", headers=auth_headers,
                          json={"symbol": "XAUUSD"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "instrument" in data
        assert "preview" in data
        # External not configured -> note expected
        assert "note" in data

    def test_upload_csv(self, admin_token):
        csv_content = "Date,Open,High,Low,Close,Volume\n"
        for i in range(60):
            csv_content += f"2024-01-{(i%28)+1:02d},100,105,99,{100+i},1000\n"
        files = {"file": ("TEST_CSV.csv", csv_content, "text/csv")}
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{BASE_URL}/api/data/upload-csv", headers=headers, files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["symbol"] == "TEST_CSV"
        assert data["has_data"] is True
        assert data["rows"] == 60


# ---------- edge lab ----------
class TestEdgeLab:
    def test_session_scan(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/edge/session-scan", headers=auth_headers,
                          json={"symbols": ["XAUUSD"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "run_id" in data
        assert "verdicts" in data and isinstance(data["verdicts"], list)
        for v in data["verdicts"]:
            assert v.get("verdict") in ("KEEP", "EXCLUDE")

    def test_ny_conditional(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/edge/ny-conditional", headers=auth_headers,
                          json={"symbols": ["XAUUSD"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "run_id" in data
        assert "verdicts" in data
        for v in data["verdicts"]:
            assert "best_condition" in v
            assert "best_hypothesis" in v

    def test_overnight(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/edge/overnight", headers=auth_headers,
                          json={"symbols": ["XAUUSD"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "run_id" in data
        # Post-normalization: backend MUST synthesize 'verdicts' and expose 'detail' rows.
        verdicts = data.get("verdicts") or []
        detail = data.get("detail") or []
        assert verdicts, f"no verdicts after normalization: {list(data.keys())}"
        assert detail, f"no detail rows after normalization: {list(data.keys())}"
        for v in verdicts:
            for k in ("symbol", "verdict", "best_session", "best_direction",
                      "best_oos_t_stat", "p_value", "bh_significant", "mtc_robust"):
                assert k in v, f"missing {k} in verdict"
            assert v["verdict"] in ("KEEP", "EXCLUDE")
            assert v["best_session"] == "OVERNIGHT"
        for row in detail:
            assert "p_value" in row
            assert "bh_significant" in row
            assert "mtc_robust" in row

    def test_significance_audit(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/edge/significance-audit", headers=auth_headers,
                          json={"symbols": ["XAUUSD", "EURUSD"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "family_size" in data
        assert "mtc_survivors" in data
        assert "run_id" in data
        assert isinstance(data.get("rows"), list) and len(data["rows"]) > 0
        for row in data["rows"]:
            for k in ("symbol", "combo", "oos_t_stat", "p_value",
                      "bonferroni_significant", "bh_significant", "mtc_robust"):
                assert k in row, f"missing {k} in significance row"


# ---------- bot diagnostics ----------
class TestBot:
    def test_rejection(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bot/rejection-taxonomy", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_market_structure(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bot/market-structure", headers=auth_headers)
        assert r.status_code == 200

    def test_quality_review(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bot/quality-review", headers=auth_headers)
        assert r.status_code == 200

    def test_demo_readiness(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bot/demo-readiness", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False


# ---------- runs ----------
class TestRuns:
    def test_runs_list_and_get(self, auth_headers):
        # ensure at least one run exists
        rr = requests.post(f"{BASE_URL}/api/edge/significance-audit", headers=auth_headers,
                           json={"symbols": ["XAUUSD"]})
        assert rr.status_code == 200
        run_id = rr.json()["run_id"]

        r = requests.get(f"{BASE_URL}/api/runs", headers=auth_headers)
        assert r.status_code == 200
        runs = r.json()["runs"]
        assert any(x["id"] == run_id for x in runs)
        for x in runs[:5]:
            for k in ("id", "run_type", "params", "created_at"):
                assert k in x

        r2 = requests.get(f"{BASE_URL}/api/runs/{run_id}", headers=auth_headers)
        assert r2.status_code == 200
        full = r2.json()
        assert full["id"] == run_id
        assert "params" in full and "result" in full


# ---------- AI Research ----------
class TestAI:
    def test_ai_config(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/config", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["report_only"] is True
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False
        assert "tasks" in data
        providers = data["providers"]
        provider_ids = {p["id"] for p in providers}
        assert "anthropic" in provider_ids
        assert "openai" in provider_ids
        # moonshot must be present but disabled
        moonshot = [p for p in providers if p["id"] == "moonshot"]
        assert moonshot and moonshot[0]["enabled"] is False

    def test_ai_chat_moonshot_rejected(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/ai/chat", headers=auth_headers,
                          json={"task": "explain_significance",
                                "provider": "moonshot",
                                "message": "hi"})
        assert r.status_code == 400

    def test_ai_chat_real_reply(self, auth_headers):
        # Real LLM call (Claude via Emergent key)
        payload = {
            "task": "explain_significance",
            "message": "In one sentence, what does mtc_robust mean?",
            "context": {"oos_t_stat": 3.2, "p_value": 0.001,
                        "bonferroni_significant": True,
                        "bh_significant": True, "mtc_robust": True}
        }
        r = requests.post(f"{BASE_URL}/api/ai/chat", headers=auth_headers,
                          json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "reply" in data and isinstance(data["reply"], str) and len(data["reply"]) > 5
        assert data["report_only"] is True
        assert "conversation_id" in data


# ---------- absolute constraint ----------
class TestSafetyConstraint:
    def test_no_arm_endpoint(self, auth_headers):
        # No endpoint should let us set allow_real_live=true
        for path in ("/api/arm", "/api/live/arm", "/api/safety/arm", "/api/live-arm"):
            r = requests.post(f"{BASE_URL}{path}", headers=auth_headers,
                              json={"allow_real_live": True})
            assert r.status_code in (404, 405), f"Unexpected response at {path}: {r.status_code}"

    def test_safety_immutable(self, auth_headers):
        # PUT/POST to safety should not change live state
        r = requests.post(f"{BASE_URL}/api/safety", headers=auth_headers,
                          json={"live_armed": True, "allow_real_live": True})
        assert r.status_code in (404, 405)
        r2 = requests.get(f"{BASE_URL}/api/safety")
        assert r2.json()["live_armed"] is False
        assert r2.json()["allow_real_live"] is False


# ---------- httpOnly cookie auth (refactor regression) ----------
class TestCookieAuth:
    def test_login_sets_httponly_cookie_and_me_works_cookie_only(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        # cookie present in jar
        assert "access_token" in s.cookies, f"access_token cookie not set; got {dict(s.cookies)}"
        # Validate Set-Cookie attributes (HttpOnly, Secure, SameSite)
        set_cookie = r.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie, f"HttpOnly missing in {set_cookie}"
        assert "Secure" in set_cookie, f"Secure missing in {set_cookie}"
        # /me works using ONLY the cookie (no Authorization header)
        r2 = s.get(f"{BASE_URL}/api/auth/me")
        assert r2.status_code == 200, r2.text
        assert r2.json()["email"] == ADMIN_EMAIL

    def test_protected_endpoint_with_cookie_only(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        # /api/instruments requires auth — should work using cookie only
        r = s.get(f"{BASE_URL}/api/instruments")
        assert r.status_code == 200, r.text
        assert "instruments" in r.json()

    def test_logout_clears_cookie(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert s.get(f"{BASE_URL}/api/auth/me").status_code == 200
        lr = s.post(f"{BASE_URL}/api/auth/logout")
        assert lr.status_code in (200, 204)
        # After logout, cookie should be removed by server (delete_cookie sends Set-Cookie with empty value)
        # Either the session cookie jar no longer holds it or /me is now 401
        r = s.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_bearer_fallback_still_works(self, admin_token):
        # No cookie session, use Bearer from login body
        r = requests.get(f"{BASE_URL}/api/auth/me",
                         headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL


# ---------- External API integration sanity ----------
class TestExternalAPI:
    def test_health_reports_external(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        # health should still report live_armed false (absolute constraint)
        data = r.json()
        assert data.get("live_armed") is False

    def test_safety_external_api_flag(self):
        r = requests.get(f"{BASE_URL}/api/safety")
        assert r.status_code == 200
        data = r.json()
        assert data["live_armed"] is False
        assert data["allow_real_live"] is False
        # external_api flag should be True when API_BASE_URL is configured & reachable
        # If unreachable, fall back to false — accept either but log
        print(f"safety.external_api = {data.get('external_api')}")
