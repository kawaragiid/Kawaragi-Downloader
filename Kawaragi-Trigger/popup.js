document.addEventListener("DOMContentLoaded", () => {
    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const btnSendTab = document.getElementById("btnSendTab");
    const btnSyncCookies = document.getElementById("btnSyncCookies");
    const msgBox = document.getElementById("msgBox");

    function updateStatusUI(connected) {
        if (connected) {
            statusDot.classList.add("online");
            statusText.textContent = "Terhubung ke Aplikasi Desktop";
            statusText.style.color = "#9ece6a";
            btnSendTab.disabled = false;
            btnSyncCookies.disabled = false;
        } else {
            statusDot.classList.remove("online");
            statusText.textContent = "Aplikasi Desktop Belum Aktif";
            statusText.style.color = "#f7768e";
            btnSendTab.disabled = true;
            btnSyncCookies.disabled = true;
            msgBox.textContent = "Pastikan Kawaragi Downloader sedang berjalan.";
        }
    }

    chrome.runtime.sendMessage({ action: "check_status" }, (res) => {
        updateStatusUI(res && res.connected);
    });

    btnSendTab.addEventListener("click", async () => {
        msgBox.textContent = "Mengirim link & cookies ke aplikasi...";
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab || !tab.url || !tab.url.startsWith("http")) {
            msgBox.textContent = "❌ Tab ini bukan halaman web video yang valid.";
            return;
        }
        chrome.runtime.sendMessage({
            action: "send_tab",
            url: tab.url,
            title: tab.title
        }, (res) => {
            if (res && res.success) {
                msgBox.style.color = "#9ece6a";
                msgBox.textContent = "✅ Berhasil dikirim ke Kawaragi Downloader!";
            } else {
                msgBox.style.color = "#f7768e";
                msgBox.textContent = "❌ Gagal mengirim ke aplikasi.";
            }
        });
    });

    btnSyncCookies.addEventListener("click", async () => {
        msgBox.textContent = "Menyinkronkan seluruh cookies...";
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        const targetUrl = (tab && tab.url && tab.url.startsWith("http")) ? tab.url : "ALL";
        chrome.runtime.sendMessage({
            action: "sync_cookies",
            url: targetUrl
        }, (res) => {
            if (res && res.success) {
                msgBox.style.color = "#9ece6a";
                msgBox.textContent = "✅ Cookies berhasil disinkronkan!";
            } else {
                msgBox.style.color = "#f7768e";
                msgBox.textContent = "❌ Gagal mengirim cookies ke aplikasi.";
            }
        });
    });
});
