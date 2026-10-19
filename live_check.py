import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'https://trustartech.com.ng'
CHECKS = [  # (path, expected status, text that must appear)
    ('/', 200, 'Trustar'),
    ('/healthz/', 200, 'ok'),
    ('/accounts/login/', 200, 'Log in'),
    ('/accounts/signup/', 200, 'Create'),
    ('/students/teach/', 200, 'Log in'),         # redirects to login; must not 500
    ('/payments/paystack/webhook/', 405, ''),    # POST-only endpoint, exists after this deploy
]

failures = 0
for path, want_status, want_text in CHECKS:
    try:
        req = urllib.request.Request(BASE + path, headers={'User-Agent': 'trustar-live-check'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, body = resp.status, resp.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        status, body = exc.code, ''
    except Exception as exc:
        print(f"FAIL {path}: {exc}")
        failures += 1
        continue
    ok = status == want_status and want_text in body
    print(('ok   ' if ok else 'FAIL ') + f"{path} -> {status}")
    failures += not ok
sys.exit(1 if failures else 0)