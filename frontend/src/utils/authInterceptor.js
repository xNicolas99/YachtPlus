// Refresh failures end the session. Errors from a retried API operation keep
// their own status and must not turn a successful refresh into a logout.
export function installAuthInterceptor(axios, store, router) {
  let refreshPromise = null;

  function clearSession() {
    store.commit("auth/AUTH_CLEAR");
    store.commit("clearUserData");
    router.push("/login");
  }

  return axios.interceptors.response.use(
    response => response,
    error => {
      if (!error.config || error.config.skipAuthRefresh || error.response?.status !== 401) {
        return Promise.reject(error);
      }

      const refreshCount = error.config._authRefreshCount || 0;
      if (refreshCount >= 1) {
        clearSession();
        return Promise.reject(error);
      }

      if (!refreshPromise) {
        refreshPromise = store.dispatch("auth/AUTH_REFRESH")
          .finally(() => { refreshPromise = null; });
      }
      return refreshPromise.then(
        () => axios({
          ...error.config,
          xsrfCookieName: "csrf_access_token",
          xsrfHeaderName: "X-CSRF-TOKEN",
          _authRefreshCount: refreshCount + 1,
        }),
        () => {
          clearSession();
          return Promise.reject(error);
        }
      );
    }
  );
}
