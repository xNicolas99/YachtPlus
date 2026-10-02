import {
  AUTH_REQUEST,
  AUTH_ERROR,
  AUTH_SUCCESS,
  AUTH_LOGOUT,
  AUTH_REFRESH,
  AUTH_CLEAR,
  AUTH_CHANGE_PASS,
  AUTH_CHECK,
  AUTH_DISABLED,
  AUTH_ENABLED
} from "../actions/auth";
import axios from "axios";
import router from "@/router/index";
let refreshPromise = null;

const state = {
  status: "",
  username: localStorage.getItem("username") || "",
  authDisabled: null,
  // Three-valued: true once we've seen setup is done, false once we've
  // confirmed it isn't, null while we don't know yet. Persisted in
  // localStorage so a reload while gunicorn is mid-boot (or any other
  // transient /setup/status failure) doesn't yank a finished install
  // back into the wizard. The backend remains the source of truth — we
  // never UPGRADE to true on our own, only the live API response does.
  isSetup: localStorage.getItem("yp_isSetup") === "true" ? true : null,
  setupStep: 1, // Setup Wizard Step
  setupSecret: null, // Temporary storage for 2FA secret
  setupQrCode: null, // Temporary storage for QR Code
};

const getters = {
  isAuthenticated: state => !!state.username,
  authStatus: state => state.status,
  getUsername: state => state.username,
  isSetup: state => state.isSetup,
  authDisabled: state => state.authDisabled,
  setupStep: state => state.setupStep,
  setupQrCode: state => state.setupQrCode
};

const actions = {
  [AUTH_REQUEST]: ({ commit }, credentials) => {
    return new Promise((resolve, reject) => {
      commit(AUTH_REQUEST);
      const url = "/auth/login_cookie";

      // Fix: Backend expects 'username', but Login.vue sends 'email'.
      // If username is missing but email exists, map it.
      // Verified: This mapping is required for OAuth2PasswordRequestForm compatibility.
      if (credentials.email && !credentials.username) {
        credentials.username = credentials.email;
      }

      axios
        .post(url, credentials, { withCredentials: true })
        .then(resp => {
          localStorage.setItem("username", resp.data.username);
          axios.defaults.withCredentials = true;
          axios.defaults.xsrfCookieName = "csrf_access_token";
          axios.defaults.xsrfHeaderName = "X-CSRF-TOKEN";
          commit(AUTH_SUCCESS, resp);
          resolve(resp);
        })
        .catch(err => {
          // Log full error server-side (console), but show generic message to user
          console.error("[AUTH_REQUEST] Error (logs only):", err.response?.data);

          commit(AUTH_ERROR, err);
          // Don't show raw error payload to user
          commit("snackbar/setErr", new Error("Authentication failed. Please check your credentials."), { root: true });
          localStorage.removeItem("username");
          reject(new Error("Authentication failed. Please check your credentials."));
        });
    });
  },

  [AUTH_LOGOUT]: async ({ commit }) => {
    try {
      await axios.post("/auth/logout", {}, { withCredentials: true, skipAuthRefresh: true });
    } catch (error) {
      console.warn("[AUTH_LOGOUT] Server logout failed; clearing local session.", error);
    } finally {
      commit(AUTH_CLEAR);
      commit("clearUserData", null, { root: true });
      await router.push({ path: "/login" });
    }
  },
  [AUTH_REFRESH]: () => {
    // Let failures reject so the caller can stop retrying and clear the
    // session. Suppress the response interceptor on this request itself.
    if (refreshPromise) return refreshPromise;
    refreshPromise = axios.post("/auth/refresh", {}, {
      xsrfCookieName: "csrf_access_token",
      xsrfHeaderName: "X-CSRF-TOKEN",
      withCredentials: true,
      skipAuthRefresh: true,
      timeout: 15000
    }).finally(() => { refreshPromise = null; });
    return refreshPromise;
  },
  [AUTH_CHANGE_PASS]: async ({ commit }, credentials) => {
    commit(AUTH_REQUEST);
    try {
      const resp = await axios.post("/auth/me", credentials);
      commit(AUTH_CLEAR);
      commit("clearUserData", null, { root: true });
      await router.push({ path: "/login" });
      return resp;
    } catch (err) {
      commit(AUTH_ERROR);
      throw err;
    }
  },
  [AUTH_CHECK]: ({ commit, dispatch }) => {
    commit(AUTH_REQUEST);
    // Also check setup status
    return dispatch("CHECK_SETUP").then(() => {
      const url = "/auth/me";
      return axios
        .get(url, { skipAuthRefresh: true, withCredentials: true })
        .then(resp => {
          // Restore axios defaults for subsequent requests
          axios.defaults.withCredentials = true;
          axios.defaults.xsrfCookieName = "csrf_access_token";
          axios.defaults.xsrfHeaderName = "X-CSRF-TOKEN";

          if (resp.data.authDisabled == true) {
            commit(AUTH_DISABLED);
            commit(AUTH_SUCCESS, resp);
          } else {
            commit(AUTH_ENABLED);
            // If we are here, we are actually logged in, but we need to update state
            // The original code was a bit vague. If /api/auth/me returns 200, it returns user info.
            // We should treat it as success.
            commit(AUTH_SUCCESS, resp);
          }
          localStorage.setItem("username", resp.data.username);
          return true;
        })
        .catch(err => {
          // If 401, we are not logged in.
          // Do not redirect here (router handles that), just update state.
          if (err.response && err.response.status === 401) {
            commit(AUTH_CLEAR);
            commit(AUTH_ERROR);
          } else {
            // Other errors
            commit(AUTH_ERROR);
          }
          return false;
        });
    });
  },
  CHECK_SETUP: ({ commit, state }) => {
    return axios
      .get("/setup/status")
      .then(resp => {
        commit("SET_SETUP_STATUS", resp.data.is_setup);
        return resp.data.is_setup;
      })
      .catch(err => {
        // The previous behaviour was to commit `isSetup=false` on ANY
        // error — including transient 502s while gunicorn was booting,
        // or a bad cookie that 401's the request. That bounced finished
        // installs straight into the setup wizard. We now:
        //   - keep the last known value if we have one (cached from
        //     localStorage or a previous successful call),
        //   - only fall back to false when we have no prior signal at
        //     all (genuine first run).
        console.warn("Setup check failed; keeping last known state.", err);
        if (state.isSetup === null) {
          commit("SET_SETUP_STATUS", false);
          return false;
        }
        return state.isSetup;
      });
  },

  // SETUP ACTIONS
  SETUP_REGISTER: ({ commit }, user) => {
    return axios.post("/setup/register", user)
      .then(resp => {
        commit("SET_SETUP_STEP", 2);
        return resp;
      });
  },

  SETUP_2FA_GENERATE: ({ commit }) => {
    return axios.post("/auth/2fa/generate")
      .then(resp => {
        commit("SET_SETUP_SECRET", resp.data);
        return resp;
      });
  },

  SETUP_2FA_ENABLE: ({ commit, state }, code) => {
    return axios.post("/auth/2fa/enable", {
      secret: state.setupSecret,
      code: code
    })
      .then(resp => {
        commit("SET_SETUP_STEP", 3);
        return resp;
      });
  },

  SETUP_FINALIZE: ({ commit }) => {
    return axios.post("/setup/finalize")
      .then(resp => {
        commit("SET_SETUP_STATUS", true);
        return resp;
      });
  }
};

