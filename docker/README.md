# AI Agent Platform — Docker Deployment

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Web/Nginx │────▶│    API      │────▶│  PostgreSQL │
│   :80       │     │   :8010     │     │   :5432     │
└─────────────┘     └─────────────┘     └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   MinIO     │
                     │   :9000     │
                     │ (Object     │
                     │  Storage)   │
                     └─────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   Worker    │
                     │  (Async     │
                     │  Downloads) │
                     └─────────────┘
```

## Quick Start

### 1. Clone and Configure

```bash
cd ai-agent
cp docker/.env.example docker/.env
# Edit docker/.env with your settings
```

### 2. Build and Start

```bash
cd docker
docker compose up -d --build
```

### 3. Verify

```bash
curl http://localhost:8010/health
# Expected: {"status":"ok"}
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Web (Nginx) | 80 | Serves React frontend + API proxy |
| API | 8010 | FastAPI backend (chat, media, auth) |
| PostgreSQL | 5432 | Relational database |
| MinIO | 9000, 9001 | Object storage (API) + Console |
| Worker | - | Background media downloader |

## Configuration

Edit `docker/.env`:

```bash
# Database
DB_PASSWORD=your_secure_password_here

# MinIO
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=media-assets
MINIO_PUBLIC_URL=http://localhost:9000/media-assets

# Agnes AI (your video/image provider)
AGNES_API_KEY=sk-your-agnes-api-key-here
AGNES_BASE_URL=https://apihub.agnes-ai.com/v1

# App
SECRET_KEY=change-this-in-production
```

## Media Flow

1. **Generation**: User sends message → Agent detects video model → Calls Agnes AI API
2. **Storage**: Worker downloads video from Agnes CDN → Stores in MinIO
3. **Database**: MediaAsset record created with MinIO object key
4. **Delivery**: Frontend requests media → API serves from MinIO (no 401!)

## Monitoring

### MinIO Console
```
http://localhost:9001
Username: minioadmin
Password: minioadmin
```

### API Health
```bash
curl http://localhost:8010/health
```

### Logs
```bash
docker compose logs -f api
docker compose logs -f worker
```

## Production Checklist

- [ ] Change all default passwords
- [ ] Set `MINIO_PUBLIC_URL` to your domain
- [ ] Configure SSL for Nginx
- [ ] Set `CORS_ORIGINS` to your frontend domain
- [ ] Use external PostgreSQL if needed
- [ ] Backup MinIO data regularly (`mc mirror`)

## Troubleshooting

### Media not loading
```bash
# Check if MinIO is running
docker compose ps minio

# Check bucket exists
docker exec ai-agent-minio mc ls local/media-assets

# Check worker logs
docker compose logs worker
```

### Video 401 error
- This is now fixed! All media is served publicly from MinIO
- No auth required for media access

### Database connection failed
```bash
docker compose restart postgres
docker compose exec api python -c "from app.core.database import engine; print(engine.url)"
```
