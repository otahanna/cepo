# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V68

KULLANIM:
- CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyun.
- V68'i çalıştırın.

V68:
- V67 bakiye / son maliyet / tutar düzenini korur.
- Ürün açıldığında Ürün Adı + Barkod ile Google Görseller araması yapar.
- İlk indirilebilir gerçek görseli alır.
- Arka planı mümkünse rembg, değilse kenar tabanlı yöntemle temizler.
- Görseli barkod bazında yerel önbelleğe kaydeder.
"""

from __future__ import annotations

import os
import sys
import io
import re
import json
import html
import threading
import importlib.util
import urllib.parse
import urllib.request
from typing import List, Tuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
V67_FILE = "CEPO_Hizli_Stok_Karti_V67_Referans_Bakiye_Gorsel.py"
V67_PATH = os.path.join(HERE, V67_FILE)
V67_URL = "https://raw.githubusercontent.com/otahanna/cepo/main/CEPO_Hizli_Stok_Karti_V67_Referans_Bakiye_Gorsel.py"

# V67 aynı klasörde yoksa otomatik indir. V67 de V65'i kullanır.
if not os.path.isfile(V67_PATH):
    try:
        req = urllib.request.Request(
            V67_URL,
            headers={"User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok-V68"},
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
        with open(V67_PATH, "wb") as f:
            f.write(data)
    except Exception as exc:
        raise SystemExit(
            "V67 yardımcı dosyası bulunamadı ve otomatik indirilemedi.\n"
            + str(exc)
        )

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v67_base", V67_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V67 modülü yüklenemedi.")
v67 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v67
spec.loader.exec_module(v67)

base = v67.base
base.APP_TITLE = "CEPO Hızlı Stok Kartı V68"

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    Image = None
    PIL_OK = False


def _v68_google_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Connection": "close",
    }


def _v68_fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_v68_google_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(8 * 1024 * 1024)
        ctype = str(resp.headers.get("Content-Type") or "")
    enc = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    try:
        return raw.decode(enc, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _v68_decode_url(value: str) -> str:
    u = html.unescape(str(value or ""))
    u = u.replace("\\u003d", "=").replace("\\u0026", "&")
    u = u.replace("\\/", "/")
    try:
        u = bytes(u, "utf-8").decode("unicode_escape")
    except Exception:
        pass
    return u.strip()


def _v68_is_good_image_url(url: str) -> bool:
    low = str(url or "").lower()
    if not low.startswith(("http://", "https://")):
        return False
    bad_hosts = (
        "google.com", "googleusercontent.com/images/branding", "gstatic.com",
        "googleapis.com", "youtube.com", "ytimg.com"
    )
    if any(x in low for x in bad_hosts):
        return False
    bad_words = ("favicon", "logo", "sprite", "icon", "blank.gif", "transparent.gif")
    if any(x in low for x in bad_words):
        return False
    return True


def _v68_google_image_candidates(query: str) -> List[str]:
    q = str(query or "").strip()
    if not q:
        return []
    url = "https://www.google.com/search?tbm=isch&hl=tr&safe=active&q=" + urllib.parse.quote_plus(q)
    page = _v68_fetch_text(url)

    candidates: List[str] = []

    # Google Görseller sayfasında farklı dönemlerde kullanılan özgün görsel alanları.
    patterns = [
        r'"ou":"(https?://[^"\\]+(?:\\.[^"\\]*)?)"',
        r'"originalImageUrl":"(https?://[^"\\]+(?:\\.[^"\\]*)?)"',
        r'\["(https?://[^"\\]+\.(?:jpg|jpeg|png|webp)(?:\?[^"\\]*)?)",\d+,\d+\]',
        r'imgurl=(https?%3A%2F%2F[^&"\s]+)',
        r'"(https?://[^"\\\s]+\.(?:jpg|jpeg|png|webp)(?:\?[^"\\\s]*)?)"',
    ]

    for pat in patterns:
        for found in re.findall(pat, page, flags=re.I):
            try:
                if found.startswith("http%"):
                    found = urllib.parse.unquote(found)
                u = _v68_decode_url(found)
            except Exception:
                continue
            if _v68_is_good_image_url(u) and u not in candidates:
                candidates.append(u)
        if len(candidates) >= 20:
            break

    # Bazı Google HTML'lerinde imgres bağlantısından özgün URL çıkar.
    for found in re.findall(r'href=["\']([^"\']*?/imgres\?[^"\']+)["\']', page, flags=re.I):
        try:
            full = html.unescape(found)
            parsed = urllib.parse.urlparse(full)
            qs = urllib.parse.parse_qs(parsed.query)
            u = (qs.get("imgurl") or [""])[0]
            u = _v68_decode_url(u)
            if _v68_is_good_image_url(u) and u not in candidates:
                candidates.append(u)
        except Exception:
            pass

    return candidates


def _v68_google_cache_path(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(barcode or "urun"))
    return os.path.join(v67._v67_cache_dir(), "google_" + safe + ".png")


def _v68_download_bytes(url: str, referer: str = "https://www.google.com/", timeout: int = 20) -> bytes:
    headers = _v68_google_headers()
    headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(12 * 1024 * 1024)


def _v68_download_google_image(product_name: str, barcode: str):
    if not PIL_OK:
        return None, ""

    cache = _v68_google_cache_path(barcode)
    if os.path.isfile(cache):
        try:
            return Image.open(cache).convert("RGBA"), "Google Görseller"
        except Exception:
            pass

    query = " ".join(x for x in [str(product_name or "").strip(), str(barcode or "").strip()] if x)
    candidates = []
    try:
        candidates = _v68_google_image_candidates(query)
    except Exception:
        candidates = []

    # İlk sonuç önceliklidir; indirilemezse yalnızca teknik fallback olarak sıradaki denenir.
    for image_url in candidates[:12]:
        try:
            raw = _v68_download_bytes(image_url)
            if not raw:
                continue
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img = v67._v67_remove_background(img)
            if img is None:
                continue
            try:
                img.save(cache, "PNG", optimize=True)
            except Exception:
                pass
            return img, "Google Görseller"
        except Exception:
            continue

    # Google tarafı geçici olarak engellenirse boş kalmaması için V67 kaynağına düş.
    try:
        return v67._v67_download_product_image(barcode)
    except Exception:
        return None, ""


def _v68_start_product_image(self, barcode: str):
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return
    try:
        product_name = (self.ent_stokadi.get() or "").strip()
    except Exception:
        product_name = ""

    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    token = self._v67_image_token
    v67._v67_set_image_status(
        self,
        "GOOGLE GÖRSELLER'DE ARANIYOR...\n" + (product_name or digits),
    )

    def worker():
        image, source = _v68_download_google_image(product_name, digits)
        try:
            self.after(0, lambda: v67._v67_apply_product_image(self, token, image, source))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


# V67'in ToptanTR otomatik aramasını devre dışı bırakıp Google akışını bağla.
def _v68_load_product_dashboard(self, barcode: Optional[str] = None):
    b = (barcode or (self.ent_barkod.get() if hasattr(self, "ent_barkod") else "") or "").strip()
    result = v67._ORIG_LOAD_PRODUCT_DASHBOARD(self, barcode)
    if b:
        _v68_start_product_image(self, b)
    return result


base.App.load_product_dashboard = _v68_load_product_dashboard


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
