<template>
  <div class="yp-page backups-page">
    <PageHeader title="Volume backups" subtitle="Verified archives, daily schedules and restoration into a new volume.">
      <template #actions><v-btn prepend-icon="mdi-refresh" :loading="loading" :disabled="loading" @click="refresh">Refresh</v-btn></template>
    </PageHeader>
    <v-alert v-if="error" type="error" role="alert" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="notice" type="success" role="status" class="mb-4">{{ notice }}</v-alert>
    <v-alert type="info" class="mb-5">
      Stop an application's writes before taking a consistent backup. Live backups are only crash-consistent
      and require explicit acknowledgement. Infrastructure volumes, custom volume drivers/options, links and
      special files are excluded. Archives remain on this server; copy the backup storage off-host for disaster recovery.
      Restoring creates a separate volume and never replaces an existing volume.
    </v-alert>

    <v-card class="mb-5">
      <v-card-title>Create a backup</v-card-title>
      <v-card-text>
        <v-select v-model="selectedVolume" :items="volumes" item-title="name" item-value="name"
          :item-props="volumeProps" label="Source volume" :disabled="loading || submitting" hide-details="auto" />
        <p v-if="source?.running_containers?.length" class="mt-3">
          Running applications: {{ source.running_containers.join(', ') }}.
        </p>
        <v-checkbox v-model="confirmLive" :disabled="submitting"
          label="I accept that a backup of a running application may require application-specific recovery" />
        <v-btn color="primary" prepend-icon="mdi-content-save-outline" :loading="submitting"
          :disabled="!canCreate || submitting" @click="createBackup">Create backup</v-btn>
      </v-card-text>
    </v-card>

    <v-card class="mb-5">
      <v-card-title class="d-flex flex-wrap align-center ga-3">Archives <v-chip size="small">{{ total }}</v-chip></v-card-title>
      <v-data-table-server :headers="archiveHeaders" :items="archives" :items-length="total" :loading="loading"
        :items-per-page="pageSize" :page="page" @update:page="changePage" :items-per-page-options="[pageSize]" item-value="id">
        <template #item.created_at="{ item }">{{ formatDate(item.created_at) }}</template>
        <template #item.status="{ item }"><v-chip size="small" :color="statusColor(item.status)">{{ item.status }}</v-chip></template>
        <template #item.size_bytes="{ item }">{{ formatSize(item.size_bytes) }}</template>
        <template #item.actions="{ item }">
          <div class="d-flex flex-wrap ga-1">
            <v-btn size="small" variant="text" :disabled="item.status !== 'completed'" @click="openRestore(item)">Restore</v-btn>
            <v-btn v-if="item.operation_id" size="small" variant="text" :to="`/tasks?operation=${encodeURIComponent(item.operation_id)}`">Task</v-btn>
            <v-btn size="small" variant="text" color="error" :disabled="['queued', 'running'].includes(item.status)" @click="deleting = item">Delete</v-btn>
          </div>
        </template>
        <template #expanded-row="{ item }"><tr><td :colspan="archiveHeaders.length">{{ item.error }}</td></tr></template>
        <template #no-data>No archives yet. Choose an application volume to create your first backup.</template>
      </v-data-table-server>
      <v-card-text v-if="archives.some(item => item.error)"><p v-for="item in archives.filter(item => item.error)" :key="item.id" class="text-error">{{ item.volume }}: {{ item.error }}</p></v-card-text>
    </v-card>

    <v-card>
      <v-card-title>Daily backup schedules</v-card-title>
      <v-card-text>
        <p class="mb-4">Times are UTC. Retention applies to completed archives for the selected volume, including manual backups. Schedules run while YachtPlus is available.</p>
        <v-row>
          <v-col cols="12" md="4"><v-select v-model="schedule.volume" :items="volumes" item-title="name" item-value="name" :item-props="volumeProps" label="Volume" :disabled="scheduleSaving" /></v-col>
          <v-col cols="6" md="2"><v-text-field v-model.number="schedule.hour_utc" type="number" min="0" max="23" label="Hour (UTC)" :disabled="scheduleSaving" /></v-col>
          <v-col cols="6" md="2"><v-text-field v-model.number="schedule.minute_utc" type="number" min="0" max="59" label="Minute" :disabled="scheduleSaving" /></v-col>
          <v-col cols="12" md="4"><v-text-field v-model.number="schedule.retain_count" type="number" min="1" max="30" label="Archives to keep (1–30)" :disabled="scheduleSaving" /></v-col>
        </v-row>
        <v-checkbox v-model="schedule.enabled" label="Enable daily backup" :disabled="scheduleSaving" />
        <v-checkbox v-model="schedule.confirm_live" label="Allow crash-consistent live backups for this schedule" :disabled="scheduleSaving" />
        <v-btn color="primary" :loading="scheduleSaving" :disabled="!scheduleValid || scheduleSaving" @click="saveSchedule">Save schedule</v-btn>
      </v-card-text>
      <v-table>
        <thead><tr><th>Volume</th><th>Daily (UTC)</th><th>Keep</th><th>Status</th><th>Last attempt</th><th>Actions</th></tr></thead>
        <tbody><tr v-for="item in schedules" :key="item.id">
          <td>{{ item.volume }}</td><td>{{ pad(item.hour_utc) }}:{{ pad(item.minute_utc) }}</td>
          <td>{{ item.retain_count }}</td><td>{{ item.enabled ? 'Enabled' : 'Disabled' }}<p v-if="item.last_error" class="text-error">{{ item.last_error }}</p></td><td>{{ formatDate(item.last_run_at) }}</td>
          <td><v-btn size="small" variant="text" :disabled="scheduleSaving" @click="editSchedule(item)">Edit</v-btn><v-btn size="small" variant="text" color="error" :disabled="scheduleSaving" @click="scheduleToDelete = item">Delete</v-btn></td>
        </tr><tr v-if="!schedules.length"><td colspan="6">No backup schedules configured.</td></tr></tbody>
      </v-table>
    </v-card>

    <v-dialog v-model="restoreDialog" max-width="640" :persistent="restoring">
      <v-card>
        <v-card-title>Restore volume backup</v-card-title>
        <v-card-text>
          <p class="mb-3">{{ restoreArchive?.volume }} · {{ formatDate(restoreArchive?.created_at) }} · {{ formatSize(restoreArchive?.size_bytes) }}</p>
          <p class="mb-4">Step {{ restoreStep }} of 3: {{ restoreStep === 1 ? 'Choose a new destination' : restoreStep === 2 ? 'Review verified archive' : 'Restoration submitted' }}</p>
          <v-text-field v-if="restoreStep < 3" v-model="targetVolume" label="New volume name" :disabled="verifying || restoring" @update:model-value="invalidatePreview" />
          <v-alert v-if="restoreError" type="error" role="alert" class="mb-3">{{ restoreError }}</v-alert>
          <template v-if="restorePreview && restoreStep === 2">
            <v-alert type="success" class="mb-3">Checksum and archive paths verified. {{ restorePreview.entry_count }} entries will be restored into {{ restorePreview.target_volume }}.</v-alert>
            <p>Files are restored with UID/GID 1000:1000. After completion, configure your application to use the new volume and verify its data before switching traffic.</p>
            <v-checkbox v-model="restoreConfirmed" :disabled="restoring" label="Create this new volume and restore the verified archive" />
          </template>
          <v-alert v-if="restoreStep === 3" type="info">Restoration continues in Tasks. Existing volumes have not been changed.</v-alert>
        </v-card-text>
        <v-card-actions>
          <v-btn :disabled="restoring" @click="restoreDialog = false">{{ restoreStep === 3 ? 'Close' : 'Cancel' }}</v-btn>
          <v-spacer />
          <v-btn v-if="restoreStep === 1" color="primary" :loading="verifying" :disabled="!validTarget || verifying" @click="verifyRestore">Verify archive</v-btn>
          <v-btn v-if="restoreStep === 2" color="primary" :loading="restoring" :disabled="!restoreConfirmed || restoring" @click="restoreBackup">Restore to new volume</v-btn>
          <v-btn v-if="restoreStep === 3" color="primary" :to="`/tasks?operation=${encodeURIComponent(restoreOperation || '')}`">Open task</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog :model-value="!!deleting" max-width="480" :persistent="deleteBusy" @update:model-value="value => { if (!value && !deleteBusy) deleting = null; }">
      <v-card><v-card-title>Delete backup?</v-card-title><v-card-text>Delete the archive of {{ deleting?.volume }} from {{ formatDate(deleting?.created_at) }}? Application data is unaffected.</v-card-text><v-card-actions><v-btn :disabled="deleteBusy" @click="deleting = null">Cancel</v-btn><v-spacer /><v-btn color="error" :loading="deleteBusy" :disabled="deleteBusy" @click="deleteBackup">Delete archive</v-btn></v-card-actions></v-card>
    </v-dialog>
    <v-dialog :model-value="!!scheduleToDelete" max-width="480" :persistent="scheduleSaving" @update:model-value="value => { if (!value && !scheduleSaving) scheduleToDelete = null; }">
      <v-card><v-card-title>Delete backup schedule?</v-card-title><v-card-text>Daily backups for {{ scheduleToDelete?.volume }} will stop. Existing archives remain available.</v-card-text><v-card-actions><v-btn :disabled="scheduleSaving" @click="scheduleToDelete = null">Cancel</v-btn><v-spacer /><v-btn color="error" :loading="scheduleSaving" :disabled="scheduleSaving" @click="deleteSchedule">Delete schedule</v-btn></v-card-actions></v-card>
    </v-dialog>
  </div>
