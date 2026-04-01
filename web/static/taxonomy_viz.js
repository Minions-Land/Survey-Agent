/**
 * taxonomy_viz.js — Taxonomy tree visualization
 *
 * Features:
 *   - Horizontal tree: root → categories → subcategories → papers
 *   - SVG connector lines drawn after layout
 *   - Confidence threshold slider (client-side filtering)
 *   - Edit mode: drag-drop reclassification, inline name editing
 *   - Apply edits → POST /api/taxonomy/edit
 */

class TaxonomyViz {
  constructor() {
    this._data = null;          // full data from taxonomy_update event
    this._threshold = 0.5;      // effective threshold (0–1): 1=all classified, 0=none
    this._editMode = false;
    this._pendingEdits = null;  // modified taxonomy during edit mode
    this._dragSrc = null;       // { type: 'paper'|'cat', id, fromCatId }

    // Danger-zone boundaries (configurable here, not exposed in UI)
    this.SAFE_MIN = 0.2;
    this.SAFE_MAX = 0.8;

    this._drawer  = document.getElementById('tax-drawer');
    this._tree    = document.getElementById('tax-tree');
    this._svg     = document.getElementById('tax-svg');
    this._handle  = document.getElementById('tax-handle');
    this._statEl  = document.getElementById('tax-handle-stats');
    this._thrVal    = document.getElementById('tax-threshold-val');
    this._editBtn   = document.getElementById('tax-edit-btn');
    this._applyBtn  = document.getElementById('tax-apply-btn');
    this._cancelBtn = document.getElementById('tax-cancel-btn');
    this._unclPool  = document.getElementById('tax-unclassified');

    // Custom slider elements
    this._sliderWrap   = document.getElementById('tax-slider-wrap');
    this._sliderTrack  = document.getElementById('tax-slider-track');
    this._sliderThumb  = document.getElementById('tax-slider-thumb');
    this._sliderGhost  = document.getElementById('tax-slider-ghost');
    this._confirmBtn   = document.getElementById('tax-confirm-btn');
    this._ghostVal     = null;  // pending value in danger zone, null when none

    this._ro = new ResizeObserver(() => this._drawConnectors());

    this._initSlider();
  }

  /* ── Public API ──────────────────────────────────────────────────────────── */

  /** Called by app.js when a taxonomy_update WebSocket event arrives. */
  update(data) {
    this._data = data;
    this._editMode = false;
    this._pendingEdits = null;
    this._syncEditUI();
    this._render(data.taxonomy, data.papers);
    this._updateHandle(data);
    // Auto-open drawer on first update
    if (!this._drawer.classList.contains('open')) {
      this._drawer.classList.add('open');
    }
  }

  toggleDrawer() {
    this._drawer.classList.toggle('open');
    if (this._drawer.classList.contains('open')) {
      this._drawConnectors();
    }
  }

  setThreshold(val) {
    this._threshold = parseFloat(val);
    this._updateSliderUI();
    this._applyThreshold();
  }

  confirmThreshold() {
    if (this._ghostVal !== null) {
      this._threshold = this._ghostVal;
      this._ghostVal = null;
      this._confirmBtn.style.display = 'none';
      this._sliderGhost.classList.remove('visible');
      this._updateSliderUI();
      this._applyThreshold();
    }
  }

  enterEditMode() {
    if (!this._data) return;
    this._editMode = true;
    // Deep clone taxonomy for editing
    this._pendingEdits = JSON.parse(JSON.stringify(this._data.taxonomy));
    this._syncEditUI();
    this._tree.closest('.tax-tree-wrap').classList.add('tax-edit-active');
    this._enableDragDrop();
    this._enableInlineEdit();
  }

  exitEditMode(apply) {
    if (apply && this._pendingEdits) {
      this._applyEdits();
    }
    this._editMode = false;
    this._pendingEdits = null;
    this._syncEditUI();
    this._tree.closest('.tax-tree-wrap').classList.remove('tax-edit-active');
    if (this._data) {
      this._render(this._data.taxonomy, this._data.papers);
    }
  }

  /* ── Custom slider with danger zones ──────────────────────────────────────── */

