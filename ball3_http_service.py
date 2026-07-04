import json
import os
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pylogger as logger


def find_cert(filename):
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, '_internal', filename)
        if os.path.exists(p):
            return p
    p = os.path.join(os.getcwd(), filename)
    if os.path.exists(p):
        return p
    raise RuntimeError(f'Certificate file missing: {filename}')


HTTP_PORT = 9000
HTTPS_PORT = 9001

_start_predict_cb = None
_stop_predict_cb = None
_dispatch_index_cb = None
_save_result_cb = None


def register_ball3_callbacks(start_predict_cb, stop_predict_cb, dispatch_index_cb=None, save_result_cb=None):
    global _start_predict_cb, _stop_predict_cb, _dispatch_index_cb, _save_result_cb
    _start_predict_cb = start_predict_cb
    _stop_predict_cb = stop_predict_cb
    _dispatch_index_cb = dispatch_index_cb
    _save_result_cb = save_result_cb
    logger.info('BALL3 HTTP callbacks registered.')


class Ball3HTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, data, status=200):
        resp = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def _read_data(self, parsed=None):
        if self.command == 'POST':
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except Exception as e:
                logger.warning(f'[BALL3 HTTP] JSON parse failed: {e}')
                return {}
        if self.command == 'GET':
            if parsed is None:
                parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            return {k: v[0] for k, v in params.items() if v}
        return {}

    def do_POST(self):
        self._handle_request()

    def do_GET(self):
        self._handle_request()

    def _handle_request(self):
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_data(parsed)
        gmcode = data.get('gmcode')
        gmstate = data.get('gmstate', 0)
        index = data.get('index', None)
        if gmcode is None:
            self._send_json({'status': 'error', 'msg': 'gmcode missing'}, 400)
            return
        gmcode_resp = gmcode.decode('utf-8', errors='ignore') if isinstance(gmcode, (bytes, bytearray)) else gmcode
        if isinstance(gmcode, str):
            gmcode = gmcode.encode()
        try:
            gmstate = int(gmstate)
        except Exception:
            gmstate = 0
        try:
            index = int(index) if index is not None else None
        except Exception:
            index = None

        if path == '/start_predict':
            logger.info(f'[BALL3 HTTP] start_predict request gmcode={gmcode}, gmstate={gmstate}')
            if _start_predict_cb:
                _start_predict_cb(gmcode, gmstate)
            self._send_json({'status': 'ok', 'action': 'start_predict', 'gmcode': gmcode_resp, 'gmstate': gmstate})
            return

        if path == '/dispatch_index':
            if index is None:
                self._send_json({'status': 'error', 'msg': 'index missing'}, 400)
                return
            logger.info(f'[BALL3 HTTP] dispatch_index request gmcode={gmcode}, index={index}')
            if _dispatch_index_cb:
                _dispatch_index_cb(gmcode, index)
            self._send_json({'status': 'ok', 'action': 'dispatch_index', 'gmcode': gmcode_resp, 'index': index})
            return

        if path == '/save_result':
            logger.info(f'[BALL3 HTTP] save_result request gmcode={gmcode}')
            if _save_result_cb:
                _save_result_cb(gmcode)
            self._send_json({'status': 'ok', 'action': 'save_result', 'gmcode': gmcode_resp})
            return

        if path == '/stop_predict':
            logger.info(f'[BALL3 HTTP] stop_predict request gmcode={gmcode}, gmstate={gmstate}')
            if _stop_predict_cb:
                _stop_predict_cb(gmcode, gmstate)
            self._send_json({'status': 'ok', 'action': 'stop_predict', 'gmcode': gmcode_resp, 'gmstate': gmstate})
            return

        self._send_json({'status': 'error', 'msg': f'unknown path {path}'}, 404)


def start_ball3_http_service(http_port=None, https_port=None):
    http_port = http_port or HTTP_PORT
    https_port = https_port or HTTPS_PORT
    http_server = HTTPServer(('0.0.0.0', http_port), Ball3HTTPRequestHandler)
    logger.info(f'[BALL3 HTTP] HTTP server started: http://127.0.0.1:{http_port}')

    def run_http():
        http_server.serve_forever()

    threading.Thread(target=run_http, daemon=True, name='ball3_http_server').start()

    try:
        crt = find_cert('server.crt')
        key = find_cert('server.key')
        logger.info(f'[BALL3 HTTP] Using cert: {crt}')
        logger.info(f'[BALL3 HTTP] Using key: {key}')
        https_server = HTTPServer(('0.0.0.0', https_port), Ball3HTTPRequestHandler)
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(crt, key)
        https_server.socket = ssl_ctx.wrap_socket(https_server.socket, server_side=True)
        logger.info(f'[BALL3 HTTP] HTTPS server started: https://127.0.0.1:{https_port}')

        def run_https():
            https_server.serve_forever()

        threading.Thread(target=run_https, daemon=True, name='ball3_https_server').start()
    except Exception as e:
        logger.warning(f'[BALL3 HTTP] HTTPS not started: {e}')
