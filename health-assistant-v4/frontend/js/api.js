/**
 * SympGuard AI -- thin fetch wrapper around the backend API.
 * No framework, no build step -- plain functions returning Promises.
 */
const SympGuardAPI = (function () {
  const BASE = window.SYMPGUARD_CONFIG.API_BASE;

  async function request(path, options) {
    let res;
    try {
      res = await fetch(BASE + path, Object.assign({
        headers: { "Content-Type": "application/json" },
      }, options));
    } catch (networkErr) {
      const err = new Error("Could not reach the SympGuard AI server. Check that the backend is running and reachable.");
      err.isNetworkError = true;
      throw err;
    }

    let body = null;
    try { body = await res.json(); } catch (_) { /* no body */ }

    if (!res.ok) {
      const message = (body && body.detail) ? body.detail : `Request failed (${res.status})`;
      const err = new Error(typeof message === "string" ? message : JSON.stringify(message));
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  return {
    startCheck(text, region) {
      return request("/api/symptoms/start", { method: "POST", body: JSON.stringify({ text: text, region: region || null }) });
    },
    followUp(sessionId, answers) {
      return request("/api/symptoms/follow-up", { method: "POST", body: JSON.stringify({ session_id: sessionId, answers: answers }) });
    },
    analyze(sessionId) {
      return request("/api/symptoms/analyze", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
    },
    doctorSummary(sessionId) {
      return request("/api/doctor-summary", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
    },
    listFirstAid() {
      return request("/api/first-aid", { method: "GET" });
    },
    getFirstAid(topicId) {
      return request("/api/first-aid/" + encodeURIComponent(topicId), { method: "GET" });
    },
    getEmergencyContacts(region) {
      const q = region ? ("?region=" + encodeURIComponent(region)) : "";
      return request("/api/emergency-contacts" + q, { method: "GET" });
    },
    getRegions() {
      return request("/api/emergency-contacts/regions", { method: "GET" });
    },
    getSources() {
      return request("/api/sources", { method: "GET" });
    },
    health() {
      return request("/health", { method: "GET" });
    },
  };
})();
