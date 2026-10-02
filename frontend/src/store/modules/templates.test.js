import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import templates from "./templates";

vi.mock("axios", () => ({ default: { post: vi.fn() } }));
vi.mock("@/router/index", () => ({ default: { push: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

describe("writeTemplateVariables", () => {
  it("returns the request promise and stores the successful server response", async () => {
    const commit = vi.fn();
    const payload = [{ variable: "directory", replacement: "/data" }];
    axios.post.mockResolvedValueOnce({ data: payload });

    const request = templates.actions.writeTemplateVariables({ commit }, payload);
    expect(request).toBeInstanceOf(Promise);
    await expect(request).resolves.toEqual(payload);
    expect(axios.post).toHaveBeenCalledWith("/settings/variables", payload, {});
    expect(commit).toHaveBeenCalledWith("setTemplateVariables", payload);
    expect(commit).toHaveBeenLastCalledWith("setLoading", false);
  });

  it("rejects failed writes after reporting the error and clears loading", async () => {
    const commit = vi.fn();
    const error = new Error("write failed");
    axios.post.mockRejectedValueOnce(error);

    await expect(templates.actions.writeTemplateVariables({ commit }, [])).rejects.toBe(error);
    expect(commit).toHaveBeenCalledWith("snackbar/setErr", error, { root: true });
    expect(commit).not.toHaveBeenCalledWith("setTemplateVariables", expect.anything());
    expect(commit).toHaveBeenLastCalledWith("setLoading", false);
  });
});
