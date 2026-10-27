import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import UpdatePlans from "./UpdatePlans.vue";

vi.mock("axios", () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const plan = (values = {}) => ({
  project_name: "demo", configured: false, project_exists: true, enabled: false, excluded: false,
  weekdays: [0, 1, 2, 3, 4, 5, 6], window_start_hour: 0, window_end_hour: 24, cadence_days: 1,
  last_run: null, last_status: "never", last_error: null, last_operation_id: null, next_due: null,
  ...values,
});
const response = (row = plan(), legacy = false) => ({ data: { items: [row], legacy_auto_update: legacy, timezone: "UTC" } });
function context() {
  const vm = UpdatePlans.data();
  for (const [name, method] of Object.entries(UpdatePlans.methods)) vm[name] = method.bind(vm);
  for (const [name, getter] of Object.entries(UpdatePlans.computed)) Object.defineProperty(vm, name, { get: () => getter.call(vm) });
  return vm;
}

beforeEach(() => vi.resetAllMocks());

describe("project update plans", () => {
  it("starts disabled, loads UTC project state and never saves an implicit plan", async () => {
    axios.get.mockResolvedValueOnce(response());
    const vm = context();
    expect(vm.form.enabled).toBe(false);
    await vm.fetchPlans();
    expect(axios.get).toHaveBeenCalledWith("/update-plans");
    expect(vm.selectedProject).toBe("demo");
    expect(vm.form.enabled).toBe(false);
    expect(vm.dirty).toBe(false);
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("saves only schedule fields and retains the server's persistent result", async () => {
    axios.get.mockResolvedValueOnce(response());
    axios.put.mockResolvedValueOnce({ data: plan({ configured: true, enabled: true, weekdays: [0], window_start_hour: 22, window_end_hour: 2, last_status: "succeeded" }) });
    const vm = context();
    await vm.fetchPlans();
    Object.assign(vm.form, { enabled: true, weekdays: [0], window_start_hour: 22, window_end_hour: 2 });
    expect(vm.dirty).toBe(true);
    await vm.savePlan();
    expect(axios.put).toHaveBeenCalledWith("/update-plans/demo", {
      enabled: true, excluded: false, weekdays: [0], window_start_hour: 22, window_end_hour: 2, cadence_days: 1,
    });
    expect(vm.selectedPlan.last_status).toBe("succeeded");
    expect(vm.dirty).toBe(false);
  });

  it("turns off the enabled draft when excluded and saves the exclusion", async () => {
    axios.get.mockResolvedValueOnce(response(plan({ configured: true, enabled: true })));
    axios.put.mockResolvedValueOnce({ data: plan({ configured: true, excluded: true }) });
    const vm = context();
    await vm.fetchPlans();
    vm.form.excluded = true;
    vm.excludeChanged(true);
    expect(vm.form.enabled).toBe(false);
    await vm.savePlan();
    expect(axios.put.mock.calls[0][1].excluded).toBe(true);
  });

  it.each([
    { weekdays: [] }, { cadence_days: 0 }, { cadence_days: 1.5 }, { window_start_hour: 2, window_end_hour: 2 },
  ])("prevents invalid window submissions: %j", async changes => {
    axios.get.mockResolvedValueOnce(response());
    const vm = context();
    await vm.fetchPlans();
    Object.assign(vm.form, changes);
    await vm.savePlan();
    expect(vm.validationError).not.toBe("");
    expect(axios.put).not.toHaveBeenCalled();
  });

  it("retains unsaved values after save failure and blocks duplicate submissions", async () => {
    axios.get.mockResolvedValueOnce(response());
    let rejectSave;
    axios.put.mockReturnValueOnce(new Promise((_, reject) => { rejectSave = reject; }));
    const vm = context();
    await vm.fetchPlans();
    vm.form.enabled = true;
    const pending = vm.savePlan();
    await vm.savePlan();
    expect(axios.put).toHaveBeenCalledOnce();
    rejectSave({ response: { data: { detail: "Administrator permission required" } } });
    await pending;
    expect(vm.form.enabled).toBe(true);
    expect(vm.selectedPlan.enabled).toBe(false);
    expect(vm.error).toBe("Administrator permission required");
  });

  it("rejects malformed results without resetting a draft or inventing success", async () => {
    axios.get.mockResolvedValueOnce(response());
    axios.put.mockResolvedValueOnce({ data: {} });
    const vm = context();
    await vm.fetchPlans();
    vm.form.enabled = true;
    await vm.savePlan();
    expect(vm.form.enabled).toBe(true);
    expect(vm.error).toContain("Could not save");
  });

  it("keeps unavailable projects read-only while permitting removal of their stored plan", async () => {
    axios.get.mockResolvedValueOnce(response(plan({ configured: true, project_exists: false })));
    const vm = context();
    await vm.fetchPlans();
    await vm.savePlan();
    expect(vm.formDisabled).toBe(true);
    expect(axios.put).not.toHaveBeenCalled();
    axios.delete.mockResolvedValueOnce({ data: { deleted: true } });
    axios.get.mockResolvedValueOnce({ data: { items: [], legacy_auto_update: false, timezone: "UTC" } });
    await vm.resetPlan();
    expect(axios.delete).toHaveBeenCalledWith("/update-plans/demo");
    expect(vm.plans).toEqual([]);
  });

  it("restores global behavior only after the explicit reset action", async () => {
    axios.get.mockResolvedValueOnce(response(plan({ configured: true, excluded: true }), true));
    const vm = context();
    await vm.fetchPlans();
    expect(vm.legacyAutoUpdate).toBe(true);
    expect(axios.delete).not.toHaveBeenCalled();
    vm.resetDialog = true;
    axios.delete.mockResolvedValueOnce({ data: { deleted: true } });
    axios.get.mockResolvedValueOnce(response(plan(), true));
    await vm.resetPlan();
    expect(vm.selectedPlan.configured).toBe(false);
    expect(vm.resetDialog).toBe(false);
  });

  it("offers a clean retry after a load failure and preserves drafts on refresh", async () => {
    axios.get.mockRejectedValueOnce(new Error("offline"));
    const vm = context();
    await vm.fetchPlans();
    expect(vm.loaded).toBe(false);
    expect(vm.error).toContain("Could not load");
    axios.get.mockResolvedValueOnce(response());
    await vm.fetchPlans();
    vm.form.cadence_days = 7;
    await vm.fetchPlans();
    expect(axios.get).toHaveBeenCalledTimes(2);
    expect(vm.form.cadence_days).toBe(7);
  });

  it("formats server timestamps as UTC, including SQLite timestamps without offsets", () => {
    const vm = context();
    expect(vm.formatTime("2026-10-26T23:00:00")).toBe("2026-10-26 23:00:00 UTC");
    expect(vm.formatTime("2026-10-27T01:00:00+02:00")).toBe("2026-10-26 23:00:00 UTC");
    expect(vm.formatTime(null)).toBe("None");
    expect(vm.formatTime("broken")).toBe("Unavailable");
  });
});