  _initSlider() {
    if (!this._sliderWrap || !this._sliderTrack) return;

    // Set danger zone widths (percentage of track)
    const lowZone  = this._sliderTrack.querySelector('.tax-slider-danger-low');
    const highZone = this._sliderTrack.querySelector('.tax-slider-danger-high');
    if (lowZone)  lowZone.style.width  = `${this.SAFE_MIN * 100}%`;
    if (highZone) highZone.style.width = `${(1 - this.SAFE_MAX) * 100}%`;

    // Initial thumb position
    this._updateSliderUI();

    // Drag interaction
    let dragging = false;

    const getVal = (e) => {
      const rect = this._sliderTrack.getBoundingClientRect();
      const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
      return Math.max(0, Math.min(1, x / rect.width));
    };

    const onMove = (e) => {
      if (!dragging) return;
      e.preventDefault();
      const raw = getVal(e);

      if (raw < this.SAFE_MIN || raw > this.SAFE_MAX) {
        // Danger zone: real thumb clamps at boundary, ghost shows target
        const clamped = raw < this.SAFE_MIN ? this.SAFE_MIN : this.SAFE_MAX;
        this._threshold = clamped;
        this._ghostVal  = raw;
        this._sliderGhost.classList.add('visible');
        this._sliderGhost.style.left = `${raw * 100}%`;
        this._confirmBtn.style.display = 'inline';
      } else {
        // Safe zone: direct control
        this._threshold = raw;
        this._ghostVal  = null;
        this._sliderGhost.classList.remove('visible');
        this._confirmBtn.style.display = 'none';
      }
      this._updateSliderUI();
      this._applyThreshold();
    };

    const onEnd = () => {
      dragging = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onEnd);
      document.removeEventListener('touchmove', onMove);
      document.removeEventListener('touchend', onEnd);
    };

