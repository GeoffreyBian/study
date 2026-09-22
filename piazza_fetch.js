// Piazza resource fetch — the browser half.
//
// Piazza has no resources API (network.get_resources, network.get and
// content.get_resources all answer "Method not found"), so the listing is
// scraped from the resources page DOM. Run this with the claude-in-chrome
// javascript_tool on a tab at
//     piazza.com/<school>/<term>/<class>/resources
// while he is signed in. `piazza.py` then unpacks the result.
//
// Set SLUG and KNOWN before pasting. KNOWN comes from
//     python3 piazza.py <slug> --known
//
// Everything is packed into ONE zip download. Chrome blocks a page's second
// and later automatic downloads unless the user grants "multiple automatic
// downloads", and it blocks them silently — the first file arrives and the
// rest vanish with no error in the tool result. One download sidesteps that.
//
// The zip is written by hand with the store method (no compression): pptx and
// pdf are already deflated, so compressing again buys nothing and would mean
// shipping a deflate implementation.
//
// Return only the one-line summary. The extension blocks any tool result that
// looks like it carries cookie or query-string data, and resource metadata
// trips that heuristic.

const SLUG = "REPLACE_SLUG";
const KNOWN = []; // resource ids already filed locally

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return (buf) => {
    let c = 0xffffffff;
    for (let i = 0; i < buf.length; i++) c = t[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
})();

function zip(files) {
  const enc = new TextEncoder();
  const parts = [];
  const central = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name);
    const crc = CRC(f.data);
    const lfh = new DataView(new ArrayBuffer(30));
    lfh.setUint32(0, 0x04034b50, true);
    lfh.setUint16(4, 20, true);          // version needed
    lfh.setUint16(8, 0, true);           // method: store
    lfh.setUint32(14, crc, true);
    lfh.setUint32(18, f.data.length, true);
    lfh.setUint32(22, f.data.length, true);
    lfh.setUint16(26, name.length, true);
    parts.push(new Uint8Array(lfh.buffer), name, f.data);
    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true);
    cd.setUint16(4, 20, true);
    cd.setUint16(6, 20, true);
    cd.setUint16(10, 0, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, f.data.length, true);
    cd.setUint32(24, f.data.length, true);
    cd.setUint16(28, name.length, true);
    cd.setUint32(42, offset, true);
    central.push(new Uint8Array(cd.buffer), name);
    offset += 30 + name.length + f.data.length;
  }
  const cdSize = central.reduce((s, p) => s + p.length, 0);
  const eocd = new DataView(new ArrayBuffer(22));
  eocd.setUint32(0, 0x06054b50, true);
  eocd.setUint16(8, files.length, true);
  eocd.setUint16(10, files.length, true);
  eocd.setUint32(12, cdSize, true);
  eocd.setUint32(16, offset, true);
  return new Blob([...parts, ...central, new Uint8Array(eocd.buffer)], { type: 'application/zip' });
}

const links = [...document.querySelectorAll('a[href^="/class_profile/get_resource/"]')];

const rows = links.map((a) => {
  const row = a.closest('tr') || a.closest('[role="row"]');
  const cells = row ? [...row.children].map((c) => c.textContent.trim()) : [];
  let section = '';
  for (let p = a.parentElement; p; p = p.parentElement) {
    const h = p.querySelector && p.querySelector('h1,h2,h3,[role="heading"]');
    if (h && h.textContent.trim()) { section = h.textContent.trim(); break; }
  }
  return {
    rid: a.getAttribute('href').split('/').pop(),
    href: a.getAttribute('href'),
    title: a.textContent.trim(),
    // Resource tables are <title, date>, but only some have a date column:
    // Lecture Notes calls it "Lecture Date", Assignments a due date, and
    // General Resources has none. An absent date is not a reason to skip.
    date: cells.length > 1 ? cells[1] : '',
    inTable: !!row,
    section,
  };
});

// A link inside a pinned post has no table row and its "section" is the post
// subject; those are not course resources.
const wanted = rows.filter((r) => r.inTable && !KNOWN.includes(r.rid));

const EXT = {
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/pdf': 'pdf',
  'application/zip': 'zip',
  'text/plain': 'txt',
};

const files = [];
const manifest = [];
for (const r of wanted) {
  const res = await fetch(r.href, { credentials: 'same-origin' });
  const data = new Uint8Array(await res.arrayBuffer());
  const type = (res.headers.get('content-type') || '').split(';')[0];
  const ext = EXT[type] || (type.split('/').pop() || 'bin').replace(/[^a-z0-9]/gi, '');
  const file = `${r.rid}.${ext}`;
  files.push({ name: file, data });
  manifest.push({ ...r, file, bytes: data.length, mime: type });
}
files.push({
  name: 'manifest.json',
  data: new TextEncoder().encode(JSON.stringify({ slug: SLUG, fetched: new Date().toISOString(), items: manifest }, null, 2)),
});

const blob = zip(files);
const a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = `piazza__${SLUG}__bundle.zip`;
document.body.appendChild(a);
a.click();
a.remove();

`${manifest.length} new of ${rows.length} listed, ${Math.round(blob.size / 1048576)} MB in one zip`;
