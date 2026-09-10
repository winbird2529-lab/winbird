// /static/js/runningConfig.js

const LOCAL_STORAGE_KEY = 'running_mode_config';

export const DEFAULT_CONFIG = {
    pc_mode: "auto",
    ey_mode: "auto",
    dw_mode: "auto",
    tw_mode: "auto"
};

// ดึงการตั้งค่าโหมดเลขที่เอกสาร
export async function getRunningConfig() {
    try {
        const res = await fetch("/api/running-config");
        if (res.ok) {
            const data = await res.json();
            const config = { ...DEFAULT_CONFIG, ...data };
            localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(config));
            return config;
        }
    } catch (err) {
        console.warn("Fetch /api/running-config error, using localStorage fallback:", err);
    }

    try {
        const cached = localStorage.getItem(LOCAL_STORAGE_KEY);
        if (cached) {
            return { ...DEFAULT_CONFIG, ...JSON.parse(cached) };
        }
    } catch (e) {}

    return { ...DEFAULT_CONFIG };
}

// บันทึกการตั้งค่าโหมดเลขที่เอกสาร
export async function saveRunningConfig(config) {
    try {
        localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(config));
        const res = await fetch("/api/running-config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config)
        });
        return res.ok;
    } catch (err) {
        console.warn("Save /api/running-config warning:", err);
        return false;
    }
}
