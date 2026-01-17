# Yacht Debugging Cheatsheet

Since you've already applied the recent patches (PRs #111, #107, #104, #102) but the interface is still failing, follow this checklist to isolate the root cause.

## 1. Image Version Check

Ensure you are running the **actual** built image, not a cached stale one.

*   **Check DockerHub/GHCR SHA:** Go to the package page (e.g. `ghcr.io/yachtplus/yachtplus`) and note the SHA digest of the `latest` tag.
*   **Check Local SHA:**
    ```bash
    docker inspect --format='{{.RepoDigests}}' yachtplus
    ```
    *   *Compare:* If the hashes don't match, you are running an old version.
    *   *Fix:* `docker-compose pull && docker-compose up -d`

## 2. Build Logs Check

If you suspect the frontend code is broken (e.g. white screen), check the build logs in GitHub Actions.

*   **Action Name:** Look for `docker-image.yml` or `ghcr.yml` in the Actions tab.
*   **Step to Check:** "Build and Push" -> "Build Frontend" (or similar).
*   **What to look for:**
    *   `npm run build` success message.
    *   Any warnings about "asset size limit" (usually ignored) vs "compilation failed".
    *   Ensure `VITE_` environment variables were passed correctly if you customized them.

## 3. Container Logs Diagnostics

Run `docker logs -f yachtplus` and watch for these specific lines during startup:

### A. Docker Connection (Success)
You **must** see this specific line from `backend/api/main.py`:
```text
INFO:api.main:Docker Socket/Proxy is available.
```
*   *Failure:* If you see `CRITICAL: Failed to connect to Docker after 5 attempts`, your TCP socket proxy is unreachable. Check firewall/network.

### B. Scheduler Lock (Success)
To confirm only one worker runs background tasks:
```text
INFO:api.main:Scheduler Lock acquired. Starting Scheduler...
```
(Only one worker will say this; others will say `Scheduler Lock already held...`. This is normal.)

### C. JS/Nginx Errors
*   *Nginx:* Look for `[error] ... open() "/app/static/..." failed (2: No such file or directory)`. This means the frontend build artifacts were not copied to `/app/static`.

## 4. Browser DevTools Checklist

Open Chrome/Firefox DevTools (F12):

### A. Console Tab
*   **Red Errors:**
    *   `Refused to evaluate a string as JavaScript`: CSP violation (check if `unsafe-eval` is properly allowed in headers).
    *   `404 Not Found` for `.js` or `.css` files: The frontend build failed or path is wrong.
    *   `Uncaught SyntaxError`: Broken JS bundle.

### B. Network Tab
Filter by `XHR` or `Fetch`. reload the page.
*   **Check `/api/setup/status` (or similar):**
    *   **403 Forbidden:** The `check_setup_status` middleware is blocking you. This is expected if setup isn't done, but the UI should redirect you to `/setup`.
    *   **502 Bad Gateway:** Nginx is running, but Python Backend (Gunicorn) is dead/crashing. Check container logs immediately.
    *   **504 Gateway Timeout:** Python is hanging (likely trying to connect to Docker socket synchronously and timing out).

## 5. The "Nuclear Option" (Clean Rebuild)

If weird caching or corrupt volumes are suspected, wipe everything and start fresh.

**WARNING: This deletes your Yacht configuration and database!**

```bash
# 1. Stop containers
docker-compose down

# 2. Remove the image (force pull next time)
docker rmi ghcr.io/yachtplus/yachtplus:latest

# 3. Prune volumes (DANGER: Deletes data)
# Verify the volume name first with 'docker volume ls'
docker volume rm yacht_config

# 4. Pull and Start
docker-compose pull
docker-compose up -d
```
