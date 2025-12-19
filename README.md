This project is based on Yacht-sh/Yacht by wickedyoda, which is licensed under the Creative Commons Attribution 4.0 International License.

Original source: https://github.com/Yacht-sh/Yacht Copyright (c) 2025 wickedyoda

---

# YachtPlus

**YachtPlus** is a container management UI designed to simplify the deployment and management of Docker containers. It provides a user-friendly interface for managing templates, applications, and server settings.

## Features

*   **Dashboard**: Visualize CPU and memory usage of your containers.
*   **Templates**: Easily deploy applications using predefined templates.
*   **User Management**: Secure authentication with granular permissions.
*   **Two-Factor Authentication (2FA)**: Enhanced security for administrator accounts.
*   **Dark Mode**: Built-in dark theme for comfortable viewing.
*   **Projects**: Manage Docker Compose projects directly from the UI.

## Installation

### Docker CLI

You can run YachtPlus using the following command:

```bash
docker run -d \
  --name yachtplus \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v yachtplus_data:/config \
  ghcr.io/xnicolas99/yachtplus:latest
```

### Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: "3"
services:
  yachtplus:
    image: ghcr.io/xnicolas99/yachtplus:latest
    container_name: yachtplus
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - yachtplus_data:/config
    # Optional: Set PUID/PGID if needed for permissions
    # environment:
    #   - PUID=1000
    #   - PGID=1000

volumes:
  yachtplus_data:
```

Then run:

```bash
docker compose up -d
```

## Getting Started

1.  Open your browser and navigate to `http://<your-server-ip>:8000`.
2.  You will be redirected to the **Setup** wizard.
3.  Follow the instructions to create your administrator account and configure Two-Factor Authentication (2FA).
    *   *Note: 2FA is mandatory for the initial administrator account.*
4.  Once setup is complete, you can log in and start managing your containers!
