import indexHtml from './index.html';

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function ssrEvents(eventsData) {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = [];

  for (const [, venue] of Object.entries(eventsData.venues || {})) {
    for (const e of (venue.events || [])) {
      const dateStr = (e.start_datetime || '').slice(0, 10);
      if (dateStr >= today) {
        upcoming.push({ ...e, venueName: venue.name, venueAddress: venue.address });
      }
    }
  }

  upcoming.sort((a, b) => (a.start_datetime || '').localeCompare(b.start_datetime || ''));

  return upcoming.map(e => {
    const date = e.start_datetime
      ? new Date(e.start_datetime + 'Z').toLocaleDateString('en-US', {
          weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'America/New_York',
        })
      : '';
    const time = e.time ? ' · ' + e.time : '';
    const subtitle = e.subtitle ? ` — ${escHtml(e.subtitle)}` : '';
    const admission = e.admission ? ` · ${escHtml(e.admission)}` : '';
    const titleHtml = e.event_url
      ? `<a href="${escHtml(e.event_url)}">${escHtml(e.title)}</a>`
      : escHtml(e.title);

    return `<article data-venue="${escHtml(e.venueName)}">
  <time datetime="${escHtml(e.start_datetime || '')}">${escHtml(date)}${escHtml(time)}</time>
  <h2>${titleHtml}${subtitle}</h2>
  <p>${escHtml(e.venueName)}${e.venueAddress ? ' · ' + escHtml(e.venueAddress) : ''}${admission}</p>
</article>`;
  }).join('\n');
}

function jsonLdEvents(eventsData) {
  const today = new Date().toISOString().slice(0, 10);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() + 90);
  const cutoffStr = cutoff.toISOString().slice(0, 10);

  const events = [];
  for (const [, venue] of Object.entries(eventsData.venues || {})) {
    for (const e of (venue.events || [])) {
      const dateStr = (e.start_datetime || '').slice(0, 10);
      if (dateStr >= today && dateStr <= cutoffStr) {
        const event = {
          '@type': 'MusicEvent',
          'name': e.title,
          'startDate': e.start_datetime,
          'location': {
            '@type': 'MusicVenue',
            'name': venue.name,
            'address': {
              '@type': 'PostalAddress',
              'streetAddress': venue.address,
              'addressRegion': 'NC',
              'addressCountry': 'US',
            },
          },
          'organizer': {
            '@type': 'Organization',
            'name': venue.name,
            'url': venue.events_url || '',
          },
        };
        if (e.end_datetime) event.endDate = e.end_datetime;
        if (e.event_url) event.url = e.event_url;
        if (e.subtitle) event.description = e.subtitle;
        if (e.admission) event.offers = {
          '@type': 'Offer',
          'description': e.admission,
          'url': e.event_url || venue.events_url || '',
        };
        events.push(event);
      }
    }
  }

  events.sort((a, b) => (a.startDate || '').localeCompare(b.startDate || ''));

  return JSON.stringify({ '@context': 'https://schema.org', '@graph': events });
}

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

      let eventsData;
      try { eventsData = JSON.parse(eventsJson); } catch { eventsData = {}; }

      const ldJson = jsonLdEvents(eventsData);
      const ssrHtml = ssrEvents(eventsData);

      let injected = indexHtml.replace(
        '<head>',
        `<head>\n<script>window.__EVENTS__=${eventsJson};window.__GENRES__=${JSON.stringify(genreMap)};</script>\n<script type="application/ld+json">${ldJson}</script>`
      );
      injected = injected.replace(
        '<div id="event-list" hidden></div>',
        `<div id="event-list" hidden>${ssrHtml}</div>`
      );

      return new Response(injected, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-cache',
        },
      });
    }

    if (path === '/robots.txt') {
      const robots = `User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: DuckDuckBot
Allow: /

User-agent: Twitterbot
Allow: /

User-agent: facebookexternalhit
Allow: /

User-agent: LinkedInBot
Allow: /

User-agent: Slackbot
Allow: /

User-agent: *
Disallow: /

Sitemap: https://nctrianglemusic.live/sitemap.xml
`;
      return new Response(robots, {
        headers: {
          'Content-Type': 'text/plain',
          'Cache-Control': 'public, max-age=86400',
        },
      });
    }

    if (path === '/sitemap.xml') {
      const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://nctrianglemusic.live/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>`;
      return new Response(sitemap, {
        headers: {
          'Content-Type': 'application/xml',
          'Cache-Control': 'public, max-age=3600',
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
