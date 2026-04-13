const SERVER_URL = "http://localhost:65432";

async function checkTask() {
    try {
        const response = await fetch(`${SERVER_URL}/get-task`);
        if (response.ok) {
            const task = await response.json();
            if (task.url) {
                console.log("Menerima tugas untuk:", task.url);
                await processTask(task.url);
            }
        }
    } catch (e) {
        // Server aplikasi belum menyala, abaikan secara diam-diam
    }
}

async function processTask(targetUrl) {
    let cookieString = "";
    try {
        const urlObj = new URL(targetUrl);
        let domain = urlObj.hostname.replace("www.", "");
        
        // Atasi masalah link pendek youtube (youtu.be)
        if (domain === "youtu.be") domain = "youtube.com";

        const cookies = await chrome.cookies.getAll({ domain: domain });
        
        // FORMAT NETSCAPE HTTP COOKIE FILE (Wajib untuk yt-dlp)
        let netscapeCookies = "# Netscape HTTP Cookie File\n";
        for (let c of cookies) {
            let domainStr = c.domain;
            let flag = domainStr.startsWith('.') ? "TRUE" : "FALSE";
            let path = c.path;
            let secure = c.secure ? "TRUE" : "FALSE";
            let expiration = c.expirationDate ? Math.round(c.expirationDate) : 0;
            netscapeCookies += `${domainStr}\t${flag}\t${path}\t${secure}\t${expiration}\t${c.name}\t${c.value}\n`;
        }
        cookieString = netscapeCookies;
    } catch (e) {
        console.error("Gagal ekstrak cookies:", e);
    }

    // Kirim kunci login ke Aplikasi Kawaragi di Desktop
    try {
        await fetch(`${SERVER_URL}/submit-cookies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cookies: cookieString })
        });
    } catch (e) {
        console.error("Gagal mengirim data ke aplikasi desktop", e);
    }
}

// Cek tugas dari aplikasi setiap 1.5 detik
setInterval(checkTask, 1500);

// Mencegah Google Chrome menidurkan ekstensi ini (Aturan Manifest V3)
chrome.alarms.create("keepAlive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(() => { console.log("Kawaragi Bridge tetap aktif"); });