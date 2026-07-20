package com.cepo.elterminali;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.net.http.SslError;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final String PREFS = "cepo_terminal_prefs";
    private static final String KEY_CONFIGURED = "configured";
    private static final String KEY_PROFILE = "profile";
    private static final String KEY_BRANCH = "branch_id";
    private static final String ADMIN_PIN = "2125";
    private static final String HALK_URL = "https://terminal-halk.limonsupermarket.com";
    private static final String LIMON_URL = "https://terminal-limon.limonsupermarket.com";

    private SharedPreferences prefs;
    private WebView webView;
    private ProgressBar progress;
    private String profile = "HALK";
    private int branchId = 24;
    private long lastBackPress = 0L;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        buildUi();
        configureWebView();

        if (!prefs.getBoolean(KEY_CONFIGURED, false)) {
            showConfigDialog(true);
        } else {
            loadSavedTerminal();
        }
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(243, 246, 242));

        webView = new WebView(this);
        webView.setVisibility(View.INVISIBLE);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        FrameLayout.LayoutParams pp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3)
        );
        pp.gravity = Gravity.TOP;
        root.addView(progress, pp);

        TextView gear = new TextView(this);
        gear.setText("⚙");
        gear.setTextColor(Color.WHITE);
        gear.setTextSize(20);
        gear.setGravity(Gravity.CENTER);
        gear.setBackgroundColor(Color.rgb(11, 93, 42));
        gear.setElevation(dp(6));
        FrameLayout.LayoutParams gp = new FrameLayout.LayoutParams(dp(44), dp(44));
        gp.gravity = Gravity.TOP | Gravity.END;
        gp.topMargin = dp(8);
        gp.rightMargin = dp(8);
        root.addView(gear, gp);
        gear.setOnClickListener(v -> promptAdmin());

        setContentView(root);
    }

    private void configureWebView() {
        android.webkit.WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
                progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                injectBranch(view);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    Toast.makeText(MainActivity.this, "Sunucuya bağlanılamadı.", Toast.LENGTH_LONG).show();
                    webView.setVisibility(View.VISIBLE);
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                Toast.makeText(MainActivity.this, "Güvenli bağlantı doğrulanamadı.", Toast.LENGTH_LONG).show();
            }
        });
    }

    private void loadSavedTerminal() {
        profile = prefs.getString(KEY_PROFILE, "HALK");
        branchId = prefs.getInt(KEY_BRANCH, "LIMON".equals(profile) ? 2 : 24);
        webView.setVisibility(View.INVISIBLE);
        webView.clearHistory();
        webView.loadUrl("LIMON".equals(profile) ? LIMON_URL : HALK_URL);
    }

    private void injectBranch(WebView view) {
        String js = "(function(){try{" +
                "var k='cepo_terminal_branch_id';" +
                "var p='cepo_terminal_native_profile';" +
                "var b='" + branchId + "';" +
                "var changed=false;" +
                "if(localStorage.getItem(k)!==b){localStorage.setItem(k,b);changed=true;}" +
                "if(localStorage.getItem(p)!=='" + profile + "'){localStorage.setItem(p,'" + profile + "');changed=true;}" +
                "return changed?'RELOAD':'OK';" +
                "}catch(e){return 'ERROR';}})();";

        view.evaluateJavascript(js, value -> {
            if (value != null && value.contains("RELOAD")) {
                view.postDelayed(view::reload, 120);
            } else {
                webView.setVisibility(View.VISIBLE);
                webView.requestFocus();
            }
        });
    }

    private void promptAdmin() {
        EditText pin = new EditText(this);
        pin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        pin.setHint("Yönetici şifresi");

        AlertDialog d = new AlertDialog.Builder(this)
                .setTitle("Terminal Ayarları")
                .setView(pin)
                .setNegativeButton("İptal", null)
                .setPositiveButton("Devam", null)
                .create();

        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            if (!ADMIN_PIN.equals(pin.getText().toString().trim())) {
                pin.setError("Şifre hatalı");
                return;
            }
            d.dismiss();
            showConfigDialog(false);
        }));
        d.show();
    }

    private void showConfigDialog(boolean firstRun) {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(22), dp(8), dp(22), 0);

        TextView info = new TextView(this);
        info.setText("Tek APK • HALK veya LIMON profili\nBu ayar yalnız bu terminalde saklanır.");
        info.setPadding(0, 0, 0, dp(12));
        form.addView(info);

        Spinner spinner = new Spinner(this);
        spinner.setAdapter(new ArrayAdapter<>(
                this,
                android.R.layout.simple_spinner_dropdown_item,
                new String[]{"HALK", "LIMON"}
        ));
        spinner.setSelection("LIMON".equals(prefs.getString(KEY_PROFILE, "HALK")) ? 1 : 0);
        form.addView(spinner, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));

        EditText branch = new EditText(this);
        branch.setInputType(InputType.TYPE_CLASS_NUMBER);
        branch.setHint("Şube / Depo ID");
        branch.setText(String.valueOf(prefs.getInt(KEY_BRANCH, 24)));
        form.addView(branch, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));

        EditText firstPin = new EditText(this);
        if (firstRun) {
            firstPin.setHint("Yönetici şifresi");
            firstPin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
            form.addView(firstPin, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));
        }

        AlertDialog.Builder b = new AlertDialog.Builder(this)
                .setTitle(firstRun ? "CEPO El Terminali Kurulumu" : "Terminal Profili")
                .setView(form)
                .setPositiveButton("Kaydet", null);

        if (!firstRun) {
            b.setNegativeButton("İptal", null);
        }

        AlertDialog d = b.create();
        d.setCancelable(!firstRun);
        d.setOnShowListener(x -> d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            if (firstRun && !ADMIN_PIN.equals(firstPin.getText().toString().trim())) {
                firstPin.setError("Yönetici şifresi hatalı");
                return;
            }

            String selected = String.valueOf(spinner.getSelectedItem());
            int id;
            try {
                id = Integer.parseInt(branch.getText().toString().trim());
            } catch (Exception e) {
                branch.setError("Geçerli Şube ID girin");
                return;
            }

            if (id <= 0) {
                branch.setError("Şube ID sıfırdan büyük olmalı");
                return;
            }

            if ("LIMON".equals(selected) && (id < 2 || id > 6)) {
                branch.setError("LIMON için 2 - 6 arası kullanılabilir");
                return;
            }

            prefs.edit()
                    .putBoolean(KEY_CONFIGURED, true)
                    .putString(KEY_PROFILE, selected)
                    .putInt(KEY_BRANCH, id)
                    .apply();

            d.dismiss();
            loadSavedTerminal();
        }));
        d.show();
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
            return;
        }

        long now = System.currentTimeMillis();
        if (now - lastBackPress < 1800) {
            super.onBackPressed();
            return;
        }
        lastBackPress = now;
        Toast.makeText(this, "Çıkmak için tekrar geri tuşuna basın.", Toast.LENGTH_SHORT).show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