    this._sliderWrap.addEventListener('mousedown', (e) => {
      dragging = true;
      onMove(e);
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onEnd);
    });
    this._sliderWrap.addEventListener('touchstart', (e) => {
      dragging = true;
      onMove(e);
      document.addEventListener('touchmove', onMove, { passive: false });
      document.addEventListener('touchend', onEnd);
    });
  }

  _updateSliderUI() {
    if (!this._sliderThumb) return;
    this._sliderThumb.style.left = `${this._threshold * 100}%`;
    this._thrVal.textContent = this._threshold.toFixed(2);

    // Color the value label when in danger zone
    const inDanger = this._threshold < this.SAFE_MIN || this._threshold > this.SAFE_MAX;
    this._thrVal.style.color = inDanger ? 'var(--danger)' : 'var(--text)';
  }

  /* ── Rendering ───────────────────────────────────────────────────────────── */

  _render(taxonomy, papers) {
    this._ro.disconnect();
    this._tree.innerHTML = '';

    if (!taxonomy || !taxonomy.categories || taxonomy.categories.length === 0) {
      this._tree.innerHTML = '<div class="tax-empty">调研进行中，分类体系尚未建立...</div>';
      return;
    }

    const topic = (this._data && this._data.topic) || 'Survey';

    // Root node
    const rootBranch = document.createElement('div');
    rootBranch.className = 'tax-branch';
    rootBranch.dataset.id = 'root';

    const rootNode = this._makeNode('root', topic, '', null, 'tax-node-root');
    rootBranch.appendChild(rootNode);

    // Children column (major categories)
    const catChildren = document.createElement('div');
    catChildren.className = 'tax-children';
    catChildren.dataset.parentId = 'root';

    taxonomy.categories.forEach(cat => {
      catChildren.appendChild(this._renderCategory(cat, papers, 1));
    });

    rootBranch.appendChild(catChildren);
    this._tree.appendChild(rootBranch);

    // Unclassified pool
    this._renderUnclassified(taxonomy, papers);

    // Draw connectors after layout settles
    requestAnimationFrame(() => {
      this._drawConnectors();
      this._applyThreshold();
      this._ro.observe(this._tree);
    });
  }

  _renderCategory(cat, papers, depth) {
    const branch = document.createElement('div');
    branch.className = 'tax-branch';
    branch.dataset.id = cat.id;
    branch.dataset.type = depth === 1 ? 'cat' : 'sub';

    const paperCount = this._countPapers(cat);
    const nodeClass = depth === 1 ? 'tax-node-cat' : 'tax-node-sub';
    const node = this._makeNode(cat.id, cat.name, cat.description, paperCount, nodeClass);
    branch.appendChild(node);

    const hasChildren = cat.subcategories.length > 0 || cat.paper_ids.length > 0;
    if (!hasChildren) return branch;

    const children = document.createElement('div');
    children.className = 'tax-children';
    children.dataset.parentId = cat.id;

    // Subcategories first
    cat.subcategories.forEach(sub => {
      children.appendChild(this._renderCategory(sub, papers, depth + 1));
    });

    // Direct papers (not in any subcategory)
    cat.paper_ids.forEach(pid => {
      const p = (papers || {})[pid];
      if (p) children.appendChild(this._renderPaper(pid, p, cat.id));
    });

    branch.appendChild(children);
    return branch;
  }

  _renderPaper(pid, p, catId) {
    const branch = document.createElement('div');
    branch.className = 'tax-branch';
    branch.dataset.id = pid;
    branch.dataset.type = 'paper';
    branch.dataset.catId = catId;

    const node = document.createElement('div');
    node.className = 'tax-node tax-node-paper';
    node.dataset.id = pid;
    node.dataset.conf = p.confidence ?? 1.0;

    const abbrEl = document.createElement('div');
    abbrEl.className = 'tax-node-abbr';
    abbrEl.textContent = p.abbr || _shortKey(p.cite_key || pid);

    const fullEl = document.createElement('div');
    fullEl.className = 'tax-node-abbr-full';
    fullEl.textContent = p.title || '';
    fullEl.title = p.title || '';

    const confEl = document.createElement('div');
    confEl.className = 'tax-node-conf';
    const conf = p.confidence ?? 1.0;
    confEl.textContent = `${Math.round(conf * 100)}%`;

    const handle = document.createElement('div');
    handle.className = 'tax-drag-handle';
    handle.textContent = '⠿';

    node.appendChild(abbrEl);
    node.appendChild(fullEl);
    node.appendChild(confEl);
    node.appendChild(handle);
    branch.appendChild(node);
    return branch;
  }

  _makeNode(id, title, desc, count, extraClass) {
    const node = document.createElement('div');
    node.className = `tax-node ${extraClass || ''}`;
    node.dataset.id = id;

    const titleEl = document.createElement('div');
    titleEl.className = 'tax-node-title';
    titleEl.textContent = title;
    node.appendChild(titleEl);

    if (desc) {
      const descEl = document.createElement('div');
      descEl.className = 'tax-node-desc';
      descEl.textContent = desc;
      node.appendChild(descEl);
    }
    if (count !== null) {
      const countEl = document.createElement('div');
      countEl.className = 'tax-node-count';
      countEl.textContent = `${count} 篇`;
      node.appendChild(countEl);
    }

    const handle = document.createElement('div');
    handle.className = 'tax-drag-handle';
    handle.textContent = '⠿';
    node.appendChild(handle);

    return node;
  }

  _renderUnclassified(taxonomy, papers) {
    if (!this._unclPool) return;
    this._unclPool.innerHTML = '';

    // Papers not assigned to any category
    const assignedIds = new Set();
    const collectIds = cats => cats.forEach(c => {
      c.paper_ids.forEach(id => assignedIds.add(id));
      collectIds(c.subcategories);
    });
    collectIds(taxonomy.categories);

    const unclassified = Object.entries(papers || {})
      .filter(([id]) => !assignedIds.has(id));

    if (unclassified.length === 0) {
      this._unclPool.style.display = 'none';
      return;
    }

    this._unclPool.style.display = 'block';
    const label = document.createElement('div');
    label.className = 'tax-unclassified-label';
    label.textContent = `⚠️ 未分类论文 (${unclassified.length})`;
    this._unclPool.appendChild(label);

    const pillsWrap = document.createElement('div');
    pillsWrap.className = 'tax-unclassified-papers';
    unclassified.forEach(([id, p]) => {
      const pill = document.createElement('div');
      pill.className = 'tax-unclassified-pill';
      pill.textContent = p.abbr || _shortKey(p.cite_key || id);
      pill.title = p.title || id;
      pill.dataset.id = id;
      pillsWrap.appendChild(pill);
    });
    this._unclPool.appendChild(pillsWrap);

    // Update badge
    const badge = document.getElementById('tax-unclassified-badge');
    if (badge) {
      badge.textContent = unclassified.length;
      badge.style.display = unclassified.length > 0 ? 'inline' : 'none';
    }
  }

  /* ── SVG connectors ──────────────────────────────────────────────────────── */

  _drawConnectors() {
    const svg = this._svg;
    if (!svg) return;
    svg.innerHTML = '';

    const wrapRect = this._tree.closest('.tax-tree-wrap').getBoundingClientRect();

    // For every .tax-children, find its parent .tax-node and child .tax-node elements
    this._tree.querySelectorAll('.tax-children').forEach(childrenEl => {
      const parentId = childrenEl.dataset.parentId;
      // Find the parent node box (sibling of this children element's parent branch)
      const parentBranch = childrenEl.parentElement;
      const parentNode = parentBranch.querySelector(':scope > .tax-node');
      if (!parentNode) return;

      const childBranches = childrenEl.querySelectorAll(':scope > .tax-branch');
      if (childBranches.length === 0) return;

      const childNodes = Array.from(childBranches).map(b => b.querySelector(':scope > .tax-node')).filter(Boolean);
      if (childNodes.length === 0) return;

      const pRect = parentNode.getBoundingClientRect();
      const px = pRect.right - wrapRect.left;
      const py = pRect.top + pRect.height / 2 - wrapRect.top;

      // Midpoint X between parent right and first child left
      const firstChildRect = childNodes[0].getBoundingClientRect();
      const midX = px + (firstChildRect.left - wrapRect.left - px) / 2;

      // Vertical span from first to last child midpoint
      const firstY = firstChildRect.top + firstChildRect.height / 2 - wrapRect.top;
      const lastRect = childNodes[childNodes.length - 1].getBoundingClientRect();
      const lastY = lastRect.top + lastRect.height / 2 - wrapRect.top;

      // Horizontal line from parent to midX
      this._line(svg, px, py, midX, py);
      // Vertical line
      if (childNodes.length > 1) {
        this._line(svg, midX, firstY, midX, lastY);
      }
      // Horizontal lines from midX to each child
      childNodes.forEach(cn => {
        const cr = cn.getBoundingClientRect();
        const cy = cr.top + cr.height / 2 - wrapRect.top;
        const cx = cr.left - wrapRect.left;
        this._line(svg, midX, cy, cx, cy);
      });
    });
  }

  _line(svg, x1, y1, x2, y2) {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('class', 'tax-connector-line');
    svg.appendChild(line);
  }

  /* ── Confidence threshold ─────────────────────────────────────────────────── */

  _applyThreshold() {
    // Semantics: threshold=1 → all classified; threshold=0 → none classified
    // A paper is classified if confidence >= (1 - threshold)
    const minConf = 1 - this._threshold;
    const papers = this._tree.querySelectorAll('.tax-node-paper');
    let hiddenCount = 0;

    papers.forEach(node => {
      const conf = parseFloat(node.dataset.conf ?? '1');
      const branch = node.closest('.tax-branch');
      if (conf < minConf) {
        branch.classList.add('hidden-conf');
        hiddenCount++;
      } else {
        branch.classList.remove('hidden-conf');
        node.classList.toggle('low-confidence', conf < 0.6);
      }
    });

    // Show hidden papers in unclassified pool
    this._showThresholdPool(hiddenCount);
    // Redraw connectors after visibility change
    requestAnimationFrame(() => this._drawConnectors());
  }

  _showThresholdPool(count) {
    if (!this._unclPool) return;
    // Update or create threshold-hidden section
    let thrSection = document.getElementById('tax-thr-pool');
    if (count > 0) {
      if (!thrSection) {
        thrSection = document.createElement('div');
        thrSection.id = 'tax-thr-pool';
        thrSection.className = 'tax-unclassified-pool';
        thrSection.style.borderColor = 'var(--accent2)';
        this._unclPool.after(thrSection);
      }
      thrSection.innerHTML = `<div class="tax-unclassified-label" style="color:var(--accent2)">
        📉 置信度低于 ${Math.round(this._threshold * 100)}% 的论文 (${count} 篇)
      </div><div class="tax-unclassified-papers">
        ${Array.from(this._tree.querySelectorAll('.tax-branch.hidden-conf .tax-node-paper'))
          .map(n => {
            const pid = n.dataset.id;
            const p = (this._data?.papers || {})[pid] || {};
            return `<div class="tax-unclassified-pill" style="border-color:var(--accent2);color:var(--accent2)" title="${(p.title||'').replace(/"/g,'')}">${p.abbr || pid}</div>`;
          }).join('')}
      </div>`;
      thrSection.style.display = 'block';
    } else if (thrSection) {
      thrSection.style.display = 'none';
    }
  }

  /* ── Edit mode: drag & drop ─────────────────────────────────────────────── */

  _enableDragDrop() {
    // Make all nodes draggable
    this._tree.querySelectorAll('.tax-branch[data-type]').forEach(branch => {
      branch.draggable = true;
      branch.addEventListener('dragstart', e => this._onDragStart(e, branch));
      branch.addEventListener('dragend', () => this._onDragEnd());
    });

    // Make category children areas drop targets
    this._tree.querySelectorAll('.tax-children').forEach(zone => {
      zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
      zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
      zone.addEventListener('drop', e => this._onDrop(e, zone));
    });

    // Unclassified pool as drop target
    if (this._unclPool) {
      this._unclPool.addEventListener('dragover', e => { e.preventDefault(); });
      this._unclPool.addEventListener('drop', e => this._onDropToUnclassified(e));
    }
  }

  _onDragStart(e, branch) {
    this._dragSrc = {
      type: branch.dataset.type,
      id: branch.dataset.id,
      catId: branch.dataset.catId || null,
      el: branch,
    };
    branch.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', branch.dataset.id);
  }

  _onDragEnd() {
    this._tree.querySelectorAll('.dragging').forEach(el => el.classList.remove('dragging'));
    this._tree.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    this._dragSrc = null;
  }

  _onDrop(e, zone) {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (!this._dragSrc) return;

    const targetCatId = zone.dataset.parentId;
    const src = this._dragSrc;

    if (src.type === 'paper') {
      this._movePaperInEdits(src.id, src.catId, targetCatId);
    } else if (src.type === 'cat' || src.type === 'sub') {
      this._moveCatInEdits(src.id, targetCatId);
    }

    // Re-render with pending edits
    this._render(this._pendingEdits, this._data.papers);
    this._enableDragDrop();
    this._enableInlineEdit();
    this._tree.closest('.tax-tree-wrap').classList.add('tax-edit-active');
  }

  _onDropToUnclassified(e) {
    e.preventDefault();
    if (!this._dragSrc || this._dragSrc.type !== 'paper') return;
    const src = this._dragSrc;
    this._movePaperInEdits(src.id, src.catId, null); // null = unclassified
    this._render(this._pendingEdits, this._data.papers);
    this._enableDragDrop();
    this._enableInlineEdit();
    this._tree.closest('.tax-tree-wrap').classList.add('tax-edit-active');
  }

  /* ── Edit mode: inline title editing ─────────────────────────────────────── */

  _enableInlineEdit() {
    this._tree.querySelectorAll('.tax-node-title').forEach(titleEl => {
      const nodeEl = titleEl.closest('.tax-node');
      if (!nodeEl || nodeEl.classList.contains('tax-node-root')) return;
      titleEl.contentEditable = 'true';
      titleEl.addEventListener('blur', () => {
        const newName = titleEl.textContent.trim();
        const catId = nodeEl.dataset.id;
        this._renameCatInEdits(catId, newName);
      });
      titleEl.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); titleEl.blur(); }
      });
    });
  }

  /* ── Pending edits helpers ────────────────────────────────────────────────── */

  _movePaperInEdits(paperId, fromCatId, toCatId) {
    if (!this._pendingEdits) return;
    const allCats = this._flatCats(this._pendingEdits.categories);

    // Remove from source
    allCats.forEach(c => {
      c.paper_ids = c.paper_ids.filter(id => id !== paperId);
    });

    // Add to destination
    if (toCatId) {
      const dest = allCats.find(c => c.id === toCatId);
      if (dest && !dest.paper_ids.includes(paperId)) {
        dest.paper_ids.push(paperId);
      }
    }
  }

  _moveCatInEdits(catId, newParentId) {
    if (!this._pendingEdits) return;
    const allCats = this._flatCats(this._pendingEdits.categories);
    const cat = allCats.find(c => c.id === catId);
    if (!cat) return;

    // Remove from current parent
    allCats.forEach(c => {
      c.subcategories = c.subcategories.filter(s => s.id !== catId);
    });
    this._pendingEdits.categories = this._pendingEdits.categories.filter(c => c.id !== catId);

    // Add to new parent
    if (newParentId === 'root') {
      cat.parent_id = null;
      this._pendingEdits.categories.push(cat);
    } else {
      const newParent = allCats.find(c => c.id === newParentId);
      if (newParent) {
        cat.parent_id = newParentId;
        newParent.subcategories.push(cat);
      }
    }
  }

  _renameCatInEdits(catId, newName) {
    if (!this._pendingEdits || !newName) return;
    const cat = this._flatCats(this._pendingEdits.categories).find(c => c.id === catId);
    if (cat) cat.name = newName;
  }

  _flatCats(cats) {
    const result = [];
    const visit = list => list.forEach(c => { result.push(c); visit(c.subcategories); });
    visit(cats);
    return result;
  }

  /* ── Apply edits to backend ─────────────────────────────────────────────── */

  async _applyEdits() {
    if (!this._pendingEdits) return;
    try {
      const resp = await fetch('/api/taxonomy/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ taxonomy: this._pendingEdits }),
      });
      const result = await resp.json();
      if (result.taxonomy) {
        this._data.taxonomy = result.taxonomy;
      }
      this._render(this._data.taxonomy, this._data.papers);
    } catch (err) {
      console.error('taxonomy/edit failed:', err);
    }
  }

  /* ── Handle bar ──────────────────────────────────────────────────────────── */

  _updateHandle(data) {
    if (!this._statEl) return;
    const catCount = (data.taxonomy?.categories || []).length;
    const paperCount = Object.keys(data.papers || {}).length;
    this._statEl.innerHTML = `
      <span class="tax-handle-stat">📂 ${catCount} 大类</span>
      <span class="tax-handle-stat">📄 ${paperCount} 篇论文</span>
    `;
  }

  _syncEditUI() {
    if (!this._editBtn) return;
    if (this._editMode) {
      this._editBtn.style.display = 'none';
      this._applyBtn.style.display = 'inline';
      this._cancelBtn.style.display = 'inline';
    } else {
      this._editBtn.style.display = 'inline';
      this._applyBtn.style.display = 'none';
      this._cancelBtn.style.display = 'none';
    }
  }

  _countPapers(cat) {
    let n = cat.paper_ids.length;
    cat.subcategories.forEach(s => { n += this._countPapers(s); });
    return n;
  }
}

/* ── Helpers ──────────────────────────────────────────────────────────────── */

function _shortKey(key) {
  // "vaswani2017attention" → "Vaswani17"
  const m = key.match(/^([a-z]+)(\d{4})/i);
  if (m) return m[1].charAt(0).toUpperCase() + m[1].slice(1) + m[2].slice(2);
  return key.slice(0, 10);
}

/* ── Global init ──────────────────────────────────────────────────────────── */

let _taxViz = null;

function taxVizInit() {
  _taxViz = new TaxonomyViz();
}

function taxVizUpdate(data) {
  if (_taxViz) _taxViz.update(data);
}

function taxToggleDrawer() {
  if (_taxViz) _taxViz.toggleDrawer();
}

function taxSetThreshold(val) {
  if (_taxViz) _taxViz.setThreshold(val);
}

function taxConfirmThreshold() {
  if (_taxViz) _taxViz.confirmThreshold();
}

function taxEnterEdit() {
  if (_taxViz) _taxViz.enterEditMode();
}

function taxApplyEdit() {
  if (_taxViz) _taxViz.exitEditMode(true);
}

function taxCancelEdit() {
  if (_taxViz) _taxViz.exitEditMode(false);
}
