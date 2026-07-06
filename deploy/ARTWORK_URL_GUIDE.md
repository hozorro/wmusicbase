# Artwork Static File URL Guide

This document describes how to use the new static file URLs for artwork in the frontend.

## Overview

Artwork files are now pre-generated as static files and served directly by nginx (production) or FastAPI (development). The frontend should use the new URL format with `cover_art_hash` for cache invalidation.

## URL Format

### Artist Artwork

| Type | Old URL | New URL |
|------|---------|---------|
| Face | `/artwork/artist/{id}?img_cate=face` | `/media/artists/{id}_face.jpg?v={face_art_hash}` |
| Portrait | `/artwork/artist/{id}?img_cate=portrait` | `/media/artists/{id}_portrait.jpg?v={portrait_art_hash}` |

### Album Artwork

| Old URL | New URL |
|---------|---------|
| `/artwork/album/{id}` | `/media/albums/{id}.jpg?v={cover_art_hash}` |

### Track Artwork

| Old URL | New URL |
|---------|---------|
| `/artwork/track/{id}` | `/media/tracks/{id}.jpg?v={cover_art_hash}` |

### Playlist Artwork

| Old URL | New URL |
|---------|---------|
| `/artwork/playlist/{id}` | `/media/playlists/{id}.jpg?v={cover_art_hash}` |

## Frontend Implementation Examples

### JavaScript/TypeScript

```typescript
// Artist face image
function getArtistFaceUrl(artist: Artist): string {
  return `/media/artists/${artist.id}_face.jpg?v=${artist.face_art_hash || 'default'}`;
}

// Artist portrait image
function getArtistPortraitUrl(artist: Artist): string {
  return `/media/artists/${artist.id}_portrait.jpg?v=${artist.portrait_art_hash || 'default'}`;
}

// Album cover
function getAlbumCoverUrl(album: Album): string {
  return `/media/albums/${album.id}.jpg?v=${album.cover_art_hash || 'default'}`;
}

// Track cover
function getTrackCoverUrl(track: Track): string {
  return `/media/tracks/${track.id}.jpg?v=${track.cover_art_hash || 'default'}`;
}

// Playlist cover
function getPlaylistCoverUrl(playlist: Playlist): string {
  return `/media/playlists/${playlist.id}.jpg?v=${playlist.cover_art_hash || 'default'}`;
}
```

### React Component Example

```tsx
interface ArtistAvatarProps {
  artist: Artist;
  size?: 'small' | 'medium' | 'large';
}

function ArtistAvatar({ artist, size = 'medium' }: ArtistAvatarProps) {
  const sizeMap = { small: 64, medium: 128, large: 256 };
  const pixelSize = sizeMap[size];
  
  const imageUrl = `/media/artists/${artist.id}_face.jpg?v=${artist.face_art_hash || 'default'}`;
  
  return (
    <img
      src={imageUrl}
      alt={artist.name}
      width={pixelSize}
      height={pixelSize}
      style={{ borderRadius: '50%' }}
      loading="lazy"
    />
  );
}
```

### Vue Component Example

```vue
<template>
  <img
    :src="imageUrl"
    :alt="artist.name"
    :width="size"
    :height="size"
    style="border-radius: 50%"
    loading="lazy"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Artist } from '@/types';

const props = defineProps<{
  artist: Artist;
  size?: number;
}>();

const imageUrl = computed(() => 
  `/media/artists/${props.artist.id}_face.jpg?v=${props.artist.face_art_hash || 'default'}`
);
</script>
```

## Cache Invalidation

The `v={hash}` query parameter triggers cache invalidation when the artwork changes:

1. **Normal request**: Browser caches the image with the hash
2. **Artwork updated**: Backend updates `face_art_hash` / `portrait_art_hash` / `cover_art_hash`
3. **Frontend detects change**: New hash in URL = new request = fresh image
4. **nginx cache**: Set to 1 year with `immutable` flag for optimal performance

## Workbox/PWA Integration

If using Workbox for service worker caching:

```javascript
// workbox-config.js
module.exports = {
  runtimeCaching: [
    {
      urlPattern: /^https:\/\/your-domain\.com\/media\//,
      handler: 'CacheFirst',
      options: {
        cacheName: 'artwork-cache',
        expiration: {
          maxEntries: 500,
          maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
        },
      },
    },
  ],
};
```

## Fallback Handling

If the static file doesn't exist (404), the frontend should display a default image:

```typescript
function handleImageError(event: React.SyntheticEvent<HTMLImageElement>) {
  const img = event.currentTarget;
  img.src = '/media/default/artist_face.jpg'; // or appropriate default
}

<img 
  src={imageUrl} 
  onError={handleImageError}
  alt="Artist"
/>
```

## Migration Checklist

- [ ] Update artist API response to include `face_art_hash` and `portrait_art_hash`
- [ ] Update all frontend components using artist artwork
- [ ] Update all frontend components using album artwork
- [ ] Update all frontend components using track artwork
- [ ] Update all frontend components using playlist artwork
- [ ] Run artwork pre-generation script: `python -m app.scripts.generate_artworks`
- [ ] Configure nginx with the new static file location
- [ ] Test cache invalidation by updating an artwork
