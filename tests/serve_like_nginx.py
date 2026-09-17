"""Serve the app the way the live server does, for the browser audits.

Run: python3 tests/serve_like_nginx.py          (foreground, port 8032)

On the live server nginx serves app.html and forwards only a fixed list
of API path prefixes to the application; anything else falls through to
the frontend and a POST to it comes back 405. That rule has broken this
app twice - once for /purchase/ and once for /view/ - because both were
invented as new prefixes and never added to nginx.

So the audits run behind a copy of that rule rather than against the
application directly. A call to a prefix nginx does not know fails here
exactly as it would in production, before anyone notices it live.
"""
import http.server, socketserver, subprocess, sys, os, time, threading
import urllib.request, urllib.error

PORT = 8032
API_PORT = 8033

# The prefixes nginx forwards. Keep this in step with the server config -
# a new endpoint outside these paths will not reach the application.
API_PREFIXES = ("/auth/", "/employees", "/sites", "/engineers", "/attendance/",
                "/live-card/", "/adjustments/", "/summaries/", "/reports/",
                "/export/", "/store/", "/backup/", "/users", "/notifications",
                "/error-check/", "/permissions/", "/settings/", "/health")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, *a):
        pass

    def _is_api(self):
        return any(self.path.startswith(p) for p in API_PREFIXES)

    def _proxy(self, body=None):
        url = f"http://127.0.0.1:{API_PORT}{self.path}"
        req = urllib.request.Request(url, data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "connection"):
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_GET(self):
        if self._is_api():
            return self._proxy()
        return super().do_GET()

    def _with_body(self):
        if not self._is_api():
            # Exactly what the live server does with an unknown prefix:
            # the static site answers, and a POST to a page is refused.
            self.send_response(405)
            self.end_headers()
            self.wfile.write(b"405 - this path is not forwarded to the API")
            return
        n = int(self.headers.get("Content-Length") or 0)
        self._proxy(self.rfile.read(n) if n else None)

    do_POST = do_PUT = do_PATCH = do_DELETE = lambda self: Handler._with_body(self)


def main():
    env = dict(os.environ)
    env.setdefault("DATABASE_URL", "sqlite:////tmp/audit_app.db")
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app",
                            "--port", str(API_PORT), "--log-level", "warning"],
                           cwd=os.path.join(ROOT, "app"), env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        api.kill()
        sys.exit("the application did not come up")

    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"serving like the live server on http://127.0.0.1:{PORT}/app.html", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        api.terminate()


if __name__ == "__main__":
    main()
