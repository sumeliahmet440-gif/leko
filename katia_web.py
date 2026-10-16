# -*- coding: utf-8 -*-
"""
KATIA - Telefon / web arayüzü (iPhone Safari, Android, arkadaşlar için).

Kurulum: pip install flask
Telefon aynı Wi-Fi'deyken:  http://BILGISAYAR_IP:8765
Safari > Paylaş > "Ana Ekrana Ekle" ile uygulama gibi kullanılır.

İki kod vardır:
  owner (sahip)  : her komut (ışık, site açma, WhatsApp...) çalışır
  guest (misafir): sadece sohbet / soru-cevap. PC'yi KONTROL EDEMEZ.
"""
import hmac
import socket
import threading
import time

try:
    from flask import Flask, request, jsonify, Response
    from werkzeug.serving import make_server
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Katia">
<meta name="theme-color" content="__BG__">
<link rel="manifest" href="/manifest.json">
<title>Katia</title>
<style>
:root{--bg:__BG__;--ac:__ACCENT__;--tx:#e8dccb;--dim:#7a7066;--ln:#2e2822}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);font-family:-apple-system,system-ui,Segoe UI,sans-serif}
#app{display:flex;flex-direction:column;height:100%;padding:env(safe-area-inset-top) 12px env(safe-area-inset-bottom)}
header{display:flex;align-items:center;justify-content:space-between;padding:12px 4px;letter-spacing:6px;font-weight:700}
header small{letter-spacing:2px;color:var(--dim);font-weight:400}
#orb{width:64px;height:64px;border-radius:50%;margin:4px auto 8px;background:radial-gradient(circle,var(--ac),transparent 70%);animation:p 3s infinite;opacity:.9}
#orb.on{animation-duration:.8s}
@keyframes p{50%{transform:scale(1.15);opacity:1}}
#log{flex:1;overflow-y:auto;padding:6px 2px;display:flex;flex-direction:column;gap:10px}
.m{max-width:88%;padding:10px 13px;border-radius:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word;font-size:16px}
.me{align-self:flex-end;background:var(--ac);color:#000}
.k{align-self:flex-start;border:1px solid var(--ln);background:#0d0a08}
form{display:flex;gap:8px;padding:10px 0}
input{flex:1;font-size:16px;padding:12px;border-radius:12px;border:1px solid var(--ln);background:#0d0a08;color:var(--tx);outline:none}
button{font-size:18px;border:1px solid var(--ln);background:#0d0a08;color:var(--ac);border-radius:12px;padding:0 14px}
button.s{background:var(--ac);color:#000;font-weight:700}
</style></head><body><div id="app">
<header><span>KATIA</span><small id="role"></small><button id="spk" type="button" title="Sesli cevap">🔊</button></header>
<div id="orb"></div>
<div id="log"></div>
<form id="f"><button id="mic" type="button">🎤</button><input id="t" placeholder="Konuş ya da yaz" autocomplete="off"><button class="s" type="submit">↵</button></form>
</div>
<script>
let token=localStorage.getItem('katia_token')||'';
let speakOn=localStorage.getItem('katia_speak')!=='0';
const log=document.getElementById('log'),orb=document.getElementById('orb'),spk=document.getElementById('spk');
spk.textContent=speakOn?'🔊':'🔇';
spk.onclick=()=>{speakOn=!speakOn;localStorage.setItem('katia_speak',speakOn?'1':'0');spk.textContent=speakOn?'🔊':'🔇';if(!speakOn&&window.speechSynthesis)speechSynthesis.cancel();};
function add(cls,txt){const d=document.createElement('div');d.className='m '+cls;d.textContent=txt;log.appendChild(d);log.scrollTop=log.scrollHeight;}
function speak(t){if(!speakOn||!window.speechSynthesis)return;speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(String(t).replace(/\s+/g,' ').slice(0,400));u.lang='tr-TR';speechSynthesis.speak(u);}
function unlockSpeech(){if(window.speechSynthesis){speechSynthesis.speak(new SpeechSynthesisUtterance(''));}}
async function send(text){
  text=(text||'').trim();if(!text)return;
  if(!token){token=prompt('Giriş kodu')||'';if(!token)return;localStorage.setItem('katia_token',token);}
  add('me',text);orb.classList.add('on');
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify({text})});
    if(r.status===401){localStorage.removeItem('katia_token');token='';add('k','Kod yanlış. Tekrar dene.');}
    else if(r.status===429){add('k','Çok fazla hatalı deneme. Biraz bekle.');}
    else{const j=await r.json();document.getElementById('role').textContent=j.role==='guest'?'MİSAFİR':'SAHİP';add('k',j.reply);speak(j.reply);}
  }catch(e){add('k','Bağlantı hatası: Katia açık mı?');}
  orb.classList.remove('on');
}
document.getElementById('f').onsubmit=e=>{e.preventDefault();unlockSpeech();const i=document.getElementById('t');const v=i.value;i.value='';send(v);};
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
document.getElementById('mic').onclick=()=>{
  unlockSpeech();
  if(!SR){add('k','Mikrofon için sayfanın HTTPS olması ve Safari/Chrome gerekir. Şimdilik yazabilirsin.');return;}
  const r=new SR();r.lang='tr-TR';r.onstart=()=>orb.classList.add('on');r.onend=()=>orb.classList.remove('on');
  r.onresult=e=>send(e.results[0][0].transcript);r.onerror=e=>add('k','Mikrofon hatası: '+e.error);r.start();
};
add('k','Selam! Ben Katia. Yaz ya da 🎤 ile konuş.');
</script></body></html>"""

MANIFEST = ('{"name":"Katia","short_name":"Katia","start_url":"/","display":"standalone",'
            '"background_color":"__BG__","theme_color":"__BG__"}')


class WebServer:
    def __init__(self, cfg, ask_fn):
        self.cfg, self.ask_fn = cfg, ask_fn
        self.srv = None
        self.thread = None
        self.lock = threading.Lock()
        self.fails = {}  # ip -> (sayı, engel_bitişi)

    def start(self):
        if not FLASK_AVAILABLE:
            return False, "Web arayüzü için: pip install flask"
        w = self.cfg.get("web", {})
        owner, guest = w.get("owner", ""), w.get("guest", "")
        port = int(w.get("port", 8765))
        if not owner:
            return False, "Web için sahip kodu boş (AYARLAR > TELEFON/WEB)."
        theme = self.cfg.get("theme", {})
        bg, accent = theme.get("BG", "#050403"), theme.get("ACCENT", "#c9a27a")

        app = Flask(__name__)

        @app.get("/")
        def index():
            return Response(PAGE.replace("__BG__", bg).replace("__ACCENT__", accent), mimetype="text/html")

        @app.get("/manifest.json")
        def manifest():
            return Response(MANIFEST.replace("__BG__", bg), mimetype="application/json")

        @app.post("/api/ask")
        def ask():
            ip = request.remote_addr or "?"
            cnt, until = self.fails.get(ip, (0, 0))
            if until > time.time():
                return jsonify(error="bekle"), 429
            tok = (request.headers.get("X-Token") or "").encode()
            if hmac.compare_digest(tok, owner.encode()):
                role = "owner"
            elif guest and hmac.compare_digest(tok, guest.encode()):
                role = "guest"
            else:
                cnt += 1
                self.fails[ip] = (cnt, time.time() + 60 if cnt >= 5 else 0)
                if cnt >= 5:
                    self.fails[ip] = (0, time.time() + 60)
                return jsonify(error="yetkisiz"), 401
            self.fails.pop(ip, None)
            text = ((request.get_json(silent=True) or {}).get("text") or "").strip()[:1000]
            if not text:
                return jsonify(reply="Bir şey yazmadın.", role=role)
            with self.lock:
                reply = self.ask_fn(text, role)
            return jsonify(reply=reply, role=role)

        try:
            self.srv = make_server("0.0.0.0", port, app, threaded=True)
        except OSError as e:
            return False, f"Web sunucu başlamadı (port {port} dolu olabilir): {e}"
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        return True, f"Telefon adresi: http://{local_ip()}:{port}"

    def stop(self):
        if self.srv:
            try:
                self.srv.shutdown()
            except Exception:
                pass
            self.srv = None
          if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8765))
    app.run(host='0.0.0.0', port=port)
