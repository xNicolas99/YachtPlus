import { describe, expect, it, vi } from "vitest";
import axios from "axios";
import { installAuthInterceptor } from "./authInterceptor";

function harness(adapter) {
  const client = axios.create({ adapter });
  const store = {
    dispatch: vi.fn().mockResolvedValue({}),
    commit: vi.fn(),
  };
  const router = { push: vi.fn() };
  installAuthInterceptor(client, store, router);
  return { client, store, router };
}

function failure(config, status) {
  return new axios.AxiosError(`Request failed: ${status}`, "ERR_BAD_RESPONSE", config,
    undefined, { status, data: { detail: `Error ${status}` }, config });
}

describe("authentication response interceptor", () => {
  it.each([403, 404, 500])("preserves a retried API error (%s) without logging out", async status => {
    const adapter = vi.fn(config => Promise.reject(failure(config, adapter.mock.calls.length === 1 ? 401 : status)));
    const { client, store, router } = harness(adapter);

    await expect(client.get("/apps/")).rejects.toMatchObject({ response: { status } });

    expect(adapter).toHaveBeenCalledTimes(2);
    expect(store.dispatch).toHaveBeenCalledExactlyOnceWith("auth/AUTH_REFRESH");
    expect(store.commit).not.toHaveBeenCalled();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("clears the session if the repeated request is still unauthorized without another refresh", async () => {
    const adapter = vi.fn(config => Promise.reject(failure(config, 401)));
    const { client, store, router } = harness(adapter);

    await expect(client.get("/apps/")).rejects.toMatchObject({ response: { status: 401 } });

    expect(adapter).toHaveBeenCalledTimes(2);
    expect(store.dispatch).toHaveBeenCalledExactlyOnceWith("auth/AUTH_REFRESH");
    expect(store.commit.mock.calls).toEqual([["auth/AUTH_CLEAR"], ["clearUserData"]]);
    expect(router.push).toHaveBeenCalledExactlyOnceWith("/login");
  });

  it("clears the session when refresh fails and never repeats the operation", async () => {
    const adapter = vi.fn(config => Promise.reject(failure(config, 401)));
    const { client, store, router } = harness(adapter);
    store.dispatch.mockRejectedValueOnce(new Error("Session expired"));

    await expect(client.get("/apps/")).rejects.toMatchObject({ response: { status: 401 } });

    expect(adapter).toHaveBeenCalledOnce();
    expect(store.commit.mock.calls).toEqual([["auth/AUTH_CLEAR"], ["clearUserData"]]);
    expect(router.push).toHaveBeenCalledExactlyOnceWith("/login");
  });

  it("shares a pending refresh across concurrent failures and retries both operations", async () => {
    let finishRefresh;
    const refresh = new Promise(resolve => { finishRefresh = resolve; });
    const adapter = vi.fn(config => config._authRefreshCount
      ? Promise.resolve({ status: 200, data: config.url, config })
      : Promise.reject(failure(config, 401)));
    const { client, store } = harness(adapter);
    store.dispatch.mockReturnValueOnce(refresh);
    const first = client.get("/apps/");
    const second = client.get("/compose/");
    await vi.waitFor(() => expect(store.dispatch).toHaveBeenCalledOnce());
    finishRefresh({});

    expect((await Promise.all([first, second])).map(response => response.data)).toEqual(["/apps/", "/compose/"]);
    expect(store.dispatch).toHaveBeenCalledOnce();
    expect(store.commit).not.toHaveBeenCalled();
  });

  it("honors the explicit refresh opt-out", async () => {
    const adapter = vi.fn(config => Promise.reject(failure(config, 401)));
    const { client, store } = harness(adapter);

    await expect(client.post("/auth/refresh", {}, { skipAuthRefresh: true })).rejects.toMatchObject({ response: { status: 401 } });

    expect(store.dispatch).not.toHaveBeenCalled();
    expect(store.commit).not.toHaveBeenCalled();
  });
});