const mutations = {
  [AUTH_REQUEST]: state => {
    state.status = "loading";
  },
  SET_SETUP_STATUS: (state, isSetup) => {
    state.isSetup = isSetup;
    // Cache the "setup is done" signal across reloads so a transient
    // /setup/status failure on the very next boot doesn't drop us back
    // into the wizard. We only persist the `true` signal — a `false`
    // result is volatile (could be a server hiccup) and shouldn't
    // poison the cache.
    try {
      if (isSetup === true) {
        localStorage.setItem("yp_isSetup", "true");
      } else if (isSetup === false) {
        localStorage.removeItem("yp_isSetup");
      }
    } catch (_) {
      // localStorage can throw in private-browsing on some browsers.
    }
  },
  SET_SETUP_STEP: (state, step) => {
    state.setupStep = step;
  },
  SET_SETUP_SECRET: (state, data) => {
    state.setupSecret = data.secret;
    state.setupQrCode = data.qr_code;
  },
  [AUTH_SUCCESS]: (state, resp) => {
    state.status = "success";
    state.username = resp.data.username;
    if (resp.data.authDisabled) {
      state.authDisabled = true;
    }
  },
  [AUTH_ERROR]: state => {
    state.status = "error";
  },
  [AUTH_DISABLED]: state => {
    state.authDisabled = true;
  },
  [AUTH_ENABLED]: state => {
    state.authDisabled = false;
  },
  [AUTH_CLEAR]: state => {
    state.accessToken = "";
    state.refreshToken = "";
    state.username = "";
    state.authDisabled = null;
    state.status = "";
    state.setupSecret = null;
    state.setupQrCode = null;
    state.setupStep = 1;
    localStorage.removeItem("username");
  }
};

export default {
  namespaced: true,
  state,
  mutations,
  getters,
  actions
};
