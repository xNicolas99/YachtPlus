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

const state = {
  status: "",
  username: localStorage.getItem("username") || "",
  authDisabled: null,
  isSetup: false // Default to false to ensure check is performed
};

const getters = {
  isAuthenticated: state => !!state.username,
  authStatus: state => state.status,
  getUsername: state => state.username,
  isSetup: state => state.isSetup
};

const actions = {
  [AUTH_REQUEST]: ({ commit }, credentials) => {
    return new Promise((resolve, reject) => {
      commit(AUTH_REQUEST);
      const url = "/auth/login";

      // Fix: Backend expects 'username', but Login.vue sends 'email'.
      // If username is missing but email exists, map it.
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

  [AUTH_LOGOUT]: ({ commit }) => {
    return new Promise(resolve => {
      commit(AUTH_REQUEST);
      const url = "/auth/logout";
      axios
        .get(url, {}, { withCredentials: true })
        .then(resp => {
          let rurl = "/auth/logout/refresh";
          axios
            .get(
              rurl,
              {},
              {
                xsrfCookieName: "csrf_refresh_token",
                xsrfHeaderName: "X-CSRF-TOKEN",
                withCredentials: true
              }
            )
            .then(resp => {
              commit(AUTH_CLEAR, resp);
              localStorage.removeItem("username");
              router.push({ path: "/" });
              resolve(resp);
            });

          resolve(resp);
        })
        .catch(error => {
          console.error(error);
          commit(AUTH_CLEAR);
        });
    });
  },
  [AUTH_REFRESH]: ({ commit }) => {
    return new Promise(resolve => {
      commit(AUTH_REQUEST);
      const url = "/auth/refresh";
      axios
        .post(
          url,
          {},
          {
            xsrfCookieName: "csrf_refresh_token",
            xsrfHeaderName: "X-CSRF-TOKEN",
            withCredentials: true
          }
        )
        .then(resp => {
          resolve(resp);
        })
        .catch(error => {
          console.error(error);
          commit(AUTH_CLEAR);
        });
    });
  },
  [AUTH_CHANGE_PASS]: ({ commit }, credentials) => {
    return new Promise((resolve, reject) => {
      commit(AUTH_REQUEST);
      const url = "/auth/me";
      axios
        .post(url, credentials)
        .then(resp => {
          localStorage.setItem("username", resp.data.username);
          commit(AUTH_SUCCESS, resp);
          resolve(resp);
        })
        .finally(() => {
          router.push({ path: `/user/info` });
        })
        .catch(err => {
          reject(err);
        });
    });
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
            localStorage.setItem("username", resp.data.username);
            commit(AUTH_DISABLED);
            commit(AUTH_SUCCESS, resp);
          } else {
            commit(AUTH_ENABLED);
            // If we are here, we are actually logged in, but we need to update state
            // The original code was a bit vague. If /api/auth/me returns 200, it returns user info.
            // We should treat it as success.
            commit(AUTH_SUCCESS, resp);
          }
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
        });
    });
  },
  CHECK_SETUP: ({ commit }) => {
    return axios
      .get("/setup/status")
      .then(resp => {
        commit("SET_SETUP_STATUS", resp.data.is_setup);
      })
      .catch(err => {
        console.error("Setup check failed", err);
        // If check fails (e.g. network error), we might want to fail safe.
        // But if 404, it means setup endpoint missing? No, 404 handled above.
        // If 403, it means... disallowed?
        // Let's assume if check fails, we keep isSetup as false (safe) or true?
        // If we keep it as false, user is redirected to setup.
        // If backend is down, setup page won't work either.
        // But if 404 (endpoint not found), it implies old version?
        commit("SET_SETUP_STATUS", false);
      });
  }
};

const mutations = {
  [AUTH_REQUEST]: state => {
    state.status = "loading";
  },
  SET_SETUP_STATUS: (state, isSetup) => {
    state.isSetup = isSetup;
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
  }
};

export default {
  namespaced: true,
  state,
  mutations,
  getters,
  actions
};
