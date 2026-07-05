"""
Frontend Adaptation Guide —新媒体 URL 格式适配

This document provides step-by-step instructions for adapting the frontend
to work with the new object storage architecture.

## Overview

Before:
- Frontend used external CDN URLs directly: `https://platform-outputs.agnes-ai.space/...`
- Backend proxied these via `/api/media/proxy?url=...` (which required auth = 401)

After:
- Media is stored in local MinIO
- Frontend accesses via public endpoints:
  - `/api/media/assets/{asset_id}` (by DB ID)
  - `/api/media/assets/by-key/{object_key}` (by storage key)
  - Or directly from MinIO: `/media-assets/{path}`

## Steps to Adapt

### 1. Update MediaCard Component

**File:** `web/src/components/MediaCard/index.tsx`

**Before:**
```tsx
// Used external URLs or proxy endpoint
const imageUrl = msg.blocks?.image_url;
const videoUrl = msg.blocks?.video_url;

// If it's an external URL, use proxy
<img src={proxyMediaUrl(imageUrl)} />
```

**After:**
```tsx
// Now use direct URLs from stored blocks
// Blocks now contain { stored_video_url: "/media-assets/media/2026/07/05/xxx.mp4" }
const imageUrl = msg.blocks?.image_url;
const storedVideoUrl = msg.blocks?.stored_video_url;

// No proxy needed — direct access to MinIO or Nginx proxy
<img src={imageUrl} />
<video src={storedVideoUrl} />
```

### 2. Update media.ts Service

**File:** `web/src/services/media.ts`

**Before:**
```typescript
export function proxyMediaUrl(url: string): string {
    if (url.startsWith('http')) {
        return `/api/media/proxy?url=${encodeURIComponent(url)}`;
    }
    return url;
}
```

**After:**
```typescript
// Simply return the URL as-is — no proxying needed
export function proxyMediaUrl(url: string): string {
    return url;  // Already stored internally
}

// Optional: Add direct MinIO access helper
export function getDirectMediaUrl(objectKey: string): string {
    return `/media-assets/${objectKey}`;
}
```

### 3. Update ChatInterface

**File:** `web/src/pages/ChatInterface/index.tsx`

Check the video block structure:
- Old: `{ video_url: "https://platform-outputs.agnes-ai.space/..." }`
- New: `{ stored_video_url: "/media-assets/media/2026/07/05/xxx.mp4" }`

No other changes needed — the SSE status update logic remains the same.

### 4. Verify CORS (if MinIO is separate)

If accessing MinIO directly from browser, ensure CORS is configured:
```bash
mc ilm config set local/media-assets '{"Version":"2020-01-01","Rule":[{"Expiration":{"Days":365},"ID":"cleanup-old-media","Filter":{"Prefix":""},"Status":"Enabled"}]}'
```

Or use the Nginx proxy (recommended):
```nginx
location /media-assets/ {
    proxy_pass http://minio:9000/;
    proxy_set_header Host $host;
    add_header Access-Control-Allow-Origin *;
}
```