"""Decoy-страница для браузеров — тот же лес с фонариком, что был в вашем
Cloudflare Worker. VPN-клиенты её никогда не видят (см. is_vpn_client в
api.py) — она нужна только чтобы человек, зашедший по ссылке подписки
в обычном браузере, не понял, есть ли вообще такой токен в базе."""

DECOY_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>500 — Internal Server Error</title>
<style>
  :root{{
    --bg-deep:#080f0c;
    --fog:#cddccb;
    --amber:#d9a441;
    --err:#e5484d;
    --tg:#2ea6e6;
    --x:50%;
    --y:40%;
  }}
  *{{ box-sizing:border-box; }}
  html,body{{
    margin:0; padding:0; height:100%; overflow:hidden;
    background:var(--bg-deep);
    font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  }}
  .scene{{ position:fixed; inset:0; cursor:none; }}
  .forest{{ position:absolute; inset:0; filter: saturate(0.7); }}
  .forest svg{{ width:100%; height:100%; display:block; }}
  .forest-lit{{
    position:absolute; inset:0;
    -webkit-mask-image: radial-gradient(circle 190px at var(--x) var(--y), #000 0%, #000 35%, transparent 78%);
    mask-image: radial-gradient(circle 190px at var(--x) var(--y), #000 0%, #000 35%, transparent 78%);
  }}
  .forest-lit svg{{ width:100%; height:100%; display:block; }}
  .torch-glow{{
    position:absolute; inset:0; pointer-events:none;
    background: radial-gradient(circle 220px at var(--x) var(--y),
                rgba(255,224,168,0.10) 0%, rgba(255,224,168,0.04) 40%, transparent 72%);
    mix-blend-mode: screen;
  }}
  .vignette{{
    position:absolute; inset:0; pointer-events:none;
    background: radial-gradient(ellipse at center, transparent 40%, rgba(4,8,6,0.75) 100%);
  }}
  .torch-cursor{{
    position:fixed; left:0; top:0; width:34px; height:34px;
    margin-left:-17px; margin-top:-17px; border-radius:50%;
    border:1px solid rgba(255,224,168,0.55);
    box-shadow: 0 0 18px 4px rgba(255,224,168,0.25), inset 0 0 12px rgba(255,224,168,0.35);
    pointer-events:none; z-index:40;
  }}
  .tg-btn{{
    position:fixed; top:22px; left:50%; transform:translateX(-50%); z-index:50;
    display:flex; align-items:center; gap:9px; padding:10px 18px 10px 14px;
    background:rgba(10,16,13,0.72); border:1px solid rgba(205,220,203,0.18);
    border-radius:999px; backdrop-filter: blur(6px); color:var(--fog);
    text-decoration:none; font-size:13px;
  }}
  .tg-btn:hover{{ border-color: rgba(46,166,230,0.6); background: rgba(10,16,13,0.9); }}
  .tg-btn svg{{ width:18px; height:18px; flex-shrink:0; }}
  .tg-btn .dot{{
    width:6px; height:6px; border-radius:50%; background:var(--tg);
    box-shadow:0 0 6px 1px rgba(46,166,230,0.7);
  }}
  .err-card{{
    position:fixed; left:50%; top:50%; transform:translate(-50%,-50%); z-index:45;
    width:min(430px, 86vw); background:rgba(9,14,11,0.82);
    border:1px solid rgba(229,72,77,0.35); border-radius:14px;
    padding:22px 24px 20px; backdrop-filter: blur(8px);
    box-shadow: 0 20px 60px rgba(0,0,0,0.55);
  }}
  .err-head{{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
  .err-icon{{ width:20px; height:20px; flex-shrink:0; color:var(--err); }}
  .err-code{{ font-size:15px; letter-spacing:0.06em; color:var(--err); text-transform:uppercase; }}
  .err-msg{{ color:var(--fog); font-size:13px; line-height:1.6; opacity:0.85; margin:0; }}
  .err-path{{
    margin-top:12px; padding-top:12px; border-top:1px dashed rgba(205,220,203,0.15);
    font-size:11.5px; color:rgba(205,220,203,0.55); word-break:break-all;
  }}
  .hint{{
    position:fixed; bottom:20px; left:50%; transform:translateX(-50%); z-index:45;
    font-size:11px; letter-spacing:0.08em; text-transform:uppercase;
    color:rgba(205,220,203,0.35);
  }}
  @media (max-width:520px){{ .torch-cursor{{ display:none; }} .scene{{ cursor:auto; }} }}
</style>
</head>
<body>
<div class="scene" id="scene">
  <div class="forest">
    <svg viewBox="0 0 1200 700" preserveAspectRatio="xMidYMax slice">
      <defs>
        <radialGradient id="skyGrad" cx="50%" cy="20%" r="80%">
          <stop offset="0%" stop-color="#16241c"/>
          <stop offset="100%" stop-color="#080f0c"/>
        </radialGradient>
      </defs>
      <rect x="0" y="0" width="1200" height="700" fill="url(#skyGrad)"/>
      <circle cx="960" cy="120" r="46" fill="#e9edcf" opacity="0.35"/>
      <g fill="#0d1712" opacity="0.9">
        <polygon points="0,700 0,430 40,470 70,400 100,460 140,390 170,450 210,410 240,700"/>
        <polygon points="700,700 700,440 740,480 780,410 820,470 860,400 900,460 940,410 980,700"/>
      </g>
      <rect x="0" y="640" width="1200" height="60" fill="#050a07"/>
      <g transform="translate(560,470)" fill="#120c08">
        <path d="M0 220 C -10 210 -22 205 -20 185 L -18 150 C -46 148 -70 130 -78 100 C -84 78 -78 56 -60 44 C -66 30 -64 12 -50 4 C -38 -4 -22 0 -16 10 C -6 4 6 4 16 10 C 22 0 38 -4 50 4 C 64 12 66 30 60 44 C 78 56 84 78 78 100 C 70 130 46 148 18 150 L 20 185 C 22 205 10 210 0 220 Z"/>
      </g>
    </svg>
  </div>
  <div class="forest-lit" id="litLayer">
    <svg viewBox="0 0 1200 700" preserveAspectRatio="xMidYMax slice">
      <defs>
        <radialGradient id="skyGradLit" cx="50%" cy="20%" r="80%">
          <stop offset="0%" stop-color="#2c4234"/>
          <stop offset="100%" stop-color="#182a20"/>
        </radialGradient>
      </defs>
      <rect x="0" y="0" width="1200" height="700" fill="url(#skyGradLit)"/>
      <circle cx="960" cy="120" r="46" fill="#f3f2df"/>
      <g fill="#233a2b">
        <polygon points="0,700 0,430 40,470 70,400 100,460 140,390 170,450 210,410 240,700"/>
        <polygon points="700,700 700,440 740,480 780,410 820,470 860,400 900,460 940,410 980,700"/>
      </g>
      <rect x="0" y="640" width="1200" height="60" fill="#101c14"/>
      <g transform="translate(560,470)" fill="#3a2a1c">
        <path d="M0 220 C -10 210 -22 205 -20 185 L -18 150 C -46 148 -70 130 -78 100 C -84 78 -78 56 -60 44 C -66 30 -64 12 -50 4 C -38 -4 -22 0 -16 10 C -6 4 6 4 16 10 C 22 0 38 -4 50 4 C 64 12 66 30 60 44 C 78 56 84 78 78 100 C 70 130 46 148 18 150 L 20 185 C 22 205 10 210 0 220 Z"/>
      </g>
    </svg>
  </div>
  <div class="torch-glow" id="torchGlow"></div>
  <div class="vignette"></div>

  <a class="tg-btn" href="{telegram_link}" target="_blank" rel="noopener">
    <svg viewBox="0 0 240 240" fill="none">
      <path d="M186 60 L36 118 c-9 3 -9 9 -1 12 l38 12 15 47 c2 5 4 6 8 6 3 0 5 -1 7 -4 l19 -19 39 29 c7 5 12 2 14 -7 l25 -117 c3 -12 -4 -18 -14 -13 Z" fill="#2ea6e6"/>
      <path d="M99 149 L182 84 c4 -3 1 -5 -2 -3 l-99 62 -3 42 z" fill="#c9e6f7"/>
    </svg>
    <span class="dot"></span>
    Наш Telegram-канал
  </a>

  <div class="err-card">
    <div class="err-head">
      <svg class="err-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <circle cx="12" cy="12" r="9.5"/>
        <line x1="12" y1="7.5" x2="12" y2="13"/>
        <circle cx="12" cy="16.3" r="0.9" fill="currentColor" stroke="none"/>
      </svg>
      <div class="err-code">500 — Internal Server Error</div>
    </div>
    <p class="err-msg">Чтобы активировать подписку, примените QR-код или ссылку непосредственно в одном из клиентов: v2rayN, v2rayNG, Clash for Windows, sing-box, NekoBox, NekoRay, Hiddify, Karing, Happ.</p>
    <div class="err-path">GET /sub/… — request failed</div>
  </div>

  <div class="hint">наведите курсор, чтобы осветить лес</div>
  <div class="torch-cursor" id="torchCursor"></div>
</div>
<script>
  const scene = document.getElementById('scene');
  const cursor = document.getElementById('torchCursor');
  let tx = window.innerWidth/2, ty = window.innerHeight*0.4;
  let cx = tx, cy = ty;
  function setVars(x, y){{
    scene.style.setProperty('--x', x + 'px');
    scene.style.setProperty('--y', y + 'px');
  }}
  scene.addEventListener('mousemove', (e) => {{
    tx = e.clientX; ty = e.clientY;
    cursor.style.transform = `translate(${{e.clientX}}px, ${{e.clientY}}px)`;
  }});
  scene.addEventListener('touchmove', (e) => {{
    if(e.touches[0]){{ tx = e.touches[0].clientX; ty = e.touches[0].clientY; }}
  }}, {{ passive:true }});
  function raf(){{
    cx += (tx - cx) * 0.18;
    cy += (ty - cy) * 0.18;
    setVars(cx, cy);
    requestAnimationFrame(raf);
  }}
  raf();
</script>
</body>
</html>
"""


def render_decoy_page(telegram_link: str) -> str:
    return DECOY_HTML_TEMPLATE.format(telegram_link=telegram_link)
