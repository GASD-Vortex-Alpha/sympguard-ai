/**
 * SympGuard AI -- API configuration.
 *
 * No build step, so there's no .env for the frontend. Instead:
 *   1. If the page has <meta name="sympguard-api-base" content="https://your-api.example.com">,
 *      that value is used -- this is what you edit when deploying (see README "Deployment").
 *   2. Otherwise, if running on localhost, default to the local backend.
 *   3. Otherwise, assume the API is reverse-proxied at /api on the same origin.
 *
 * This means no localhost URL is ever hardcoded into what actually ships --
 * see brief section 18 ("no localhost URL hardcoded into production frontend").
 */
(function () {
  function resolveApiBase() {
    var meta = document.querySelector('meta[name="sympguard-api-base"]');
    if (meta && meta.content && meta.content.trim()) {
      return meta.content.trim().replace(/\/$/, "");
    }
    var host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return "http://localhost:8000";
    }
    return window.location.origin + "/api-backend"; // adjust to your reverse-proxy path
  }

  window.SYMPGUARD_CONFIG = {
    API_BASE: resolveApiBase(),
    DEFAULT_REGION: "IN-TN",
  };
})();
