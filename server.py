from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, msg):
        self.send_response(code)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self):
        if self.path == "/":
            self._send(200, "OK - Amazon Bot Online.")
        elif self.path == "/run":
            self._send(200, "Esecuzione avviata.")
            subprocess.Popen(["python", "bot.py"])
        else:
            self._send(404, "Not Found")

def start():
    PORT = 10000
    server = HTTPServer(("", PORT), Handler)
    print(f"[SERVER] Attivo sulla porta {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    start()