</template>

<script>
import axios from 'axios';
import PageHeader from '@/components/PageHeader.vue';

const newSchedule = () => ({ volume: '', enabled: false, hour_utc: 2, minute_utc: 0, retain_count: 7, confirm_live: false });
const nameValid = value => /^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$/.test(value || '');

export default {
  name: 'VolumeBackups',
  components: { PageHeader },
  data() {
    return {
      volumes: [], archives: [], schedules: [], total: 0, page: 1, pageSize: 25,
      loading: false, error: '', notice: '', selectedVolume: '', confirmLive: false, submitting: false,
      schedule: newSchedule(), scheduleSaving: false, scheduleToDelete: null,
      restoreDialog: false, restoreArchive: null, restoreStep: 1, targetVolume: '', restorePreview: null,
      restoreConfirmed: false, restoreError: '', verifying: false, restoring: false, restoreOperation: null,
      deleting: null, deleteBusy: false, generation: 0, pollTimer: null, disposed: false, loadController: null,
      archiveHeaders: [
        { title: 'Volume', key: 'volume', sortable: false }, { title: 'Created', key: 'created_at', sortable: false },
        { title: 'Status', key: 'status', sortable: false }, { title: 'Size', key: 'size_bytes', sortable: false }, { title: 'Actions', key: 'actions', sortable: false },
      ],
    };
  },
  computed: {
    source() { return this.volumes.find(volume => volume.name === this.selectedVolume); },
    canCreate() {
      return this.source?.allowed === true && Array.isArray(this.source.running_containers)
        && (!this.source.running_containers.length || this.confirmLive);
    },
    validTarget() { return nameValid(this.targetVolume); },
    scheduleValid() {
      return nameValid(this.schedule.volume) && Number.isInteger(this.schedule.hour_utc) && this.schedule.hour_utc >= 0 && this.schedule.hour_utc <= 23
        && Number.isInteger(this.schedule.minute_utc) && this.schedule.minute_utc >= 0 && this.schedule.minute_utc <= 59
        && Number.isInteger(this.schedule.retain_count) && this.schedule.retain_count >= 1 && this.schedule.retain_count <= 30;
    },
  },
  mounted() {
    this.refresh();
    document.addEventListener('visibilitychange', this.visibilityChanged);
    this.pollTimer = setInterval(() => { if (!document.hidden && !this.loading && this.archives.some(row => ['queued', 'running'].includes(row.status))) this.refresh(); }, 3000);
  },
  beforeUnmount() {
    this.disposed = true;
    this.generation++;
    this.loadController?.abort();
    clearInterval(this.pollTimer);
    document.removeEventListener('visibilitychange', this.visibilityChanged);
  },
  methods: {
    volumeProps(item) {
      if (!item || typeof item !== 'object' || !Array.isArray(item.running_containers)) {
        return { disabled: true, subtitle: 'Volume information is unavailable' };
      }
      return { disabled: item.allowed !== true, subtitle: item.reason || (item.running_containers.length ? 'In use by a running application' : 'No running application') };
    },
    visibilityChanged() { if (!document.hidden) this.refresh(); },
    async refresh() {
      const generation = ++this.generation;
      this.loadController?.abort();
      const controller = new AbortController();
      this.loadController = controller;
      const config = { signal: controller.signal, timeout: 15000 };
      this.loading = true;
      try {
        const [volumes, archives, schedules] = await Promise.all([
          axios.get('/backups/volumes', config), axios.get('/backups', { ...config, params: { limit: this.pageSize, offset: (this.page - 1) * this.pageSize } }), axios.get('/backups/schedules', config),
        ]);
        if (this.disposed || generation !== this.generation) return;
        this.volumes = volumes.data.items;
        this.archives = archives.data.items;
        this.total = archives.data.total;
        this.schedules = schedules.data.items;
        this.error = '';
      } catch (error) {
        if (!this.disposed && generation === this.generation) this.error = this.errorText(error, 'Backups could not be loaded.');
      } finally {
        if (generation === this.generation) this.loading = false;
      }
    },
    async changePage(value) { this.page = value; await this.refresh(); },
    async createBackup() {
      if (!this.canCreate || this.submitting) return;
      this.submitting = true; this.notice = ''; this.error = '';
      try {
        await axios.post('/backups', { volume: this.selectedVolume, confirm_live: this.confirmLive });
        this.notice = 'Backup submitted. Its progress is available in Tasks.';
        await this.refresh();
      } catch (error) { this.error = this.errorText(error, 'Backup could not be created.'); }
      finally { this.submitting = false; }
    },
    editSchedule(item) { this.schedule = { volume: item.volume, enabled: item.enabled, hour_utc: item.hour_utc, minute_utc: item.minute_utc, retain_count: item.retain_count, confirm_live: item.confirm_live }; },
    async saveSchedule() {
      if (!this.scheduleValid || this.scheduleSaving) return;
      this.scheduleSaving = true; this.error = ''; this.notice = '';
      const { volume, ...payload } = this.schedule;
      try {
        await axios.put(`/backups/schedules/${encodeURIComponent(volume)}`, payload);
        this.notice = 'Backup schedule saved.';
        await this.refresh();
      } catch (error) { this.error = this.errorText(error, 'Schedule could not be saved.'); }
      finally { this.scheduleSaving = false; }
    },
    async deleteSchedule() {
      if (!this.scheduleToDelete || this.scheduleSaving) return;
      this.scheduleSaving = true;
      try { await axios.delete(`/backups/schedules/${encodeURIComponent(this.scheduleToDelete.volume)}`); this.scheduleToDelete = null; await this.refresh(); }
      catch (error) { this.error = this.errorText(error, 'Schedule could not be deleted.'); }
      finally { this.scheduleSaving = false; }
    },
    openRestore(item) {
      this.restoreArchive = item; this.targetVolume = ''; this.restorePreview = null;
      this.restoreConfirmed = false; this.restoreError = ''; this.restoreStep = 1; this.restoreOperation = null; this.restoreDialog = true;
    },
    invalidatePreview() { this.restorePreview = null; this.restoreConfirmed = false; this.restoreStep = 1; },
    async verifyRestore() {
      if (!this.validTarget || this.verifying) return;
      const archive = this.restoreArchive;
      const target = this.targetVolume;
      this.verifying = true; this.restoreError = '';
      try {
        const response = await axios.post(`/backups/${archive.id}/restore/preview`, { target_volume: target });
        if (!this.restoreDialog || this.restoreArchive !== archive || this.targetVolume !== target) return;
        this.restorePreview = response.data; this.restoreStep = 2;
      } catch (error) {
        if (this.restoreDialog && this.restoreArchive === archive && this.targetVolume === target) this.restoreError = this.errorText(error, 'Archive verification failed.');
      }
      finally { this.verifying = false; }
    },
    async restoreBackup() {
      if (!this.restoreConfirmed || !this.restorePreview || this.restoring || this.targetVolume !== this.restorePreview.target_volume) return;
      this.restoring = true; this.restoreError = '';
      try {
        const response = await axios.post(`/backups/${this.restoreArchive.id}/restore`, { target_volume: this.targetVolume, confirm_new_volume: true });
        this.restoreOperation = response.data.operation_id; this.restoreStep = 3;
      } catch (error) { this.restoreError = this.errorText(error, 'Restoration could not be started.'); }
      finally { this.restoring = false; }
    },
    async deleteBackup() {
      if (!this.deleting || this.deleteBusy) return;
      this.deleteBusy = true;
      try { await axios.delete(`/backups/${this.deleting.id}`); this.deleting = null; await this.refresh(); }
      catch (error) { this.error = this.errorText(error, 'Backup could not be deleted.'); }
      finally { this.deleteBusy = false; }
    },
    errorText(error, fallback) { const detail = error?.response?.data?.detail; return typeof detail === 'string' ? detail : fallback; },
    statusColor(status) { return { completed: 'success', failed: 'error', running: 'info', queued: 'warning' }[status] || 'default'; },
    formatDate(value) { return value ? new Date(value).toLocaleString() : '—'; },
    formatSize(value) { if (value == null) return '—'; return value >= 1048576 ? `${(value / 1048576).toFixed(1)} MiB` : `${(value / 1024).toFixed(1)} KiB`; },
    pad(value) { return String(value).padStart(2, '0'); },
  },
};
</script>

<style scoped>
.backups-page { width: 100%; }
</style>
