import { useEffect, useState } from 'react';
import type { Row } from '../contract';

interface PlacePhoto {
  url: string;
  authors: { displayName: string; uri?: string; photoUri?: string }[];
  source_url?: string;
}

export function usePlacePhoto(row: Row) {
  const [result, setResult] = useState<{ id: string; photo: PlacePhoto } | null>(null);
  const placeId = row.google_place_photo ? row.id : null;

  useEffect(() => {
    if (!placeId) return;
    const controller = new AbortController();
    void fetch(`/api/places/${encodeURIComponent(placeId)}/photo`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return;
        const photo: PlacePhoto = await response.json();
        if (!controller.signal.aborted) setResult({ id: placeId, photo });
      })
      .catch(() => {}); // The gradient is already rendered.
    return () => controller.abort();
  }, [placeId]);

  const google = result && result.id === placeId ? result.photo : null;
  return { url: google?.url ?? row.photo_url, google };
}
