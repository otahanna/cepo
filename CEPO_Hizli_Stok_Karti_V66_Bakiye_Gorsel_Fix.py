# -*- coding: utf-8 -*-
"""
CEPO Hızlı Stok Kartı V66 - V65 Bakiye + Tam Sayı + Otomatik Ürün Görseli Fix

KULLANIM:
- Bu dosyayı CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py ile aynı klasöre koyun.
- V66 dosyasını çalıştırın.
- V65'in tüm özellikleri korunur; aşağıdaki düzeltmeler çalışma anında uygulanır.

DÜZELTMELER:
1) Gerçek stok bakiyesi: TBL_STOK_HAREKET.DEPOID bazında SUM(MIKTAR).
   Hareket tipine göre miktarı ikinci kez artı/eksi çevirmediği için transfer bakiyesi bozulmaz.
2) Kusuratsız miktarlar 12,000 yerine 12 olarak gösterilir.
3) Barkod okutulduğunda ürün görseli otomatik aranır.
4) Görselin kenara bağlı düz/tek renk arka planı otomatik şeffaflaştırılır.
5) Görseller yerel urun_gorsel_cache klasöründe önbelleğe alınır.
"""

from __future__ import annotations

import os
import sys
import io
import re
import json
import math
import threading
import traceback
import importlib.util
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Dict, List, Optional

BASE_FILE = "CEPO_Hizli_Stok_Karti_V65_Referans_Profesyonel.py"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PATH = os.path.join(HERE, BASE_FILE)

if not os.path.exists(BASE_PATH):
    raise SystemExit(
        f"Gerekli ana dosya bulunamadı:\n{BASE_PATH}\n\n"
        f"{BASE_FILE} ile bu V66 dosyasını aynı klasöre koyun."
    )

