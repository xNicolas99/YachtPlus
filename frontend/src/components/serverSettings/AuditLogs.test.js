import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import axios from "axios";
import AuditLogs, { auditParams } from "./AuditLogs.vue";

vi.mock("axios", () => ({ default: { get: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());
function context() {
  const vm = reactive(AuditLogs.data());
  for (const [name, method] of Object.entries(AuditLogs.methods)) vm[name] = method.bind(vm);
  return vm;
}
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

describe("audit search and pagination", () => {
  it("normalizes filters and rejects reversed time ranges", () => {
    expect(auditParams({ user: " admin ", action: "", resource: "%" })).toEqual({ user: "admin", resource: "%" });
    expect(() => auditParams({ since: "2026-10-28T12:00", until: "2026-10-27T12:00" })).toThrow("From must precede Until");
  });

  it("resets pagination when applying filters and sends bounded page parameters", async () => {
    const vm = context();
    vm.page = 3;
    vm.filters.user = "admin";
    axios.get.mockResolvedValueOnce({ data: { items: [{ id: 1 }], total: 1 } });
    await vm.applyFilters();
    expect(vm.page).toBe(1);
    expect(axios.get).toHaveBeenCalledWith("/audit/entries", expect.objectContaining({ params: { user: "admin", limit: 50, offset: 0 } }));
    expect(vm.logs).toEqual([{ id: 1 }]);
  });

  it("ignores stale responses while preserving the newest results", async () => {
    const old = deferred();
    const current = deferred();
    axios.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const vm = context();
    const first = vm.fetchLogs();
    vm.page = 2;
    const second = vm.fetchLogs();
    current.resolve({ data: { items: [{ id: 2 }], total: 2 } });
    await second;
    old.resolve({ data: { items: [{ id: 1 }], total: 1 } });
    await first;
    expect(vm.logs).toEqual([{ id: 2 }]);
    expect(vm.loading).toBe(false);
  });

  it("retains previous rows and exposes a retryable failure", async () => {
    const vm = context();
    vm.logs = [{ id: 1 }];
    axios.get.mockRejectedValueOnce(new Error("network"));
    await vm.fetchLogs();
    expect(vm.logs).toEqual([{ id: 1 }]);
    expect(vm.loadError).toContain("could not be loaded");
    expect(vm.loading).toBe(false);
  });

  it("keeps applied filters separate from unsent edits", async () => {
    const vm = context();
    vm.appliedFilters = { user: "admin" };
    vm.filters.user = "unsent";
    axios.get.mockResolvedValueOnce({ data: { items: [], total: 0 } });
    await vm.changePage({ page: 2, itemsPerPage: 50 });
    expect(axios.get.mock.calls[0][1].params).toEqual({ user: "admin", limit: 50, offset: 50 });
  });
});
