# YachtPlus

YachtPlus is a container management UI with a focus on templates and 1-click deployments.

## Features

- **Vue 2 + FastAPI**: Built with a robust modern stack.
- **Docker Management**: Manage containers, images, volumes, and networks properly.
- **Docker-Compose Support**: Create and manage Docker Compose projects (formerly "Projects") directly from the UI.
- **Templates**: One-click deployment of popular applications using templates (Docker Hub integration).
- **Resources**: View and manage server resources.

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
      - 8000:8000
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./config:/config
```

Run `docker-compose up -d`.

### Initial Setup

1. Open `http://<your-ip>:8000`.
2. Follow the setup wizard to create an administrator account.
3. **Important**: 2FA is required for the admin account.

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
