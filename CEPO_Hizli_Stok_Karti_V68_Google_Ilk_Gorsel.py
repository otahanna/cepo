# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V68 - Google Görseller İlk Sonuç

Bu yama V67'nin tüm özelliklerini korur ve ürün görseli bulma motorunu değiştirir:
- Arama: "<stok adı> <barkod> ürün"
- Google Görseller HTML sonucundaki ilk uygun harici ürün görselini seçer.
- Google/gstatic/logo/icon/banner gibi sonuçları atlar.
- Görseli indirir, V67'nin arka plan temizleme motorundan geçirir ve ekrana getirir.
- Google sonucu bulunamazsa V67'nin ToptanTR/OpenFoodFacts yedeğine düşer.

KULLANIM:
V65, V67 ve bu V68 dosyası aynı klasörde olmalıdır. V68 çalıştırılır.
"""
from __future__ import annotations

import os
import sys
import io
import re
import html
import importlib.util
import urllib.parse
import urllib.request
from typing import List, Tuple

BASE_FILE = "CEPO_Hizli_Stok_Karti_V67_Referans_Bakiye_Gorsel.py"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(HERE, BASE_FILE)
if not os.path.isfile(BASE_PATH):
    raise SystemExit("Gerekli V67 dosyası bulunamadı: " + BASE_PATH)

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v67_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V67 modülü yüklenemedi.")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.base.APP_TITLE = "CEPO Hızlı Stok Kartı V68"

try:
    from PIL import Image
except Exception:
    Image = None

_ORIG_DOWNLOAD = base._v67_download_product_image
_ORIG_START = base._v67_start_product_image


def _google_headers():
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


def _fetch_google_html(query: str) -> str:
    url = "https://www.google.com/search?tbm=isch&hl=tr&safe=active&q=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers=_google_headers())
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read(6 * 1024 * 1024)
        ctype = str(resp.headers.get("Content-Type") or "")
    enc = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    if m:
        enc = m.group(1)
    return data.decode(enc, errors="replace")


def _clean_url(u: str) -> str:
    u = html.unescape(str(u or ""))
    u = u.replace("\\u003d", "=").replace("\\u0026", "&").replace("\\/", "/")
    u = u.replace("\\u002F", "/").replace("\\u003A", ":")
    return u.strip()


def _is_bad_image_url(url: str) -> bool:
    low = str(url or "").lower()
    if not low.startswith(("http://", "https://")):
        return True
    bad_hosts = (
        "google.com", "googleusercontent.com", "gstatic.com", "ggpht.com",
        "youtube.com", "ytimg.com", "facebook.com", "instagram.com",
    )
    if any(x in low for x in bad_hosts):
        return True
    bad_words = ("logo", "favicon", "icon", "sprite", "banner", "placeholder", "avatar", "whatsapp")
    if any(x in low for x in bad_words):
        return True
    return False


def _extract_google_image_urls(page: str) -> List[str]:
    urls: List[str] = []

    # Google Görseller masaüstü sonucunda gerçek görseller çoğunlukla bu JSON alanlarında bulunur.
    patterns = [
        r'\["(https?://[^"\\]+(?:\\.[^"\\]*)?)",\d+,\d+\]',
        r'"ou":"(https?://[^"]+)"',
        r'"(https?://[^" ]+?\.(?:jpg|jpeg|png|webp)(?:\?[^" ]*)?)"',
        r'(https?://[^"\'<> ]+?\.(?:jpg|jpeg|png|webp)(?:\?[^"\'<> ]*)?)',
    ]
    for pat in patterns:
        try:
            found = re.findall(pat, page or "", flags=re.I)
        except Exception:
            found = []
        for raw in found:
            u = _clean_url(raw)
            if _is_bad_image_url(u):
                continue
            if u not in urls:
                urls.append(u)
    return urls


def _download_first_google_image(query: str):
    if Image is None:
        return None
    try:
        page = _fetch_google_html(query)
    except Exception:
        return None

    for url in _extract_google_image_urls(page)[:20]:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    **_google_headers(),
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    "Referer": "https://www.google.com/",
                },
            )
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = resp.read(12 * 1024 * 1024)
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            if img.width < 120 or img.height < 120:
                continue
            return img
        except Exception:
            continue
    return None


def _v68_download_product_image(barcode: str, product_name: str = ""):
    if Image is None:
        return _ORIG_DOWNLOAD(barcode)

    cache = base._v67_cache_path(barcode)
    if os.path.isfile(cache):
        try:
            return Image.open(cache).convert("RGBA"), "Önbellek"
        except Exception:
            pass

    query_parts = []
    name = str(product_name or "").strip()
    if name:
        query_parts.append(name)
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if digits:
        query_parts.append(digits)
    query_parts.append("ürün")
    query = " ".join(query_parts)

    img = _download_first_google_image(query)
    if img is not None:
        try:
            img = base._v67_remove_background(img)
        except Exception:
            pass
        try:
            img.save(cache, "PNG", optimize=True)
        except Exception:
            pass
        return img, "Google Görseller"

    return _ORIG_DOWNLOAD(barcode)


def _v68_start_product_image(self, barcode: str):
    digits = re.sub(r"\D+", "", str(barcode or ""))
    if not digits:
        return
    self._v67_image_token = int(getattr(self, "_v67_image_token", 0)) + 1
    token = self._v67_image_token
    try:
        name = str(self.ent_stokadi.get() or "").strip()
    except Exception:
        name = ""
    base._v67_set_image_status(self, "GOOGLE GÖRSELLER'DE ARANIYOR...\n" + (name or digits))

    def worker():
        image, source = _v68_download_product_image(digits, name)
        try:
            self.after(0, lambda: base._v67_apply_product_image(self, token, image, source))
        except Exception:
            pass

    import threading
    threading.Thread(target=worker, daemon=True).start()


base._v67_start_product_image = _v68_start_product_image

# V67 load_product_dashboard fonksiyonu çalışma anında global _v67_start_product_image adını çağırdığı için
# yukarıdaki override otomatik devreye girer.

if __name__ == "__main__":
    login_app = base.base.LoginWindow()
    login_app.mainloop()
