"""REVIEW-2 DB-free toy: does a Flask test-client session set on the default
host reach a request sent with base_url on another host? A stand-in app with
the same gate shape as app.py (host check -> login redirect -> non-admin 403).
It imports neither the Radar app nor models, opens no DB and no socket."""
import flask, werkzeug
from importlib.metadata import version
app = flask.Flask(__name__)
app.secret_key = "toy"
HOST = "mgemmel.viewdns.net"
@app.before_request
def gate():
    if flask.request.host.split(":")[0] != HOST:
        return
    if "user_id" not in flask.session:
        return flask.redirect("/login")
    flask.abort(403)  # the toy user is a non-admin
@app.route("/radar/api/analysis/company/1")
def read():
    return "ok"
@app.route("/login")
def login():
    return "login"
app.config["TESTING"] = True
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user_id"] = 7
    local = c.get("/radar/api/analysis/company/1")
    remote = c.get("/radar/api/analysis/company/1", base_url=f"http://{HOST}")
print("flask", version("flask"), "werkzeug", version("werkzeug"))
print("default host with session:", local.status_code)
print("full-access host via base_url:", remote.status_code, remote.headers.get("Location"))
