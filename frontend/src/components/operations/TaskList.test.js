import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import axios from "axios";
import TaskList from "./TaskList.vue";

vi.mock("axios", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function context() {
  const vm = reactive({ ...TaskList.data(), $store: { commit: vi.fn() } });
  for (const [name, method] of Object.entries(TaskList.methods)) vm[name] = method.bind(vm);
  return vm;
}

describe("task overview", () => {
  it("opens task links from backup and update pages by operation query", async () => {
    axios.get.mockResolvedValue({ data: { id: "linked", status: "succeeded" } });
    const vm = context();
    await TaskList.watch["$route.query.operation"].handler.call(vm, "linked");
    expect(vm.selected.id).toBe("linked");
    expect(vm.detailsOpen).toBe(true);
    expect(axios.get).toHaveBeenCalledExactlyOnceWith("/operations/linked", { timeout: 15000 });
  });

  it("does not reopen a closed details dialog after a slow linked task response", async () => {
    const response = deferred();
    axios.get.mockReturnValueOnce(response.promise);
    const vm = context();
    const pending = vm.openRequested("linked");
    vm.closeDetails();
    response.resolve({ data: { id: "linked", status: "succeeded" } });
    await pending;
    expect(vm.selected).toBeNull();
    expect(vm.detailsOpen).toBe(false);
  });

  it("loads a filtered server page without client-side truncation", async () => {
    axios.get.mockResolvedValue({ data: { items: [{ id: "one" }], total: 80 } });
    const vm = context();
    vm.status = "failed";
    vm.page = 3;
    await vm.load();
    expect(axios.get).toHaveBeenCalledExactlyOnceWith("/operations", {
      params: { status: "failed", limit: 25, offset: 50 }, timeout: 15000,
    });
    expect(vm.total).toBe(80);
    expect(vm.lastUpdated).toBeTruthy();
  });

  it("ignores responses from superseded list requests", async () => {
    const earlier = deferred();
    const current = deferred();
    axios.get.mockReturnValueOnce(earlier.promise).mockReturnValueOnce(current.promise);
    const vm = context();
    const first = vm.load();
    vm.status = "failed";
    const second = vm.load();
    current.resolve({ data: { items: [{ id: "current" }], total: 1 } });
    await second;
    earlier.resolve({ data: { items: [{ id: "old" }], total: 100 } });
    await first;
    expect(vm.items).toEqual([{ id: "current" }]);
    expect(vm.total).toBe(1);
  });

  it("keeps old results visibly stale after a failed request", async () => {
    axios.get.mockRejectedValue(new Error("offline"));
    const vm = context();
    vm.items = [{ id: "last-good" }];
    await vm.load();
    expect(vm.items).toEqual([{ id: "last-good" }]);
    expect(vm.error).toContain("out of date");
    expect(vm.loading).toBe(false);
  });

  it("does not overwrite a newly selected task with an older details response", async () => {
    const detail = deferred();
    axios.get.mockResolvedValueOnce({ data: { items: [], total: 0 } }).mockReturnValueOnce(detail.promise);
    const vm = context();
    vm.open({ id: "old" });
    const loading = vm.load();
    await vi.waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    vm.open({ id: "new" });
    detail.resolve({ data: { id: "old", status: "succeeded" } });
    await loading;
    expect(vm.selected.id).toBe("new");
  });

  it("prevents duplicate retries and opens the new task", async () => {
    const response = deferred();
    axios.post.mockReturnValueOnce(response.promise);
    axios.get.mockResolvedValue({ data: { items: [{ id: "new-task", status: "queued" }], total: 1 } });
    const vm = context();
    vm.open({ id: "failed-task", retryable: true });
    const retry = vm.retry();
    await vm.retry();
    expect(axios.post).toHaveBeenCalledOnce();
    response.resolve({ data: { id: "new-task", status: "queued" } });
    await retry;
    expect(vm.selected.id).toBe("new-task");
    expect(vm.retrying).toBe(false);
  });
});
