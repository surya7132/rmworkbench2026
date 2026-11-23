/* Relationship map for the client page.
 *
 * layout(data) is a plain function (no browser needed) that places every node on a fixed grid:
 *     suppliers  ->  the client's own companies  ->  customers        (supply chain flows left to right)
 *     group name and sector across the top, people and needs along the bottom.
 * mount(el, data, opts) draws it with Cytoscape and returns a small controller.
 */
(function (root) {
  'use strict';
  const SUPPLY = ['supplies', 'freight for'];
  const COL_X = 400, ROW_Y = 108;
  const COLORS = { group: '#12294d', own: '#2563eb', counterparty: '#ffffff', person: '#f1f5f9', sector: '#0d9488', need: '#d97706' };

  function shortName(n) {
    return n.replace(/\s+(Pvt\.?|Private)\s+(Ltd\.?|Limited)$/i, '').replace(/\s+(Ltd\.?|Limited)$/i, '');
  }

  function prepare(data) {
    const nodes = data.nodes.filter(n => !(n.type === 'client_group' && !n.mine));   // other clients' groups are noise here
    const ids = new Set(nodes.map(n => n.id));
    let edges = data.edges.filter(e => ids.has(e.source) && ids.has(e.target));
    const primary = new Set(edges.filter(e => e.label === 'primary borrower').map(e => e.source + '>' + e.target));
    edges = edges.filter(e => !(e.label === 'part of' && primary.has(e.target + '>' + e.source)));   // same link drawn twice
    return { nodes, edges };
  }

  function kindOf(n) {
    if (n.type === 'client_group') return 'group';
    if (n.type === 'company') return n.mine ? 'own' : 'counterparty';
    return n.type;   // person, sector, need
  }

  function colTitle(c) {
    if (c < 0) return c === -1 ? 'Suppliers' : 'Tier ' + (-c) + ' suppliers';
    return c === 1 ? 'Customers' : 'Tier ' + (c) + ' customers';
  }

  function layout(data) {
    const { nodes, edges } = prepare(data);
    const byId = new Map(nodes.map(n => [n.id, n]));
    const own = nodes.filter(n => n.type === 'company' && n.mine);
    const col = new Map();
    own.forEach(n => col.set(n.id, 0));
    const up = {}, down = {};
    edges.forEach(e => {
      if (!SUPPLY.includes(e.label)) return;
      (down[e.source] = down[e.source] || []).push(e.target);
      (up[e.target] = up[e.target] || []).push(e.source);
    });
    const walk = (adj, step) => {
      let frontier = own.map(n => n.id);
      while (frontier.length) {
        const next = [];
        frontier.forEach(id => (adj[id] || []).forEach(o => {
          const n = byId.get(o);
          if (n && n.type === 'company' && !col.has(o)) { col.set(o, col.get(id) + step); next.push(o); }
        }));
        frontier = next;
      }
    };
    walk(up, -1);
    walk(down, 1);
    const leftover = nodes.filter(n => n.type === 'company' && !col.has(n.id));
    const outer = Math.max(1, ...col.values()) + 1;
    leftover.forEach(n => col.set(n.id, outer));

    const cols = new Map();
    nodes.filter(n => col.has(n.id)).forEach(n => {
      const c = col.get(n.id);
      if (!cols.has(c)) cols.set(c, []);
      cols.get(c).push(n);
    });
    const pos = {};
    let minY = 0, maxY = 0;
    // ownership tree: who owns whom decides the rows (parent above, subsidiaries below)
    const owns = edges.filter(e => e.label === 'owns' && col.get(e.source) === 0 && col.get(e.target) === 0);
    const depth = new Map(own.map(n => [n.id, 0]));
    for (let k = 0; k < own.length; k++) owns.forEach(e => depth.set(e.target, Math.max(depth.get(e.target), depth.get(e.source) + 1)));
    const tree = owns.length > 0;
    let colX = COL_X;
    cols.forEach((arr, c) => {
      arr.sort((a, b) => (b.role === 'Primary borrower') - (a.role === 'Primary borrower') || a.label.localeCompare(b.label));
      if (c === 0 && tree) {
        const levels = new Map();
        arr.forEach(n => { const d = depth.get(n.id) || 0; if (!levels.has(d)) levels.set(d, []); levels.get(d).push(n); });
        const rows = Math.max(...levels.keys()) + 1;
        levels.forEach((lv, d) => lv.forEach((n, i) => {
          const y = (d - (rows - 1) / 2) * (ROW_Y + 24);
          pos[n.id] = { x: (i - (lv.length - 1) / 2) * 290, y };
          minY = Math.min(minY, y); maxY = Math.max(maxY, y);
        }));
        colX = COL_X + Math.max(0, Math.max(...[...levels.values()].map(lv => lv.length)) - 1) * 70;
        return;
      }
      const wide = c === 0 && arr.length > 4;                       // many companies in the group: two side by side
      const rows = wide ? Math.ceil(arr.length / 2) : arr.length;
      arr.forEach((n, i) => {
        const r = wide ? Math.floor(i / 2) : i;
        const y = (r - (rows - 1) / 2) * ROW_Y;
        pos[n.id] = { x: c * COL_X + (wide ? (i % 2 ? 140 : -140) : 0), y };
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      });
    });
    if (colX !== COL_X) cols.forEach((arr, c) => { if (c !== 0) arr.forEach(n => { pos[n.id] = { x: c * colX, y: pos[n.id].y }; }); });

    const headers = [];
    cols.forEach((arr, c) => {
      if (c === 0) return;
      headers.push({ id: 'hdr' + c, label: c === outer ? 'Other links' : colTitle(c), x: c * colX, y: minY - 78 });
    });

    const topY = minY - 200;
    nodes.filter(n => n.type === 'sector').forEach((n, i) => { pos[n.id] = { x: COL_X * 0.8 + i * 300, y: topY }; });
    const people = nodes.filter(n => n.type === 'person').sort((a, b) => (b.mine - a.mine) || a.label.localeCompare(b.label));
    const rowY = maxY + 190;
    people.forEach((n, i) => { pos[n.id] = { x: (i - (people.length - 1) / 2) * 270, y: rowY }; });
    const needs = nodes.filter(n => n.type === 'need');
    needs.forEach((n, i) => { pos[n.id] = { x: (i - (needs.length - 1) / 2) * 300, y: rowY + (people.length ? 120 : 0) }; });
    nodes.forEach(n => { if (!pos[n.id]) pos[n.id] = { x: 0, y: rowY + 220 }; });

    const suppliers = [...col].filter(([id, c]) => c < 0).length;
    const customers = [...col].filter(([id, c]) => c > 0 && c < outer).length;
    return { pos, headers, nodes, edges, col, outer, tree, summary: { companies: own.length, suppliers, customers, people: people.length, needs: needs.length } };
  }

  // ---- node cards: each node is drawn as a small SVG card (icon badge, name, one-line description) ----
  const ICONS = {
    building: '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 10h2M13 10h2M9 14h2M13 14h2M10 21v-3h4v3"/>',
    supplier: '<path d="M1.5 6.5h12v9.5h-12zM13.5 9.5h4l3 3.2V16h-7z"/><circle cx="6" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
    customer: '<path d="M3 9l1.2-5h15.6L21 9M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M5 12v8h14v-8M10 20v-4h4v4"/>',
    person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.2 3.6-6.5 8-6.5s8 2.3 8 6.5"/>',
    sector: '<path d="M3 20h18M6 16v-5M11 16V6M16 16v-8"/>',
    need: '<path d="M12 3l2.6 5.9 6.4.6-4.8 4.3 1.4 6.3L12 16.8 6.4 20.1l1.4-6.3L3 9.5l6.4-.6z"/>'
  };
  const TONE = {   // accent, soft fill, text
    own:      { a: '#2563eb', bg: '#2563eb', ink: '#ffffff', sub: '#c7d9ff' },
    sup:      { a: '#0284c7', bg: '#ffffff', ink: '#0c4a6e', sub: '#64748b', soft: '#e0f2fe' },
    cus:      { a: '#7c3aed', bg: '#ffffff', ink: '#3b0764', sub: '#64748b', soft: '#ede9fe' },
    other:    { a: '#475569', bg: '#ffffff', ink: '#1e293b', sub: '#64748b', soft: '#f1f5f9' },
    person:   { a: '#475569', bg: '#ffffff', ink: '#1e293b', sub: '#64748b', soft: '#f1f5f9' },
    sector:   { a: '#0d9488', bg: '#0f766e', ink: '#ffffff', sub: '#99f6e4' },
    need:     { a: '#d97706', bg: '#fffbeb', ink: '#78350f', sub: '#b45309', soft: '#fde68a' }
  };
  const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  function wrap(text, max, lines) {
    const words = String(text).split(/\s+/), out = [];
    let cur = '';
    words.forEach(w => { if ((cur + ' ' + w).trim().length <= max) cur = (cur + ' ' + w).trim(); else { if (cur) out.push(cur); cur = w; } });
    if (cur) out.push(cur);
    if (out.length > lines) { const keep = out.slice(0, lines); keep[lines - 1] = keep[lines - 1].replace(/[\s,.;]*$/, '').slice(0, max - 1) + '…'; return keep; }
    return out;
  }
  function card(spec) {
    // spec: {tone, icon, title, sub, news, big}
    const t = TONE[spec.tone], big = !!spec.big;
    const fs = big ? 14 : 13, cw = fs * 0.6;
    const maxChars = big ? 22 : 24;
    const lines = wrap(spec.title, maxChars, 2);
    const longest = Math.max(...lines.map(l => l.length), (spec.sub || '').length * 0.85);
    const w = Math.round(Math.min(260, Math.max(176, 70 + longest * cw + (spec.news ? 34 : 16))));
    const h = lines.length > 1 ? (big ? 84 : 76) : (big ? 72 : 64);
    const ink = t.ink, bg = t.bg;
    const filled = spec.tone === 'own' || spec.tone === 'sector';
    const badge = filled ? 'rgba(255,255,255,0.20)' : t.soft;
    const iconCol = filled ? '#ffffff' : t.a;
    const ty = lines.length > 1 ? h / 2 - 12 : h / 2 - 4;
    const titleSvg = lines.map((l, i) => '<text x="64" y="' + (ty + i * (fs + 3)) + '" font-size="' + fs + '" font-weight="700" fill="' + ink + '">' + esc(l) + '</text>').join('');
    const subSvg = spec.sub ? '<text x="64" y="' + (ty + (lines.length - 1) * (fs + 3) + 17) + '" font-size="11" fill="' + t.sub + '">' + esc(wrap(spec.sub, 30, 1)[0]) + '</text>' : '';
    const grad = filled ? '<linearGradient id="g' + spec.tone + '" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="' + (spec.tone === 'own' ? '#3b82f6' : '#14b8a6') + '"/><stop offset="1" stop-color="' + (spec.tone === 'own' ? '#1d4ed8' : '#0f766e') + '"/></linearGradient>' : '';
    const fill = filled ? 'url(#g' + spec.tone + ')' : bg;
    const stroke = spec.news ? '#f59e0b' : (filled ? 'none' : '#e2e8f0');
    const sw = spec.news ? 2.5 : 1.5;
    const accent = filled ? '' : '<rect x="1.5" y="14" width="3.5" height="' + (h - 28) + '" rx="1.75" fill="' + t.a + '"/>';
    const news = spec.news ? '<g transform="translate(' + (w - 30) + ',8)"><rect width="22" height="16" rx="8" fill="#f59e0b"/><text x="11" y="11.5" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">' + spec.news + '</text></g>' : '';
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" font-family="Segoe UI, Inter, Arial, sans-serif">' +
      '<defs>' + grad + '</defs>' +
      '<rect x="1.25" y="1.25" width="' + (w - 2.5) + '" height="' + (h - 2.5) + '" rx="14" fill="' + fill + '" stroke="' + stroke + '" stroke-width="' + sw + '"/>' + accent +
      '<circle cx="34" cy="' + h / 2 + '" r="19" fill="' + badge + '"/>' +
      '<g transform="translate(22,' + (h / 2 - 12) + ')" fill="none" stroke="' + iconCol + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + ICONS[spec.icon] + '</g>' +
      titleSvg + subSvg + news + '</svg>';
    return { w, h, svg, uri: 'data:image/svg+xml;utf8,' + encodeURIComponent(svg) };
  }

  function specFor(n, col, label, outer) {
    const c = col.get(n.id) || 0;
    const news = (n.news || []).length;
    if (n.type === 'company' && n.mine) return { tone: 'own', icon: 'building', title: label, sub: n.role || 'Group company', news, big: true };
    if (n.type === 'company') {
      if (c < 0) return { tone: 'sup', icon: 'supplier', title: label, sub: c === -1 ? 'Supplier' : 'Tier ' + (-c) + ' supplier', news };
      if (c > 0 && c < outer) return { tone: 'cus', icon: 'customer', title: label, sub: c === 1 ? 'Customer' : 'Tier ' + c + ' customer', news };
      return { tone: 'other', icon: 'building', title: label, sub: 'Linked company', news };
    }
    if (n.type === 'person') return { tone: 'person', icon: 'person', title: label, sub: n.role || 'Contact', news };
    if (n.type === 'sector') return { tone: 'sector', icon: 'sector', title: label, sub: 'Sector', news };
    return { tone: 'need', icon: 'need', title: label, sub: 'Opportunity', news };
  }

  function mount(container, data, opts) {
    opts = opts || {};
    const L = layout(data);
    const byId = new Map(L.nodes.map(n => [n.id, n]));
    const els = [];
    const groupNode = L.nodes.find(n => n.type === 'client_group');
    L.nodes.forEach(n => {
      const label = n.type === 'company' && !n.mine ? shortName(n.label) : n.label;
      const d = { id: n.id, label: n.type === 'client_group' ? n.label : '', kind: kindOf(n), news: (n.news || []).length };
      if (n.type !== 'client_group') {
        const k = card(specFor(n, L.col, label, L.outer));
        d.w = k.w; d.h = k.h; d.img = k.uri;
      }
      if (n.type === 'company' && n.mine && groupNode) d.parent = groupNode.id;
      els.push({ data: d });
    });
    L.headers.forEach(h => els.push({ data: { id: h.id, label: h.label, kind: 'hdr' } }));
    const QUIET = ['operates in', 'director of', 'works at', 'contact for', 'has need', 'primary borrower', 'part of'];
    const contained = (e) => groupNode && (e.source === groupNode.id || e.target === groupNode.id) && ['primary borrower', 'part of'].includes(e.label);
    const seenSector = new Set();   // one sector link from the group box, not one per company
    const sectorEdge = (e) => {
      if (e.label !== 'operates in' || !groupNode || !(byId.get(e.source) || {}).mine) return e;
      if (seenSector.has(e.target)) return null;
      seenSector.add(e.target);
      return Object.assign({}, e, { source: groupNode.id });
    };
    L.edges.filter(e => !contained(e)).map(sectorEdge).filter(Boolean).forEach(e => els.push({ data: { id: e.id, source: e.source, target: e.target, label: e.label, weak: e.weak ? 1 : 0, quiet: QUIET.includes(e.label) ? 1 : 0, flow: SUPPLY.includes(e.label) ? 1 : 0, owns: e.label === 'owns' ? 1 : 0 } }));
    const positions = {};
    Object.keys(L.pos).forEach(k => { positions[k] = L.pos[k]; });
    L.headers.forEach(h => { positions[h.id] = { x: h.x, y: h.y }; });
    if (groupNode) positions[groupNode.id] = { x: 0, y: 0 };   // a container: Cytoscape sizes it around its companies

    const FONT = 'Segoe UI, Inter, Arial, sans-serif';
    const cy = root.cytoscape({
      container, elements: els, minZoom: 0.25, maxZoom: 2.5, wheelSensitivity: 0.2, boxSelectionEnabled: false,
      layout: { name: 'preset', positions: (n) => positions[n.id()], fit: true, padding: 50 },
      style: [
        { selector: 'node', style: { 'shape': 'round-rectangle', 'corner-radius': 14, 'width': 'data(w)', 'height': 'data(h)', 'label': '', 'background-opacity': 0,
                                      'background-image': 'data(img)', 'background-fit': 'cover', 'background-image-opacity': 1, 'border-width': 0, 'overlay-opacity': 0,
                                      'underlay-color': '#14b8a6', 'underlay-opacity': 0, 'underlay-padding': 6, 'underlay-shape': 'round-rectangle',
                                      'transition-property': 'opacity, underlay-opacity, underlay-color, underlay-padding', 'transition-duration': '180ms' } },
        { selector: 'node[kind = "group"]', style: { 'width': 'auto', 'height': 'auto', 'background-color': '#eef4ff', 'background-opacity': 1, 'background-image': 'none', 'border-width': 1.5, 'border-color': '#bcd0f2', 'border-style': 'dashed',
                                                     'label': 'data(label)', 'color': '#1e40af', 'font-size': 14, 'font-weight': 700, 'font-family': FONT, 'text-valign': 'top', 'text-halign': 'center', 'text-margin-y': -12,
                                                     'text-max-width': 320, 'padding': 44, 'corner-radius': 28, 'underlay-opacity': 0 } },
        { selector: 'node[kind = "hdr"]', style: { 'width': 'label', 'height': 'label', 'label': 'data(label)', 'background-color': '#e2e8f0', 'background-opacity': 1, 'background-image': 'none', 'color': '#475569', 'font-size': 11, 'font-weight': 700, 'font-family': FONT,
                                                    'text-valign': 'center', 'text-halign': 'center', 'text-transform': 'uppercase', 'padding': 8, 'corner-radius': 12, 'events': 'no', 'underlay-opacity': 0 } },
        { selector: 'edge', style: { 'width': 1.4, 'line-color': '#cbd5e1', 'target-arrow-color': '#cbd5e1', 'target-arrow-shape': 'triangle', 'arrow-scale': 1, 'curve-style': 'unbundled-bezier',
                                    'control-point-distances': [28], 'control-point-weights': [0.5], 'line-style': 'dotted', 'line-cap': 'round',
                                    'label': 'data(label)', 'text-opacity': 0, 'font-size': 11, 'color': '#0f766e', 'font-weight': 600, 'font-family': FONT, 'text-rotation': 'autorotate',
                                    'text-background-color': '#ffffff', 'text-background-opacity': 0.95, 'text-background-padding': 3, 'text-background-shape': 'round-rectangle', 'overlay-opacity': 0,
                                    'transition-property': 'line-color, width, opacity', 'transition-duration': '180ms' } },
        { selector: 'edge[flow = 1]', style: { 'curve-style': 'unbundled-bezier', 'control-point-distances': [-34, 34], 'control-point-weights': [0.3, 0.7], 'line-style': 'solid', 'width': 2.6, 'line-color': '#94a3b8', 'target-arrow-color': '#94a3b8', 'arrow-scale': 1.3 } },
        { selector: 'edge[owns = 1]', style: { 'curve-style': 'bezier', 'line-style': 'solid', 'width': 2.2, 'line-color': '#93b4f0', 'target-arrow-color': '#93b4f0', 'arrow-scale': 1.2 } },
        { selector: 'edge[weak = 1]', style: { 'line-style': 'dashed' } },
        { selector: 'edge.hl', style: { 'line-color': '#0d9488', 'target-arrow-color': '#0d9488', 'width': 3, 'text-opacity': 1, 'line-style': 'solid', 'z-index': 10 } },
        { selector: 'node.hl', style: { 'underlay-color': '#14b8a6', 'underlay-opacity': 0.3, 'underlay-padding': 6 } },
        { selector: '.dim', style: { 'opacity': 0.15 } },
        { selector: 'node.match', style: { 'underlay-color': '#14b8a6', 'underlay-opacity': 0.35, 'underlay-padding': 8 } },
        { selector: 'node:selected', style: { 'underlay-color': '#0d9488', 'underlay-opacity': 0.38, 'underlay-padding': 8 } }
      ]
    });

    const real = cy.nodes('[kind != "hdr"][kind != "group"]');
    let selectedId = null;
    const info = (id) => {
      const n = byId.get(id);
      const conns = L.edges.filter(e => e.source === id || e.target === id).map(e => {
        const out = e.source === id;
        const o = byId.get(out ? e.target : e.source);
        return { out, verb: e.label, id: o.id, label: o.label };
      });
      return { id, label: n.label, type: n.type, kind: kindOf(n), mine: !!n.mine, role: n.role || '', detail: n.detail || '', news: n.news || [], conns };
    };
    const focus = (node) => {
      const hood = node.closedNeighborhood();
      real.union(cy.edges()).addClass('dim');
      hood.removeClass('dim');
      hood.edges().addClass('hl');
      node.addClass('hl');
    };
    const clearFocus = () => { cy.elements().removeClass('dim hl'); };
    const restore = () => { clearFocus(); const n = selectedId && cy.getElementById(selectedId); if (n && n.length && n.data('kind') !== 'group') focus(n); };

    cy.on('mouseover', 'node[kind != "hdr"][kind != "group"]', (ev) => { clearFocus(); focus(ev.target); container.style.cursor = 'pointer'; });
    cy.on('mouseout', 'node[kind != "hdr"][kind != "group"]', () => { restore(); container.style.cursor = 'default'; });
    cy.on('mouseover', 'edge', (ev) => { ev.target.addClass('hl'); });
    cy.on('mouseout', 'edge', (ev) => { if (!selectedId || !ev.target.connectedNodes().some(n => n.id() === selectedId)) ev.target.removeClass('hl'); });
    const select = (id) => {
      selectedId = id;
      cy.nodes().unselect();
      if (id) cy.getElementById(id).select();
      restore();
      if (opts.onSelect) opts.onSelect(id ? info(id) : null);
    };
    cy.on('tap', 'node[kind != "hdr"]', (ev) => select(ev.target.id()));
    cy.on('tap', (ev) => { if (ev.target === cy) select(null); });

    return {
      summary: L.summary,
      select,
      fit() { cy.animate({ fit: { eles: cy.elements(), padding: 50 } }, { duration: 250 }); },
      resize() { cy.resize(); cy.fit(cy.elements(), 50); },
      zoom(f) { cy.animate({ zoom: { level: Math.min(2.5, Math.max(0.25, cy.zoom() * f)), renderedPosition: { x: container.clientWidth / 2, y: container.clientHeight / 2 } } }, { duration: 150 }); },
      setVisible(kind, on) {
        const show = on ? 'element' : 'none';
        cy.nodes('[kind = "' + kind + '"]').style('display', show);
        if (kind === 'counterparty') cy.nodes('[kind = "hdr"]').style('display', show);
      },
      search(q) {
        q = (q || '').trim().toLowerCase();
        cy.nodes().removeClass('match');
        if (!q) { restore(); return 0; }
        const hits = real.filter(n => (byId.get(n.id()).label || '').toLowerCase().includes(q));
        hits.addClass('match');
        if (hits.length === 1) select(hits[0].id());
        return hits.length;
      },
      png(name) {
        const a = document.createElement('a');
        a.href = cy.png({ full: true, scale: 2, bg: '#ffffff' });
        a.download = (name || 'relationship-map') + '.png';
        document.body.appendChild(a); a.click(); a.remove();
      }
    };
  }

  const api = { layout, mount, shortName, card, specFor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.RelMap = api;
})(typeof window !== 'undefined' ? window : globalThis);
