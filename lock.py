#!/usr/bin/env python3
"""Password-lock a built page: replace index.html with an encrypted copy plus a small unlock screen.

The page is gzipped, then encrypted with AES-256-GCM under a key derived from the password with
PBKDF2-HMAC-SHA256 (600,000 rounds). The browser derives the same key with WebCrypto, decrypts,
and writes the page in place. The password never leaves the browser. A fixed, non-secret salt keeps
the "remember me" key valid across daily rebuilds.

    SITE_PASSWORD=... python lock.py site/index.html

This keeps casual visitors out. The encrypted file is still public, so use a long passphrase.
"""
import base64, gzip, hashlib, os, sys

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITERATIONS = 600_000
SALT = bytes.fromhex("ef23a73a4e8aba5c17aaad4c96297e7c")
MIN_LENGTH = 12
REMEMBER_DAYS = 30
MARKER = "desk-locked-page"

STUB = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Rachit’s Market Lens</title><style>
:root{--bg:#0a0a0a;--panel:#141414;--line:#262626;--ink:#f2f2ee;--mut:#8b8b86;--r:#ef5a4d;--am:#e8a93a}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding:16px}
form{width:100%;max-width:340px;background:var(--panel);border-top:3px solid #f4f4f0;padding:22px}
h1{margin:0 0 4px;font-size:15px;letter-spacing:.11em}p{margin:0 0 16px;color:var(--mut);font-size:12px}
input[type=password]{width:100%;background:#0d0d0d;color:var(--ink);border:1px solid #333;padding:11px 10px;font:600 14px ui-monospace,Menlo,Consolas,monospace;border-radius:3px}
input[type=password]:focus-visible,button:focus-visible{outline:2px solid var(--am);outline-offset:2px}
label{display:flex;gap:8px;align-items:center;margin:12px 0;color:var(--mut);font-size:12px}
button{width:100%;background:#f4f4f0;color:#0a0a0a;border:0;padding:11px;font:700 12px inherit;letter-spacing:.08em;cursor:pointer;border-radius:3px}
button:disabled{opacity:.6;cursor:wait}#err{min-height:18px;margin-top:10px;color:var(--r);font-size:12px}
</style></head><body><form id="f"><h1>RACHIT’S MARKET LENS</h1><p>Enter the password to open the desk.</p>
<input id="pw" type="password" autocomplete="current-password" placeholder="Password" aria-label="Password" autofocus required>
<label><input id="rm" type="checkbox" checked> Remember on this device for __DAYS__ days</label>
<button id="go" type="submit">OPEN</button><div id="err" role="alert"></div></form>
<script>
const P="__PAYLOAD__",SALT="__SALT__",IT=__ITER__,DAYS=__DAYS__,KEY="desk-lock-key";
const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0)),hex=s=>Uint8Array.from(s.match(/../g),h=>parseInt(h,16));
const err=m=>{document.getElementById("err").textContent=m};
async function decrypt(key){
  const raw=b64(P),iv=raw.slice(0,12),buf=await crypto.subtle.decrypt({name:"AES-GCM",iv},key,raw.slice(12));
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).text()}
function show(html){document.open();document.write(html);document.close()}
async function derive(pw){
  const km=await crypto.subtle.importKey("raw",new TextEncoder().encode(pw),"PBKDF2",false,["deriveKey"]);
  return crypto.subtle.deriveKey({name:"PBKDF2",salt:hex(SALT),iterations:IT,hash:"SHA-256"},km,{name:"AES-GCM",length:256},true,["decrypt"])}
(async()=>{
  if(!window.crypto||!crypto.subtle||typeof DecompressionStream==="undefined"){err("This browser cannot unlock the page. Use a current Chrome, Safari, Edge or Firefox over https.");return}
  try{const s=JSON.parse(localStorage.getItem(KEY)||"null");
    if(s&&s.exp>Date.now()){let html=null;try{html=await decrypt(await crypto.subtle.importKey("raw",b64(s.k),"AES-GCM",false,["decrypt"]))}catch(e){localStorage.removeItem(KEY)}
      if(html!==null){show(html);return}}}catch(e){}
  document.getElementById("f").onsubmit=async e=>{e.preventDefault();const go=document.getElementById("go");go.disabled=true;err("");
    let html=null;
    try{const key=await derive(document.getElementById("pw").value);
      try{html=await decrypt(key)}catch(x){err("Wrong password.");go.disabled=false;return}
      if(document.getElementById("rm").checked){try{localStorage.setItem(KEY,JSON.stringify({k:btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.exportKey("raw",key)))),exp:Date.now()+DAYS*864e5}))}catch(x){}}
    }catch(x){err("Could not unlock the page.");go.disabled=false;return}
    show(html)}})();
</script></body></html>"""


def lock_html(html, password, salt=SALT, iterations=ITERATIONS):
    """Return the encrypted stand-in page for `html`."""
    if len(password) < MIN_LENGTH: raise ValueError(f"password must be at least {MIN_LENGTH} characters")
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    iv = os.urandom(12)
    payload = base64.b64encode(iv + AESGCM(key).encrypt(iv, gzip.compress(html.encode("utf-8"), 9, mtime=0), None)).decode()
    return (STUB.replace("__PAYLOAD__", payload).replace("__SALT__", salt.hex())
            .replace("__ITER__", str(iterations)).replace("__DAYS__", str(REMEMBER_DAYS)))


def main(path):
    password = os.environ.get("SITE_PASSWORD", "")
    if not password:
        sys.exit("SITE_PASSWORD is not set: add it as a repository secret (Settings > Secrets and variables > Actions).")
    html = open(path, encoding="utf-8").read()
    if "<!-- " + MARKER in html: sys.exit(f"{path} is already locked.")
    try: locked = lock_html(html, password)
    except ValueError as e: sys.exit(str(e))
    if "MARKET LENS" in locked.replace("RACHIT’S MARKET LENS", "") or "market_cap" in locked:
        sys.exit("locked page still contains readable page content; refusing to publish it")
    open(path, "w", encoding="utf-8").write(locked.replace("<head>", "<head><!-- " + MARKER + " -->", 1))
    csv = os.path.join(os.path.dirname(path), "corporate_actions.csv")
    if os.path.exists(csv): os.remove(csv)                  # an audit log that would otherwise stay public
    print(f"locked {path}: {len(html) / 1e6:.1f} MB page, {os.path.getsize(path) / 1e6:.1f} MB encrypted")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "index.html"))
