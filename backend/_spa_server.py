#!/usr/bin/env python
"""
简单的 SPA 静态文件服务器，用于前端验收测试。
- 服务 dist/ 目录下的静态文件
- 对于不存在的文件路径，返回 index.html（SPA fallback）
- 支持 /api/* 反向代理到后端 http://127.0.0.1:8000
"""
import http.server
import socketserver
import urllib.request
import urllib.parse
import os
import sys
from pathlib import Path
from socketserver import ThreadingMixIn

PORT = 4173
DIST_DIR = Path(r"e:\硕腾网络\PyGBSentry\PyGBSentry\editions\open-source\frontend\dist")
BACKEND_URL = "http://127.0.0.1:8000"


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_PUT(self):
        self._handle_request("PUT")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_PATCH(self):
        self._handle_request("PATCH")

    def _handle_request(self, method):
        # 解析路径
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API 请求代理到后端
        if path.startswith("/api/"):
            self._proxy_to_backend(method)
            return

        # 静态文件
        if path == "/" or path == "":
            self._serve_file("index.html")
            return

        # 检查文件是否存在
        file_path = DIST_DIR / path.lstrip("/")
        if file_path.is_file():
            self._serve_file(path.lstrip("/"))
        else:
            # SPA fallback: 所有非文件路径都返回 index.html
            self._serve_file("index.html")

    def _serve_file(self, relative_path):
        file_path = DIST_DIR / relative_path
        if not file_path.is_file():
            self.send_error(404, "File not found")
            return

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            # 根据扩展名设置 Content-Type
            ext = file_path.suffix.lower()
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".ico": "image/x-icon",
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".ttf": "font/ttf",
                ".eot": "application/vnd.ms-fontobject",
                ".map": "application/json",
            }
            content_type = content_types.get(ext, "application/octet-stream")

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Server error: {e}")

    def _proxy_to_backend(self, method):
        """将 API 请求代理到后端"""
        url = f"{BACKEND_URL}{self.path}"

        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # 准备请求头
        headers = {}
        for key, value in self.headers.items():
            if key.lower() in ["host", "content-length", "connection"]:
                continue
            headers[key] = value

        # 创建请求
        req = urllib.request.Request(url, data=body, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                response_body = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() in ["transfer-encoding", "connection"]:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as e:
            response_body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except Exception as e:
            error_msg = str(e).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_msg)))
            self.end_headers()
            self.wfile.write(error_msg)

    def log_message(self, format, *args):
        # 简化日志输出，只记录错误
        if "404" in (format % args) or "500" in (format % args) or "502" in (format % args):
            print(f"[SPA] {format % args}")


class ThreadedSPAServer(ThreadingMixIn, socketserver.TCPServer):
    """多线程 SPA 服务器，避免单线程阻塞"""
    daemon_threads = True
    allow_reuse_address = True


def main():
    if not DIST_DIR.is_dir():
        print(f"ERROR: dist directory not found: {DIST_DIR}")
        sys.exit(1)

    print(f"SPA server starting on port {PORT}")
    print(f"  Serving: {DIST_DIR}")
    print(f"  Backend proxy: {BACKEND_URL}")

    with ThreadedSPAServer(("0.0.0.0", PORT), SPAHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
