# YachtPlus

YachtPlus is a container management UI with a focus on templates and 1-click deployments. It is an independent project based on the original `yacht-sh`.

## Features

- **Vue 3 + FastAPI**: Built with a robust modern stack.
- **Docker Management**: Manage containers, images, volumes, and networks properly.
- **Docker-Compose Support**: Create and manage Docker Compose projects directly from the UI.
- **Templates**: One-click deployment of popular applications using templates (Docker Hub integration).
- **Resources**: View and manage server resources.

## Security

YachtPlus includes several security enhancements:

- **2FA Enforcement**: Two-Factor Authentication (2FA) is mandatory for the administrator account to ensure secure access.
- **Fail2Ban-style Protection**: Automatically blocks IP addresses after 5 failed login attempts within 15 minutes.
- **Private IP Restriction**: By default, the system blocks access from non-private IP addresses to prevent accidental exposure to the public internet.
- **Secure Defaults**: No default credentials; the system requires a fresh setup upon first launch.

## Installation

### Recommended: Docker Compose

```yaml
version: "3"
services:
  yachtplus:
    image: ghcr.io/yachtplus/yachtplus:devel
    container_name: yachtplus
    restart: unless-stopped
    ports:
      - 8000:8080
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./config:/config
```

Run `docker-compose up -d`.

### Initial Setup

1. Open `http://<your-ip>:8000`.
2. Follow the setup wizard to create an administrator account.
3. **Important**: 2FA is required for the admin account.

### Important Configuration Notes

- **Volume Mounts**: You **must** mount `/var/run/docker.sock` and `/config` for the application to function correctly. Without these, you will encounter errors accessing the dashboard or managing apps.
- **DOCKER_GID**: The application attempts to automatically detect the correct Group ID for the Docker socket. However, if you experience permission errors, you can explicitly set `DOCKER_GID` in an `.env` file or your compose file.
  ```yaml
  # .env file
  DOCKER_GID=999 # Set to $(stat -c '%g' /var/run/docker.sock) on host
  ```

## Development

### Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Frontend (Vue.js)

```bash
cd frontend
npm install
npm run serve
```

## License

MIT
