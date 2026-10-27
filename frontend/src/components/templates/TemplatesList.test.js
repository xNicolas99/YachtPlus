import { beforeEach, describe, expect, it, vi } from "vitest";
import { reactive } from "vue";
import axios from "axios";
import TemplatesList from "./TemplatesList.vue";

vi.mock("axios", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function context() {
  const vm = reactive({ ...TemplatesList.data(), readTemplates: vi.fn().mockResolvedValue([]) });
  for (const name of ["openEditDialog", "openCreateDialog", "extractError", "submitManual"]) {
    vm[name] = TemplatesList.methods[name].bind(vm);
  }
  return vm;
}

describe("template catalog editor", () => {
  it("keeps the current catalog when an earlier catalog load completes later", async () => {
    const first = deferred();
    const second = deferred();
    axios.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const vm = context();
    const earlier = vm.openEditDialog({ id: 1, title: "First" });
    const current = vm.openEditDialog({ id: 2, title: "Second" });
    second.resolve({ data: { items: [{ title: "Second item" }] } });
    await current;
    first.resolve({ data: { items: [{ title: "First item" }] } });
    await earlier;

    expect(vm.manualForm).toMatchObject({ editingId: 2, title: "Second" });
    expect(JSON.parse(vm.manualForm.content)).toEqual([{ title: "Second item" }]);
    expect(vm.manualLoading).toBe(false);
  });

  it("does not populate a new catalog from a closed editor's pending load", async () => {
    const pending = deferred();
    axios.get.mockReturnValueOnce(pending.promise);
    const vm = context();
    const request = vm.openEditDialog({ id: 1, title: "Existing" });
    vm.manualDialog = false;
    vm.openCreateDialog();
    vm.manualForm.content = "[]";
    pending.resolve({ data: { items: [{ title: "Existing item" }] } });
    await request;

    expect(vm.manualForm).toEqual({ editingId: null, title: "", content: "[]" });
    expect(vm.manualLoading).toBe(false);
  });

  it("ignores stale load errors and leaves the active load pending", async () => {
    const first = deferred();
    const second = deferred();
    axios.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const vm = context();
    const earlier = vm.openEditDialog({ id: 1, title: "First" });
    const current = vm.openEditDialog({ id: 2, title: "Second" });
    first.reject(new Error("First catalog failed"));
    await earlier;

    expect(vm.manualError).toBeNull();
    expect(vm.manualLoading).toBe(true);
    second.resolve({ data: { items: [] } });
    await current;
    expect(vm.manualLoading).toBe(false);
  });

  it("shows load failures for the current editor", async () => {
    axios.get.mockRejectedValueOnce(new Error("Catalog unavailable"));
    const vm = context();
    await vm.openEditDialog({ id: 1, title: "First" });

    expect(vm.manualError).toBe("Catalog unavailable");
    expect(vm.manualLoading).toBe(false);
  });

  it("blocks saves until the catalog has loaded and prevents duplicate saves", async () => {
    const pending = deferred();
    axios.get.mockReturnValueOnce(pending.promise);
    const vm = context();
    const load = vm.openEditDialog({ id: 1, title: "Existing" });
    await vm.submitManual();
    expect(axios.put).not.toHaveBeenCalled();
    pending.resolve({ data: { items: [] } });
    await load;
    const save = deferred();
    axios.put.mockReturnValueOnce(save.promise);
    const saving = vm.submitManual();
    await vm.submitManual();

    expect(axios.put).toHaveBeenCalledExactlyOnceWith("/templates/1/content", { title: "Existing", content: [] });
    expect(vm.manualDialog).toBe(true);
    save.resolve({});
    await saving;
    expect(vm.manualDialog).toBe(false);
  });
});
