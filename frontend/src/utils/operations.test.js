import { afterEach, describe, expect, it, vi } from "vitest";
import { runTrackedOperation, runTrackedDeployment, waitForOperation } from "./operations";

const task = (status, extra = {}) => ({ id: "task-123", status, phase: status, ...extra });
afterEach(() => vi.useRealTimers());

describe("persistent task monitoring", () => {
  it("submits once, follows real phases and stops after success", async () => {
    const client = {
      post: vi.fn().mockResolvedValue({ data: task("queued") }),
      get: vi.fn().mockResolvedValueOnce({ data: task("running", { phase: "Pulling images" }) })
        .mockResolvedValueOnce({ data: task("succeeded") }),
    };
    const onUpdate = vi.fn();
    const payload = { kind: "compose.action", action: "update", resource: "web" };
    const result = await runTrackedOperation(client, payload, { interval: 0, onUpdate });

    expect(client.post).toHaveBeenCalledExactlyOnceWith("/operations", payload, { timeout: 15000 });
    expect(client.get).toHaveBeenCalledTimes(2);
    expect(result.status).toBe("succeeded");
    expect(onUpdate.mock.calls.map(([value]) => value.phase)).toEqual(["queued", "Pulling images", "succeeded"]);
  });

  it.each(["failed", "interrupted"])("surfaces %s without silently resubmitting the operation", async status => {
    const client = {
      post: vi.fn().mockResolvedValue({ data: task("queued") }),
      get: vi.fn().mockResolvedValue({ data: task(status, { error: "Verify the resource state." }) }),
    };
    await expect(runTrackedOperation(client, {}, { interval: 0 })).rejects.toMatchObject({
      operationId: "task-123", response: { data: { detail: "Verify the resource state." } },
    });
    expect(client.post).toHaveBeenCalledOnce();
    expect(client.get).toHaveBeenCalledOnce();
  });

  it("preserves preflight errors before a job exists", async () => {
    const error = { response: { status: 409, data: { conflicts: ["port"] } } };
    const client = { post: vi.fn().mockRejectedValue(error), get: vi.fn() };
    await expect(runTrackedDeployment(client, { name: "web" })).rejects.toBe(error);
    expect(client.post).toHaveBeenCalledExactlyOnceWith("/operations/deploy", { name: "web" }, { timeout: 15000 });
    expect(client.get).not.toHaveBeenCalled();
  });

  it("bounds monitoring while leaving the server task running", async () => {
    const client = { get: vi.fn(), post: vi.fn() };
    await expect(waitForOperation(client, task("running"), { maxWait: 0 })).rejects.toMatchObject({
      operationId: "task-123", message: expect.stringContaining("continues in Tasks"),
    });
    expect(client.get).not.toHaveBeenCalled();
    expect(client.post).not.toHaveBeenCalled();
  });

  it("cancels monitoring without issuing a server cancellation or retry", async () => {
    const controller = new AbortController();
    const client = { get: vi.fn(), post: vi.fn() };
    const result = waitForOperation(client, task("running"), { signal: controller.signal });
    controller.abort();
    await expect(result).rejects.toMatchObject({ operationId: "task-123", message: expect.stringContaining("continues in Tasks") });
    expect(client.get).not.toHaveBeenCalled();
    expect(client.post).not.toHaveBeenCalled();
  });

  it("reports an ambiguous network failure with the task ID and no resubmission", async () => {
    const client = { get: vi.fn().mockRejectedValue(new Error("offline")), post: vi.fn() };
    await expect(waitForOperation(client, task("running"), { interval: 0 })).rejects.toMatchObject({
      operationId: "task-123", message: expect.stringContaining("check the result before retrying"),
    });
    expect(client.post).not.toHaveBeenCalled();
  });

  it.each([{}, { id: "one", status: "unknown" }])("rejects malformed task responses", async response => {
    await expect(waitForOperation({}, response)).rejects.toThrow("invalid task");
  });

  it("rejects a poll response for a different task", async () => {
    const client = { get: vi.fn().mockResolvedValue({ data: task("succeeded", { id: "wrong" }) }) };
    await expect(waitForOperation(client, task("running"), { interval: 0 })).rejects.toThrow("invalid task");
  });
});
