# CEPO El Terminali Android V1

Tek APK içinde iki sunucu profili bulunur:

- HALK → https://terminal-halk.limonsupermarket.com
- LIMON → https://terminal-limon.limonsupermarket.com

## İlk kurulum

İlk açılışta:

1. HALK veya LIMON seçilir.
2. Terminalin sabit Şube / Depo ID değeri girilir.
3. Yönetici şifresi `2125` ile kaydedilir.

Ayar cihazın Android SharedPreferences alanında saklanır.

## Şube entegrasyonu

WebView sayfası açıldığında APK seçili branch ID değerini web uygulamasının:

`cepo_terminal_branch_id`

localStorage anahtarına yazar. Değer farklıysa sayfayı bir kez otomatik yeniler.
Böylece mevcut V43/V44 çoklu-terminal şube yapısı ile uyumlu çalışır.

## Yönetici ayarları

Sağ üstteki küçük dişli düğmesi yönetici şifresi ister.
Doğru şifre ile HALK/LIMON profili ve Şube ID değiştirilebilir.

## Güvenlik

- APK içinde SQL kullanıcı adı veya SQL şifresi yoktur.
- APK SQL Server'a doğrudan bağlanmaz.
- Yalnız Cloudflare Tunnel arkasındaki HTTPS adreslerine bağlanır.
- Harici HTTPS bağlantıları sistem tarayıcısına yönlendirilir.
- SSL hatalarında bağlantı zorla devam ettirilmez.

## Sunucu adresleri

HALK:
`terminal-halk.limonsupermarket.com` → ana bilgisayar `8127` → `HALK2025`

LIMON:
`terminal-limon.limonsupermarket.com` → ana bilgisayar `8128` → `LIMON2023`