spec = importlib.util.spec_from_file_location("cepo_hizli_stok_v65_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("V65 ana modülü yüklenemedi.")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.APP_TITLE = "CEPO Hızlı Stok Kartı V66"

try:
    from PIL import Image, ImageFilter
    PIL_OK = True
except Exception:
    Image = None
    ImageFilter = None
    PIL_OK = False

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


# -----------------------------------------------------------------------------
# 1) BAKİYE FIX - CEPO'nun gerçek depo stok mantığı
# -----------------------------------------------------------------------------
_ORIG_GET_DASHBOARD = base.DBAdapter.get_stock_dashboard


def _v66_get_stock_dashboard(self, stock_id: int, db_name: str) -> Dict[str, Any]:
    """V65 panel verisini alır, bakiye ve şube stoklarını gerçek SUM(MIKTAR) ile düzeltir."""
    result = _ORIG_GET_DASHBOARD(self, stock_id, db_name)
    if not self.cn or not stock_id:
        return result

    try:
        hcols = self._table_cols(base.HAREKET_TABLE)
        h_stok = self._first_existing(hcols, ["STOKID", "STOKKARTID", "STOK_ID"])
        h_qty = self._first_existing(hcols, ["MIKTAR", "ADET", "MIK", "QTY", "MIKTAR1"])
        # CEPO/HALK/LİMON gerçek şube bakiyesi DEPOID üzerinden tutuluyor.
        h_depo = self._first_existing(hcols, ["DEPOID"])
        h_date = self._first_existing(hcols, ["BELGETARIHI", "TARIH", "ISLEMTARIHI", "CREATEDATE"])

        if not h_stok or not h_qty or not h_depo:
            return result

        depo_map = self._id_name_map(
            base.DEPO_TABLE,
            ["DEPOADI", "DEPO_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )
        sube_map = self._id_name_map(
            base.SUBE_TABLE,
            ["SUBEADI", "SUBE_ADI", "ACIKLAMA", "ADI", "ISIM", "TANIM"],
        )

        cur = self.cn.cursor()
        date_expr = f"MAX(H.{h_date})" if h_date else "NULL"

        # Kaynak sistemde MIKTAR zaten işaretlidir:
        # giriş +, çıkış -. Bu nedenle tekrar hareket tipinden işaret üretmiyoruz.
        cur.execute(
            f"""
            SELECT
                ISNULL(SUM(CASE WHEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) > 0
                                THEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) ELSE 0 END),0),
                ISNULL(SUM(CASE WHEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) < 0
                                THEN ABS(CAST(ISNULL(H.{h_qty},0) AS FLOAT)) ELSE 0 END),0),
                ISNULL(SUM(CAST(ISNULL(H.{h_qty},0) AS FLOAT)),0)
            FROM {base.HAREKET_TABLE} H WITH (NOLOCK)
            WHERE H.{h_stok}=?
            """,
            (int(stock_id),),
        )
        rr = cur.fetchone()
        if rr:
            result.setdefault("summary", {})["in"] = float(rr[0] or 0)
            result["summary"]["out"] = float(rr[1] or 0)
            result["summary"]["balance"] = float(rr[2] or 0)

        cur.execute(
            f"""
            SELECT
                H.{h_depo},
                ISNULL(SUM(CASE WHEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) > 0
                                THEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) ELSE 0 END),0) AS GIRIS,
                ISNULL(SUM(CASE WHEN CAST(ISNULL(H.{h_qty},0) AS FLOAT) < 0
                                THEN ABS(CAST(ISNULL(H.{h_qty},0) AS FLOAT)) ELSE 0 END),0) AS CIKIS,
                ISNULL(SUM(CAST(ISNULL(H.{h_qty},0) AS FLOAT)),0) AS BAKIYE,
                {date_expr} AS SON_HAREKET
            FROM {base.HAREKET_TABLE} H WITH (NOLOCK)
            WHERE H.{h_stok}=? AND H.{h_depo} IS NOT NULL
            GROUP BY H.{h_depo}
            ORDER BY H.{h_depo}
            """,
            (int(stock_id),),
        )

        branches: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            depo_id, giris, cikis, bakiye, son_hareket = row
            try:
                did = int(depo_id)
            except Exception:
                did = None
            location = depo_map.get(did) or sube_map.get(did) or str(depo_id or "")
            branches.append(
                {
                    "db": db_name.upper(),
                    "location": location,
                    "in": float(giris or 0),
                    "out": float(cikis or 0),
                    "balance": float(bakiye or 0),
                    "last_date": son_hareket,
                }
            )

        # Depo bazında gerçek hareket toplamı bulunduysa V65'in türetilmiş listesini değiştir.
        result["branches"] = branches

        # Hareket tablosunda negatif miktarlar V65 tarafından yanlışlıkla pozitife çevrilmiş olabilir.
        # Son hareket listesini de ham işareti koruyarak düzeltelim.
        try:
            h_type = self._first_existing(hcols, ["HAREKETTIPID", "TIPID", "HAREKETTIPI"])
            h_doc = self._first_existing(hcols, ["BELGENO", "BELGEKODU", "FISNO", "EVRAKNO"])
            h_desc = self._first_existing(hcols, ["ACIKLAMA", "NOTLAR", "NOT", "DESCRIPTION"])
            if h_type:
                # Aynı tarih/tip/depo/belge/miktar üzerinden ham işaretleri eşleştir.
                raw_rows = {}
                cols = [h_date or "CREATEDATE", h_type, h_depo, h_doc, h_qty]
                select_cols = ", ".join(f"H.{c}" if c else "NULL" for c in cols)
                cur.execute(
                    f"SELECT TOP 700 {select_cols} FROM {base.HAREKET_TABLE} H WITH (NOLOCK) "
                    f"WHERE H.{h_stok}=? ORDER BY H.{h_date or h_qty} DESC",
                    (int(stock_id),),
                )
                for r in cur.fetchall():
                    dt, tid, dep, doc, qty = r
                    key = (str(dt), str(tid), str(dep), str(doc or ""))
                    raw_rows.setdefault(key, []).append(float(qty or 0))
                for move in result.get("movements", []):
                    dep_name = str(move.get("location") or "")
                    # Lokasyon ismi üzerinden depo ID bul.
                    dep_id = None
                    for k, v in depo_map.items():
                        if str(v) == dep_name:
                            dep_id = k
                            break
                    type_name = str(move.get("type") or "")
                    tid_match = None
                    # Tip ismi eşleştirmesi kesin değilse dokunmayız.
                    try:
                        tip_cols = self._table_cols(base.HAREKET_TIP_TABLE)
                        tip_id_col = self._first_existing(tip_cols, ["ID"])
                        tip_name_col = self._first_existing(tip_cols, ["HAREKETTIPI", "ACIKLAMA", "TANIM", "ADI", "ISIM"])
                        if tip_id_col and tip_name_col:
                            cc = self.cn.cursor()
                            cc.execute(
                                f"SELECT TOP 1 {tip_id_col} FROM {base.HAREKET_TIP_TABLE} WITH (NOLOCK) WHERE {tip_name_col}=?",
                                (type_name,),
                            )
                            tx = cc.fetchone()
                            tid_match = int(tx[0]) if tx else None
                    except Exception:
                        tid_match = None
                    key = (str(move.get("date")), str(tid_match), str(dep_id), str(move.get("document") or ""))
                    vals = raw_rows.get(key)
                    if vals:
                        move["qty"] = vals.pop(0)
        except Exception:
            pass

    except Exception as exc:
        try:
            base.debug_print(f"V66 gerçek bakiye düzeltmesi uygulanamadı ({db_name}): {exc}")
        except Exception:
            pass
    return result


base.DBAdapter.get_stock_dashboard = _v66_get_stock_dashboard


# -----------------------------------------------------------------------------
# 2) TAM SAYI / AKILLI MİKTAR FORMATLAMA
# -----------------------------------------------------------------------------
def _v66_fmt_number(self, value: Any, decimals: int = 2) -> str:
    try:
        n = float(value or 0)
    except Exception:
        return ""
    if not math.isfinite(n):
        return ""

    # 12.000000 -> 12
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}".replace(",", ".")

    # Gerçek küsurat varsa en fazla istenen basamak; sondaki sıfırları gösterme.
    raw = f"{n:,.{max(0, int(decimals))}f}"
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw.replace(",", "X").replace(".", ",").replace("X", ".")


def _v66_fmt_money(self, value: Any) -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    raw = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return raw + " ₺"


base.App._fmt_number = _v66_fmt_number
base.App._fmt_money = _v66_fmt_money


# -----------------------------------------------------------------------------
# 3) OTOMATİK ÜRÜN GÖRSELİ + ARKA PLAN TEMİZLEME
# -----------------------------------------------------------------------------
def _http_json(url: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok/66",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(2 * 1024 * 1024)
        return json.loads(data.decode("utf-8", errors="ignore"))
    except Exception:
        return None


def _download_image(url: str, timeout: int = 10) -> Optional[bytes]:
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 CEPO-Hizli-Stok/66",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            return None
        return data
    except Exception:
        return None


def _find_product_image_urls(barcode: str, product_name: str = "") -> List[str]:
    urls: List[str] = []
    barcode = re.sub(r"\D", "", str(barcode or ""))

    # Barkod tabanlı kaynaklar en güvenilir olanlar.
    if barcode:
        # UPCitemdb
        data = _http_json("https://api.upcitemdb.com/prod/trial/lookup?upc=" + urllib.parse.quote(barcode))
        try:
            for item in (data or {}).get("items", []):
                for u in item.get("images", []) or []:
                    if u and u not in urls:
                        urls.append(u)
        except Exception:
            pass

        # Open*Facts ailesi
        facts_hosts = [
            "world.openfoodfacts.org",
            "world.openbeautyfacts.org",
            "world.openproductsfacts.org",
            "world.openpetfoodfacts.org",
        ]
        for host in facts_hosts:
            data = _http_json(f"https://{host}/api/v2/product/{barcode}.json")
            product = (data or {}).get("product") or {}
            for key in (
                "image_front_url",
                "image_front_small_url",
                "image_url",
                "image_small_url",
            ):
                u = product.get(key)
                if u and u not in urls:
                    urls.append(u)

    # Barkod servislerinde bulunmazsa Bing görsel sonuçlarından doğrudan görsel URL'lerini dene.
    # API anahtarı gerektirmez; bulunamazsa sessizce geçilir.
    query = " ".join(x for x in [barcode, product_name, "ürün"] if x).strip()
    if query and len(urls) < 3:
        try:
            search_url = "https://www.bing.com/images/search?q=" + urllib.parse.quote(query) + "&form=HDRSC2"
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read(2 * 1024 * 1024).decode("utf-8", errors="ignore")
            for u in re.findall(r'&quot;murl&quot;:&quot;(https?://[^&]+?)&quot;', html):
                u = u.replace("\\/", "/")
                if u not in urls:
                    urls.append(u)
                if len(urls) >= 8:
                    break
            if len(urls) < 3:
                for u in re.findall(r'"murl"\s*:\s*"(https?://[^\"]+)"', html):
                    u = u.replace("\\/", "/")
                    if u not in urls:
                        urls.append(u)
                    if len(urls) >= 8:
                        break
        except Exception:
            pass

    return urls[:10]


def _edge_background_remove(img):
    """Kenarlarla bağlantılı düz arka planı kaldırır; ürünün içindeki beyaz alanları korur."""
    if not PIL_OK:
        return img
    img = img.convert("RGBA")

    # İşlem maliyetini sınırlamak için geçici küçültme.
    work = img.copy()
    max_side = max(work.size)
    if max_side > 900:
        scale = 900.0 / max_side
        work = work.resize((max(1, int(work.width * scale)), max(1, int(work.height * scale))))

    px = work.load()
    w, h = work.size
    if w < 3 or h < 3:
        return img

    # Köşe örneklerinden arka plan rengini tahmin et.
    samples = []
    step = max(1, min(w, h) // 40)
    for x in range(0, min(w, step * 5), step):
        for y in range(0, min(h, step * 5), step):
            samples.extend([px[x, y][:3], px[w - 1 - x, y][:3], px[x, h - 1 - y][:3], px[w - 1 - x, h - 1 - y][:3]])
    if not samples:
        return img
    bg = tuple(int(sum(c[i] for c in samples) / len(samples)) for i in range(3))

    def dist(rgb):
        return math.sqrt(sum((int(rgb[i]) - bg[i]) ** 2 for i in range(3)))

    # Köşeler birbirinden çok farklıysa fotoğrafın düz bir arka planı yoktur; agresif silme yapma.
    corner_colors = [px[0, 0][:3], px[w - 1, 0][:3], px[0, h - 1][:3], px[w - 1, h - 1][:3]]
    corner_spread = max(dist(c) for c in corner_colors)
    threshold = 52 if corner_spread < 70 else 34

    candidate = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0 or dist((r, g, b)) <= threshold:
                candidate[y * w + x] = 1

    # Yalnızca dış kenardan erişilebilen benzer renkli alanları arka plan say.
    visited = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            idx = y * w + x
            if candidate[idx] and not visited[idx]:
                visited[idx] = 1; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            idx = y * w + x
            if candidate[idx] and not visited[idx]:
                visited[idx] = 1; q.append((x, y))

    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if candidate[idx] and not visited[idx]:
                    visited[idx] = 1
                    q.append((nx, ny))

    alpha = Image.new("L", (w, h), 255)
    ap = alpha.load()
    for y in range(h):
        for x in range(w):
            if visited[y * w + x]:
                ap[x, y] = 0
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.1))
    work.putalpha(alpha)

    bbox = work.getbbox()
    if bbox:
        l, t, r, b = bbox
        pad = max(4, int(min(w, h) * 0.025))
        bbox = (max(0, l - pad), max(0, t - pad), min(w, r + pad), min(h, b + pad))
        work = work.crop(bbox)
    return work


def _prepare_product_image(data: bytes):
    if not PIL_OK:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        # rembg bilgisayarda zaten kuruluysa daha güçlü çıkarma kullan.
        if rembg_remove is not None:
            try:
                out = rembg_remove(img)
                if out is not None:
                    img = out.convert("RGBA")
            except Exception:
                img = _edge_background_remove(img)
        else:
            img = _edge_background_remove(img)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        return img
    except Exception:
        return None


def _cache_path(barcode: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", str(barcode or "urun"))[:80] or "urun"
    folder = os.path.join(base.app_dir(), "urun_gorsel_cache")
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        folder = HERE
    return os.path.join(folder, safe + ".png")


def _show_product_image(self, img, token: int):
    if token != getattr(self, "_v66_image_token", -1) or img is None:
        return
    try:
        # Görsel kutusuna oranı bozmadan sığdır.
        max_w, max_h = 250, 205
        w, h = img.size
        scale = min(max_w / max(1, w), max_h / max(1, h), 1.0)
        size = (max(1, int(w * scale)), max(1, int(h * scale)))
        ctk_img = base.ctk.CTkImage(light_image=img, dark_image=img, size=size)
        self._v66_product_ctk_image = ctk_img
        self.lbl_product_visual.configure(image=ctk_img, text="")
    except Exception as exc:
        try:
            base.debug_print(f"Ürün görseli gösterilemedi: {exc}")
        except Exception:
            pass


def _product_image_worker(self, barcode: str, product_name: str, token: int):
    if not PIL_OK:
        return
    cache = _cache_path(barcode)
    try:
        if os.path.exists(cache) and os.path.getsize(cache) > 1000:
            img = Image.open(cache).convert("RGBA")
            self.after(0, lambda im=img: _show_product_image(self, im, token))
            return
    except Exception:
        pass

    urls = _find_product_image_urls(barcode, product_name)
    for url in urls:
        if token != getattr(self, "_v66_image_token", -1):
            return
        data = _download_image(url)
        if not data:
            continue
        img = _prepare_product_image(data)
        if img is None or img.width < 40 or img.height < 40:
            continue
        try:
            img.save(cache, "PNG")
        except Exception:
            pass
        self.after(0, lambda im=img: _show_product_image(self, im, token))
        return

    if token == getattr(self, "_v66_image_token", -1):
        def no_img():
            try:
                self.lbl_product_visual.configure(image=None, text="ÜRÜN GÖRSELİ\nBulunamadı")
                self._v66_product_ctk_image = None
            except Exception:
                pass
        self.after(0, no_img)


def _start_auto_image(self, barcode: Optional[str] = None):
    barcode = (barcode or (self.ent_barkod.get() if hasattr(self, "ent_barkod") else "") or "").strip()
    product_name = (self.ent_stokadi.get() if hasattr(self, "ent_stokadi") else "") or ""
    if not barcode and not product_name:
        return
    self._v66_image_token = getattr(self, "_v66_image_token", 0) + 1
    token = self._v66_image_token
    try:
        self.lbl_product_visual.configure(image=None, text="ÜRÜN GÖRSELİ\nOtomatik aranıyor...")
        self._v66_product_ctk_image = None
    except Exception:
        pass
    threading.Thread(
        target=_product_image_worker,
        args=(self, barcode, product_name.strip(), token),
        daemon=True,
    ).start()


_ORIG_LOAD_DASHBOARD = base.App.load_product_dashboard


def _v66_load_product_dashboard(self, barcode: Optional[str] = None):
    result = _ORIG_LOAD_DASHBOARD(self, barcode)
    try:
        _start_auto_image(self, barcode)
    except Exception:
        pass
    return result


_ORIG_CLEAR_DASHBOARD = base.App._clear_dashboard


def _v66_clear_dashboard(self):
    result = _ORIG_CLEAR_DASHBOARD(self)
    self._v66_image_token = getattr(self, "_v66_image_token", 0) + 1
    self._v66_product_ctk_image = None
    try:
        self.lbl_product_visual.configure(
            image=None,
            text="▦\n\nÜRÜN GÖRSELİ\nBarkod okutulduğunda otomatik aranır",
        )
    except Exception:
        pass
    return result


base.App.load_product_dashboard = _v66_load_product_dashboard
base.App._clear_dashboard = _v66_clear_dashboard
base.App._start_auto_product_image = _start_auto_image


# Başlangıç bilgisi
try:
    base.debug_print("[V66] Gerçek depo bakiyesi + tam sayı gösterimi + otomatik arka plansız ürün görseli aktif.")
except Exception:
    pass


if __name__ == "__main__":
    login_app = base.LoginWindow()
    login_app.mainloop()
