import { beforeEach, describe, expect, it, vi } from 'vitest';
import { reactive } from 'vue';
import axios from 'axios';
import Backups from './Backups.vue';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
beforeEach(() => vi.resetAllMocks());

function context() {
  const vm = reactive(Backups.data());
  for (const [name, method] of Object.entries(Backups.methods)) vm[name] = method.bind(vm);
  for (const [name, getter] of Object.entries(Backups.computed)) Object.defineProperty(vm, name, { get: () => getter.call(vm) });
  return vm;
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

describe('volume backups', () => {
  it.each([null, undefined, '', {}, { name: 'data' }, { name: 'data', allowed: true }])(
    'safely renders an unresolved volume selection (%j)', item => {
      const vm = context();
      expect(vm.volumeProps(item)).toEqual({ disabled: true, subtitle: 'Volume information is unavailable' });
    },
  );

  it('does not allow a backup until the selected volume inventory is complete', () => {
    const vm = context();
    vm.selectedVolume = 'data';
    vm.confirmLive = true;
    expect(vm.canCreate).toBe(false);
    vm.volumes = [{ name: 'data', allowed: true }];
    expect(vm.canCreate).toBe(false);
    vm.volumes = [{ name: 'data', allowed: true, running_containers: [] }];
    expect(vm.canCreate).toBe(true);
  });

  it('requires acknowledgement for live backups and excludes protected volumes', () => {
    const vm = context();
    vm.volumes = [{ name: 'data', allowed: true, running_containers: ['db'] }, { name: 'config', allowed: false, running_containers: [] }];
    vm.selectedVolume = 'data';
    expect(vm.canCreate).toBe(false);
    vm.confirmLive = true;
    expect(vm.canCreate).toBe(true);
    vm.selectedVolume = 'config';
    expect(vm.canCreate).toBe(false);
  });

  it('preserves the latest archive page when an earlier load finishes later', async () => {
    const vm = context();
    const earlier = deferred();
    const current = deferred();
    axios.get.mockImplementation((url, config) => url === '/backups'
      ? (config.params.offset ? current.promise : earlier.promise)
      : Promise.resolve({ data: { items: [] } }));
    const first = vm.refresh();
    vm.page = 2;
    const second = vm.refresh();
    current.resolve({ data: { items: [{ id: 'new' }], total: 60 } });
    await second;
    earlier.resolve({ data: { items: [{ id: 'old' }], total: 60 } });
    await first;
    expect(vm.archives).toEqual([{ id: 'new' }]);
    expect(vm.page).toBe(2);
    expect(vm.loading).toBe(false);
  });

  it('verifies the chosen target and invalidates confirmation when it changes', async () => {
    const vm = context();
    vm.openRestore({ id: 'archive', volume: 'source' });
    vm.targetVolume = 'new-data';
    axios.post.mockResolvedValueOnce({ data: { target_volume: 'new-data', checksum_verified: true, entry_count: 3 } });
    await vm.verifyRestore();
    expect(axios.post).toHaveBeenCalledWith('/backups/archive/restore/preview', { target_volume: 'new-data' });
    expect(vm.restoreStep).toBe(2);
    vm.restoreConfirmed = true;
    vm.targetVolume = 'different';
    vm.invalidatePreview();
    expect(vm.restorePreview).toBeNull();
    expect(vm.restoreConfirmed).toBe(false);
    expect(vm.restoreStep).toBe(1);
  });

  it('ignores an archive verification response after another restore dialog opens', async () => {
    const vm = context();
    const pending = deferred();
    axios.post.mockReturnValueOnce(pending.promise);
    vm.openRestore({ id: 'old' });
    vm.targetVolume = 'new-data';
    const request = vm.verifyRestore();
    vm.openRestore({ id: 'current' });
    pending.resolve({ data: { target_volume: 'new-data', checksum_verified: true } });
    await request;
    expect(vm.restoreArchive.id).toBe('current');
    expect(vm.restorePreview).toBeNull();
    expect(vm.restoreStep).toBe(1);
  });

  it('requires a current verified target and prevents duplicate restore submissions', async () => {
    const vm = context();
    vm.openRestore({ id: 'archive' });
    vm.targetVolume = 'new-data';
    await vm.restoreBackup();
    expect(axios.post).not.toHaveBeenCalled();
    vm.restorePreview = { target_volume: 'new-data', checksum_verified: true };
    vm.restoreConfirmed = true;
    const pending = deferred();
    axios.post.mockReturnValueOnce(pending.promise);
    const first = vm.restoreBackup();
    await vm.restoreBackup();
    expect(axios.post).toHaveBeenCalledExactlyOnceWith('/backups/archive/restore', { target_volume: 'new-data', confirm_new_volume: true });
    pending.resolve({ data: { operation_id: 'operation' } });
    await first;
    expect(vm.restoreStep).toBe(3);
    expect(vm.restoreOperation).toBe('operation');
  });

  it('keeps deletion confirmation open when deleting the archive fails', async () => {
    const vm = context();
    vm.deleting = { id: 'archive' };
    axios.delete.mockRejectedValueOnce({ response: { data: { detail: 'Restoration is pending' } } });
    await vm.deleteBackup();
    expect(vm.deleting).toEqual({ id: 'archive' });
    expect(vm.error).toBe('Restoration is pending');
    expect(vm.deleteBusy).toBe(false);
  });

  it('validates and saves an explicit UTC schedule without leaking extra model fields', async () => {
    const vm = context();
    vm.schedule = { volume: 'data', enabled: true, hour_utc: 2, minute_utc: 15, retain_count: 7, confirm_live: true };
    expect(vm.scheduleValid).toBe(true);
    vm.refresh = vi.fn().mockResolvedValue();
    axios.put.mockResolvedValueOnce({ data: {} });
    await vm.saveSchedule();
    expect(axios.put).toHaveBeenCalledExactlyOnceWith('/backups/schedules/data', { enabled: true, hour_utc: 2, minute_utc: 15, retain_count: 7, confirm_live: true });
    vm.schedule.hour_utc = 24;
    expect(vm.scheduleValid).toBe(false);
    vm.schedule.hour_utc = 2;
    vm.schedule.retain_count = 0;
    expect(vm.scheduleValid).toBe(false);
  });
});
