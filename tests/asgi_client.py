"""Minimal ASGI test client (httpx is not available offline). Keeps cookies; follow_redirects optional."""
import asyncio
import urllib.parse
from http.cookies import SimpleCookie


class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.text = status, headers, body.decode("utf-8", "replace")
        self.body = body


class Client:
    def __init__(self, app):
        self.app, self.cookies = app, {}

    def request(self, method, url, data=None, headers=None, follow=False, files=None):
        u = urllib.parse.urlsplit(url)
        body = urllib.parse.urlencode(data or {}, doseq=True).encode()
        boundary = None
        if files:    # files = {field: (filename, bytes, content_type)}
            boundary = "----compasstest"
            parts = []
            for k, v in (data or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for k, (fn, content, ctype) in files.items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + content + b"\r\n")
            body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        hdrs["host"] = "testserver"
        if self.cookies:
            hdrs["cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if method == "POST":
            hdrs["content-type"] = f"multipart/form-data; boundary={boundary}" if boundary else "application/x-www-form-urlencoded"
        hdrs["content-length"] = str(len(body))
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http", "path": u.path,
                 "raw_path": u.path.encode(), "query_string": u.query.encode(), "headers": [(k.encode(), v.encode()) for k, v in hdrs.items()],
                 "server": ("testserver", 80), "client": ("127.0.0.1", 1), "root_path": ""}
        out = {"status": 0, "headers": {}, "body": b""}

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(m):
            if m["type"] == "http.response.start":
                out["status"] = m["status"]
                for k, v in m["headers"]:
                    k = k.decode().lower()
                    if k == "set-cookie":
                        c = SimpleCookie(v.decode())
                        for name, morsel in c.items():
                            if morsel.value in ("", "null") or morsel["max-age"] == "0":
                                self.cookies.pop(name, None)
                            else:
                                self.cookies[name] = morsel.value
                    out["headers"][k] = v.decode()
            elif m["type"] == "http.response.body":
                out["body"] += m.get("body", b"")

        asyncio.run(self.app(scope, receive, send))
        r = Resp(out["status"], out["headers"], out["body"])
        if follow and r.status in (301, 302, 303, 307) and "location" in r.headers:
            return self.request("GET", r.headers["location"], follow=True)
        return r

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, data=None, **kw):
        return self.request("POST", url, data=data, **kw)
