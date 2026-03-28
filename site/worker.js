import indexHtml from './index.html';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/' || path === '/index.html') {
      const [eventsObj, artistsObj] = await Promise.all([
        env.DATA_BUCKET.get('live_music_events.json'),
        env.DATA_BUCKET.get('artists_db.json'),
      ]);

      if (!eventsObj) return new Response('Data unavailable', { status: 503 });

      let eventsJson;
      try {
        eventsJson = await eventsObj.text();
      } catch (err) {
        console.error('[worker] Failed to read live_music_events.json:', err);
        return new Response('Data unavailable', { status: 503 });
      }

      let genreMap = {};
      if (artistsObj) {
        try {
          const artists = JSON.parse(await artistsObj.text());
          for (const [slug, data] of Object.entries(artists)) {
            if (data.genre?.length) genreMap[slug] = data.genre;
          }
        } catch (err) {
          console.error('[worker] Failed to parse artists_db.json:', err);
        }
      } else {
        console.error('[worker] artists_db.json not found in R2 — serving without genre data');
      }

      const injected = indexHtml.replace(
        '<head>',
        `<head>\n<script>window.__EVENTS__=${eventsJson};window.__GENRES__=${JSON.stringify(genreMap)};</script>`
      );

      return new Response(injected, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-cache',
        },
      });
    }

    if (path === '/og-image.svg') {
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#0e0e14"/>
  <rect x="0" y="0" width="8" height="630" fill="#8b7cf8"/>
  <text x="80" y="260" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="72" font-weight="700" fill="#e2e2ec">NC Triangle</text>
  <text x="80" y="350" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="72" font-weight="700" fill="#8b7cf8">Live Music</text>
  <text x="80" y="430" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="32" fill="#7878a0">Raleigh · Durham · Chapel Hill</text>
  <text x="80" y="560" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="28" fill="#4a4a68">nctrianglemusic.live</text>
</svg>`;
      return new Response(svg, {
        headers: {
          'Content-Type': 'image/svg+xml',
          'Cache-Control': 'public, max-age=86400',
        },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
