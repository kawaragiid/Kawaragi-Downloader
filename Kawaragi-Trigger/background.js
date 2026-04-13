// PENTING: Gunakan 127.0.0.1 agar merespons secepat kilat
const SERVER_URL = "http://127.0.0.1:65432";

// Teknik LONG POLLING (Terus menyala, respons instan)
async function connectToApp() {
    while (true) {
        try {
            // fetch ini akan "menunggu" sampai Python memberikan URL (tanpa lag)
            const response = await fetch(`${SERVER_URL}/get-task`);
            if (response.ok) {
                const task = await response.json();
                if (task && task.url) {
                    console.log("Tugas masuk secepat kilat:", task.url);
                    await processTask(task.url);
                }
            }
        } catch (e) {
            // Jika aplikasi Desktop belum dibuka, tunggu 2 detik lalu coba lagi
            await new Promise(resolve => setTimeout(resolve, 2000));
        }
    }
}

async function processTask(targetUrl) {
    let cookieString = "";
    try {
        const urlObj = new URL(targetUrl);
        let domain = urlObj.hostname.replace("www.", "");
        
        // Atasi masalah link pendek youtube
        if (domain === "youtu.be") domain = "youtube.com";

        const cookies = await chrome.cookies.getAll({ domain: domain });
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

    try {
        await fetch(`${SERVER_URL}/submit-cookies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cookies: cookieString })
        });
    } catch (e) {
        console.error("Gagal mengirim ke Desktop:", e);
    }
}

// Mulai koneksi abadi
connectToApp();

// Aturan Manifest V3 agar Chrome tidak menidurkan ekstensi
chrome.alarms.create("keepAlive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(() => { console.log("Bridge tetap aktif"); });