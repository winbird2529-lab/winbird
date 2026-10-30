const host = (typeof window !== "undefined" && window.location.hostname) ? window.location.hostname : "192.168.1.180";
export const API_BASE = `http://${host}:8000`;