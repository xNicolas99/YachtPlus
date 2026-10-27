const terminal = new Set(["succeeded", "failed", "interrupted"]);
const active = new Set(["queued", "running"]);

export function taskError(message, operationId) {
  const error = new Error(message);
  error.operationId = operationId;
  error.response = { data: { detail: message } };
  return error;
}

function validTask(value) {
  return value && typeof value.id === "string" && value.id.length > 0 &&
    (terminal.has(value.status) || active.has(value.status));
}

function delay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(taskError("Task monitoring stopped; the task continues in Tasks."));
    const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, milliseconds);
    function abort() {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(taskError("Task monitoring stopped; the task continues in Tasks."));
    }
    signal?.addEventListener("abort", abort, { once: true });
  });
}

export async function waitForOperation(client, operation, {
  interval = 1000, maxWait = 15 * 60 * 1000, onUpdate, signal,
} = {}) {
  if (!validTask(operation)) throw taskError("The server returned an invalid task.");
  const id = operation.id;
  const deadline = Date.now() + maxWait;
  while (true) {
    if (operation.id !== id || !validTask(operation)) throw taskError("The server returned an invalid task.", id);
    onUpdate?.(operation);
    if (operation.status === "succeeded") return operation;
    if (terminal.has(operation.status)) {
      throw taskError(operation.error || "Task did not complete. Open Tasks for details.", id);
    }
    if (Date.now() >= deadline) throw taskError("Monitoring timed out. The task continues in Tasks.", id);
    try {
      await delay(Math.min(interval, Math.max(0, deadline - Date.now())), signal);
    } catch (error) {
      error.operationId = id;
      throw error;
    }
    try {
      const response = await client.get(`/operations/${encodeURIComponent(id)}`, { timeout: 15000, signal });
      operation = response.data;
    } catch (error) {
      throw taskError("Could not read task status. Open Tasks to check the result before retrying.", id);
    }
  }
}

export async function runTrackedOperation(client, payload, options = {}) {
  const response = await client.post("/operations", payload, { timeout: 15000 });
  return waitForOperation(client, response.data, options);
}

export async function runTrackedDeployment(client, payload, options = {}) {
  const response = await client.post("/operations/deploy", payload, { timeout: 15000 });
  return waitForOperation(client, response.data, options);
}
