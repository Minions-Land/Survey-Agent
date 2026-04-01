/**
 * app.js — Survey Agent frontend logic
 *
 * Chat-style UI with pipeline stage visualization.
 */

/* ── i18n ──────────────────────────────────────────────────────────────────── */
const TRANSLATIONS = {
  zh: {
    'section.topic':   '📖 综述主题',
    'section.refMaterials': '📖 参考资料',
    'section.llm':     '🤖 语言模型',
    'section.search':  '🔍 文献搜索',
    'section.output':  '📄 输出设置',
    'label.seeds':     '种子论文（可选）',
    'label.paperIds':  '论文 ID（可选）',
    'label.startDoc':  '起始文档（可选）',
    'label.startDocHint': '上传你的初步理解或规划文件（PDF/MD/Word/TXT）',
    'btn.uploadStartDoc': '📝 上传起始文档',
    'label.readingDepth': '阅读深度',
    'opt.skim':        '泛读（标题+摘要）',
    'opt.standard':    '常见读（推荐）',
    'opt.deep':        '精读（全文）',
    'msg.startDocUploading': '正在上传起始文档...',
    'msg.startDocUploaded':  '起始文档已上传',
    'msg.startDocFail':      '起始文档上传失败',
    'label.provider':  'Provider',
    'label.apiKey':    'API Key',
    'label.cheapModel':'轻量模型（提取）',
    'label.expModel':  '高质量模型（写作）',
    'label.s2Key':     'Semantic Scholar API Key（可选）',
    'label.searchSources': '启用的搜索源',
    'label.format':    '文档格式',
    'label.sensitivity': '分类法敏感度',
    'label.mindmap':   '生成思维导图（Mermaid）',
    'label.papersDir': '本地 PDF 目录（可选）',
    'label.searchHint':'输入关键词后点击搜索',
    'opt.balanced':    'Balanced（推荐）',
    'opt.strict':      'Strict（全手动）',
    'opt.liberal':     'Liberal（全自动）',
    'btn.start':       '🚀 开始调研',
    'btn.stop':        '⏹ 停止',
    'btn.send':        '发送',
    'btn.close':       '关闭',
    'btn.searchPapers':'🔍 标题搜索',
    'btn.uploadPDF':   '📎 上传 PDF',
    'btn.search':      '搜索',
    'btn.browse':      '📁 选择',
    'placeholder.topic':      '例：视觉 Transformer 在医学图像分析中的应用',
    'placeholder.seeds':      'S2 ID · arXiv ID · DOI（逗号分隔）',
    'placeholder.searchTitle':'论文标题关键词...',
    'placeholder.apiKey':     '从环境变量读取（可留空）',
    'placeholder.s2Key':      '无 key 时速率受限',
    'placeholder.papersDir':  '例：data/papers',
    'placeholder.reply':      '输入回复...',
    'placeholder.agentWorking':'Agent 正在工作中...',
    'status.idle':     '空闲',
    'status.running':  '运行中',
    'status.done':     '已完成',
    'status.error':    '错误',
    'status.preparing':'准备中...',
    'welcome.title':   '👋 欢迎使用 Survey Agent',
    'welcome.hint1':   '在左侧填写配置后点击「开始调研」',
    'welcome.hint2':   '系统将自动完成文献检索、分类、写作全流程',
    'done.title':      '🎉 综述已完成！',
    'done.body':       '综述文件已保存到 data/surveys/ 目录。可在输出窗口查看文件路径。',
    'interrupt.dialogue':        '💬 请回复 Agent...',
    'interrupt.survey_decision': '📋 发现已有综述，请决策：',
    'interrupt.taxonomy_review': '🗂 分类法变更提案，请审核：',
    'interrupt.outline_review':  '📑 综述大纲已生成，请确认：',
    'opt.continue':    '✅ 继续，我的综述有独特视角',
    'opt.abort':       '⛔ 放弃，已有综述已充分覆盖',
    'opt.approve':     '✅ 批准',
    'opt.reject':      '❌ 拒绝',
    'opt.confirmOutline': '✅ 确认，开始写作',
    'pipeline.dialogue':       '对话',
    'pipeline.survey_search':  '综述检索',
    'pipeline.research':       '文献扩展',
    'pipeline.extraction':     '信息提取',
    'pipeline.taxonomy_review':'分类审核',
    'pipeline.writing':        '写作',
    'pipeline.complete':       '完成',
    'phase.starting':       '准备中',
    'phase.dialogue':       '对话阶段',
    'phase.survey_search':  '搜索已有综述',
    'phase.research':       '构建论文网络',
    'phase.extraction':     '结构化提取',
    'phase.taxonomy_review':'分类法审核',
    'phase.writing':        '撰写综述',
    'phase.complete':       '完成！',
    'msg.started':     '🚀 调研已启动，正在连接服务...',
    'msg.disconnected':'连接已断开',
    'msg.wsError':     'WebSocket 连接失败',
    'msg.stopped':     '已停止',
    'msg.error':       '错误: ',
    'msg.topicRequired': '请填写综述主题',
    'msg.uploading':   '正在上传 PDF...',
    'msg.uploadOk':    'PDF 已上传，已作为种子论文添加',
    'msg.uploadFail':  '上传失败',
    'msg.searching':   '搜索中...',
    'msg.noResults':   '未找到相关论文',
    'msg.browseFail':  '无法打开文件夹选择器',
    'msg.seedAdded':   '已添加',
    'label.citations': '引用',
    'section.dlrefs':  '📥 下载引用文献',
    'label.dlrefsHint':'上传一篇 PDF，系统自动提取参考文献并从 arXiv / Unpaywall 下载全文',
    'btn.selectPDF':   '📄 选择 PDF',
    'msg.dlrefsRunning':'正在提取并下载引用文献，请稍候...',
    'msg.dlrefsOk':    '完成',
    'msg.dlrefsFail':  '下载失败',
    'tax.title':       '分类可视化',
    'tax.dragHint':    '上拉展开',
    'tax.threshold':   '分类阈值',
    'tax.edit':        '✏️ 编辑分类',
    'tax.apply':       '✅ 应用修改',
    'tax.cancel':      '✕ 取消',
    'tax.empty':       '调研进行中，分类体系尚未建立...',
    'tax.maxPapers':   '上限',
    'tax.confirm':     '确认',
    'tax.dangerWarn':  '⚠️ 超出安全范围',
  },
  en: {
    'section.topic':   '📖 Survey Topic',
    'section.refMaterials': '📖 Reference Materials',
    'section.llm':     '🤖 Language Model',
    'section.search':  '🔍 Literature Search',
    'section.output':  '📄 Output Settings',
    'label.seeds':     'Seed Papers (optional)',
    'label.paperIds':  'Paper IDs (optional)',
    'label.startDoc':  'Start Document (optional)',
    'label.startDocHint': 'Upload your initial understanding or plan (PDF/MD/Word/TXT)',
    'btn.uploadStartDoc': '📝 Upload Start Doc',
    'label.readingDepth': 'Reading Depth',
    'opt.skim':        'Skim (title + abstract)',
    'opt.standard':    'Standard (recommended)',
    'opt.deep':        'Deep (full paper)',
    'msg.startDocUploading': 'Uploading Start document...',
    'msg.startDocUploaded':  'Start document uploaded',
    'msg.startDocFail':      'Start document upload failed',
    'label.provider':  'Provider',
    'label.apiKey':    'API Key',
    'label.cheapModel':'Lightweight Model (extraction)',
    'label.expModel':  'High-Quality Model (writing)',
    'label.s2Key':     'Semantic Scholar API Key (optional)',
    'label.searchSources': 'Enabled Search Sources',
    'label.format':    'Output Format',
    'label.sensitivity': 'Taxonomy Sensitivity',
    'label.mindmap':   'Generate Mind Map (Mermaid)',
    'label.papersDir': 'Local PDF Directory (optional)',
    'label.searchHint':'Enter keywords then click Search',
    'opt.balanced':    'Balanced (recommended)',
    'opt.strict':      'Strict (all manual)',
    'opt.liberal':     'Liberal (fully automatic)',
    'btn.start':       '🚀 Start Survey',
    'btn.stop':        '⏹ Stop',
    'btn.send':        'Send',
    'btn.close':       'Close',
    'btn.searchPapers':'🔍 Search by Title',
    'btn.uploadPDF':   '📎 Upload PDF',
    'btn.search':      'Search',
    'btn.browse':      '📁 Browse',
    'placeholder.topic':      'e.g. Vision Transformers in Medical Image Analysis',
    'placeholder.seeds':      'S2 ID · arXiv ID · DOI (comma-separated)',
    'placeholder.searchTitle':'Paper title keywords...',
    'placeholder.apiKey':     'Read from env var (leave empty)',
    'placeholder.s2Key':      'Rate-limited without key',
    'placeholder.papersDir':  'e.g. data/papers',
    'placeholder.reply':      'Enter your reply...',
    'placeholder.agentWorking':'Agent is working...',
    'status.idle':     'Idle',
    'status.running':  'Running',
    'status.done':     'Done',
    'status.error':    'Error',
    'status.preparing':'Preparing...',
    'welcome.title':   '👋 Welcome to Survey Agent',
    'welcome.hint1':   'Fill in the config on the left and click "Start Survey"',
    'welcome.hint2':   'The system will automatically handle retrieval, classification, and writing',
    'done.title':      '🎉 Survey Complete!',
    'done.body':       'Survey files saved to data/surveys/. Check the output panel for paths.',
    'interrupt.dialogue':        '💬 Please reply to the Agent...',
    'interrupt.survey_decision': '📋 Existing survey found. What would you like to do?',
    'interrupt.taxonomy_review': '🗂 Taxonomy change proposal — please review:',
    'interrupt.outline_review':  '📑 Outline generated — please confirm:',
    'opt.continue':    '✅ Continue — my survey has a unique angle',
    'opt.abort':       '⛔ Abort — the existing survey covers this',
    'opt.approve':     '✅ Approve',
    'opt.reject':      '❌ Reject',
    'opt.confirmOutline': '✅ Confirm — start writing',
    'pipeline.dialogue':       'Dialogue',
    'pipeline.survey_search':  'Search',
    'pipeline.research':       'Research',
    'pipeline.extraction':     'Extraction',
    'pipeline.taxonomy_review':'Taxonomy',
    'pipeline.writing':        'Writing',
    'pipeline.complete':       'Done',
    'phase.starting':       'Preparing',
    'phase.dialogue':       'Dialogue',
    'phase.survey_search':  'Searching Surveys',
    'phase.research':       'Building Network',
    'phase.extraction':     'Extraction',
    'phase.taxonomy_review':'Taxonomy Review',
    'phase.writing':        'Writing Survey',
    'phase.complete':       'Complete!',
    'msg.started':     '🚀 Survey started, connecting...',
    'msg.disconnected':'Connection closed',
    'msg.wsError':     'WebSocket connection failed',
    'msg.stopped':     'Stopped',
    'msg.error':       'Error: ',
    'msg.topicRequired': 'Please enter a survey topic',
    'msg.uploading':   'Uploading PDF...',
    'msg.uploadOk':    'PDF uploaded and added as seed paper',
    'msg.uploadFail':  'Upload failed',
    'msg.searching':   'Searching...',
    'msg.noResults':   'No papers found',
    'msg.browseFail':  'Could not open folder picker',
    'msg.seedAdded':   'Added',
    'label.citations': 'citations',
    'section.dlrefs':  '📥 Download References',
    'label.dlrefsHint':'Upload a PDF to extract & download its references from arXiv / Unpaywall',
    'btn.selectPDF':   '📄 Select PDF',
    'msg.dlrefsRunning':'Extracting and downloading references...',
    'msg.dlrefsOk':    'Done',
    'msg.dlrefsFail':  'Download failed',
    'tax.title':       'Taxonomy',
    'tax.dragHint':    'Pull up',
    'tax.threshold':   'Threshold',
    'tax.edit':        '✏️ Edit',
    'tax.apply':       '✅ Apply',
    'tax.cancel':      '✕ Cancel',
    'tax.empty':       'Taxonomy not yet built...',
    'tax.confirm':     'Confirm',
    'tax.dangerWarn':  '⚠️ Outside safe range',
    'tax.maxPapers':   'Limit',
  },
};

/* ── i18n engine ───────────────────────────────────────────────────────────── */
let currentLang = localStorage.getItem('sa_lang') || 'zh';

function t(key) {
  const primary = (TRANSLATIONS[currentLang] || {})[key];
  if (primary) return primary;
  const fallback = (TRANSLATIONS.zh || {})[key];
  if (fallback) return fallback;
  return null;
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const val = t(el.getAttribute('data-i18n'));
    if (val != null) el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const val = t(el.getAttribute('data-i18n-placeholder'));
    if (val != null) el.placeholder = val;
  });
  document.getElementById('lang-btn').textContent = currentLang === 'zh' ? '中 / EN' : 'EN / 中';
  document.documentElement.lang = currentLang === 'zh' ? 'zh-CN' : 'en';
  const ci = document.getElementById('chat-input');
  if (ci && !interruptActive) ci.placeholder = t('placeholder.agentWorking') || '';
  onProviderChange();
  buildPipeline();
  if (currentPhase) updatePipeline(currentPhase);
}

function toggleLang() {
  currentLang = currentLang === 'zh' ? 'en' : 'zh';
  localStorage.setItem('sa_lang', currentLang);
  applyTranslations();
}

/* ── Theme ─────────────────────────────────────────────────────────────────── */
let currentTheme = localStorage.getItem('sa_theme') || 'dark';
function applyTheme() {
  document.documentElement.setAttribute('data-theme', currentTheme);
  document.getElementById('theme-btn').textContent = currentTheme === 'dark' ? '☀️' : '🌙';
}
function toggleTheme() {
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('sa_theme', currentTheme);
  applyTheme();
}

/* ── State ─────────────────────────────────────────────────────────────────── */
let ws = null;
let jobId = null;
let isRunning = false;
let interruptActive = false;
let _lastServerError = '';   // stores the last error message from the server

/* ── Pipeline ──────────────────────────────────────────────────────────────── */
const PIPELINE_STAGES = [
  { key: 'dialogue',        pct: 5   },
  { key: 'survey_search',   pct: 15  },
  { key: 'research',        pct: 35  },
  { key: 'extraction',      pct: 55  },
  { key: 'taxonomy_review', pct: 65  },
  { key: 'writing',         pct: 85  },
  { key: 'complete',        pct: 100 },
];
let currentPhase = null;

function buildPipeline() {
  const el = document.getElementById('pipeline-stages');
  if (!el) return;
  el.innerHTML = '';
  PIPELINE_STAGES.forEach((stage, i) => {
    if (i > 0) {
      const conn = document.createElement('div');
      conn.className = 'pipeline-connector';
      conn.dataset.idx = i - 1;
      el.appendChild(conn);
    }
    const s = document.createElement('div');
    s.className = 'pipeline-stage';
    s.dataset.stage = stage.key;
    s.dataset.status = 'pending';
    const dot = document.createElement('div');
    dot.className = 'pipeline-dot';
    const label = document.createElement('span');
    label.className = 'pipeline-label';
    label.textContent = t(`pipeline.${stage.key}`) || stage.key;
    s.appendChild(dot);
    s.appendChild(label);
    el.appendChild(s);
  });
}

function updatePipeline(phase) {
  const idx = PIPELINE_STAGES.findIndex(s => s.key === phase);
  if (idx === -1) return;
  currentPhase = phase;
  document.querySelectorAll('.pipeline-stage').forEach((el, i) => {
    const dot = el.querySelector('.pipeline-dot');
    if (i < idx) {
      el.dataset.status = 'completed';
      dot.textContent = '✓';
    } else if (i === idx) {
      el.dataset.status = 'in-progress';
      dot.textContent = '';
    } else {
      el.dataset.status = 'pending';
      dot.textContent = '';
    }
  });
  document.querySelectorAll('.pipeline-connector').forEach((el, i) => {
    el.classList.toggle('completed', i < idx);
  });
  document.getElementById('pipeline').style.display = 'block';
}

function setSubStatus(text) {
  const el = document.getElementById('pipeline-substatus');
  if (el) el.textContent = text;
}

/* ── Agent output buffering ────────────────────────────────────────────────── */
let agentBuffer = '';
let agentTimer = null;
let agentContentEl = null;
const FLUSH_MS = 150;

function flushAgentBuffer() {
  if (!agentBuffer) return;
  if (agentContentEl) {
    agentContentEl.innerHTML = renderMarkdown(escapeHtml(agentBuffer));
  } else {
    agentContentEl = appendChatMessage('agent', agentBuffer);
  }
  scrollOutputToBottom();
}

function finishAgentBubble() {
  clearTimeout(agentTimer);
  if (agentBuffer) flushAgentBuffer();
  agentBuffer = '';
  agentContentEl = null;
}

/* ── Minimal markdown ──────────────────────────────────────────────────────── */
function renderMarkdown(escaped) {
  escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  escaped = escaped.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
  escaped = escaped.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  return escaped;
}

/* ── Chat message renderer ─────────────────────────────────────────────────── */
function appendChatMessage(type, text) {
  const stream = document.getElementById('output-stream');
  const welcome = stream.querySelector('.welcome-msg');
  if (welcome) welcome.remove();

  if (type === 'system') {
    const el = document.createElement('div');
    el.className = 'chat-system';
    el.textContent = text.replace(/\n+$/, '');
    stream.appendChild(el);
    scrollOutputToBottom();
    return null;
  }

  const msg = document.createElement('div');
  msg.className = `chat-msg chat-${type}`;

  const avatar = document.createElement('div');
  avatar.className = 'chat-avatar';
  avatar.textContent = type === 'user' ? '👤' : '🤖';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';

  const content = document.createElement('div');
  content.className = 'chat-content';
  if (type === 'agent' || type === 'error') {
    content.innerHTML = renderMarkdown(escapeHtml(text));
  } else {
    content.textContent = text;
  }

  const time = document.createElement('div');
  time.className = 'chat-time';
  time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  bubble.appendChild(content);
  bubble.appendChild(time);
  msg.appendChild(avatar);
  msg.appendChild(bubble);
  stream.appendChild(msg);
  scrollOutputToBottom();
  return content;
}

/** Backward-compatible wrapper — routes old appendOutput calls to chat system */
function appendOutput(text, cls = '') {
  if (cls === 'system' || cls === 'success') appendChatMessage('system', text);
  else if (cls === 'error') appendChatMessage('error', text);
  else if (cls === 'agent') appendChatMessage('user', text);  // 'agent' class was user messages
  else appendChatMessage('agent', text);
}

function clearOutput() {
  document.getElementById('output-stream').innerHTML = '';
  document.getElementById('pipeline').style.display = 'none';
  document.getElementById('pipeline-substatus').textContent = '';
  currentPhase = null;
  finishAgentBubble();
  buildPipeline();
}

function scrollOutputToBottom() {
  const s = document.getElementById('output-stream');
  s.scrollTop = s.scrollHeight;
}

/* ── LLM Provider defaults ─────────────────────────────────────────────────── */
const PROVIDER_DEFAULTS = {
  anthropic: { cheap: 'claude-haiku-4-5',       expensive: 'claude-opus-4-6'              },
  openai:    { cheap: 'gpt-4o-mini',            expensive: 'gpt-4o'                       },
  gemini:    { cheap: 'gemini-2.0-flash-lite',   expensive: 'gemini-2.5-pro-preview-03-25' },
  deepseek:  { cheap: 'deepseek-chat',          expensive: 'deepseek-reasoner'            },
  kimi:      { cheap: 'moonshot-v1-8k',         expensive: 'moonshot-v1-128k'             },
  qwen:      { cheap: 'qwen-turbo',             expensive: 'qwen-max'                     },
  glm:       { cheap: 'glm-4-flash',            expensive: 'glm-4-plus'                   },
};

function onProviderChange() {
  const d = PROVIDER_DEFAULTS[document.getElementById('llm_provider').value] || {};
  document.getElementById('llm_cheap_model').placeholder = d.cheap || '';
  document.getElementById('llm_expensive_model').placeholder = d.expensive || '';
}

/* ── Seed search ───────────────────────────────────────────────────────────── */
function toggleSeedSearch() {
  const p = document.getElementById('seed-search-panel');
  const vis = p.style.display !== 'none';
  p.style.display = vis ? 'none' : 'block';
  if (!vis) document.getElementById('seed-search-input').focus();
}

async function doSeedSearch() {
  const q = document.getElementById('seed-search-input').value.trim();
  const r = document.getElementById('seed-results');
  if (!q) return;
  r.innerHTML = `<div class="seed-empty">${t('msg.searching') || '...'}</div>`;
  try {
    const resp = await fetch(`/api/search-papers?q=${encodeURIComponent(q)}&limit=8`);
    const data = await resp.json();
    const papers = data.results || [];
    if (!papers.length) { r.innerHTML = `<div class="seed-empty">${t('msg.noResults')}</div>`; return; }
    r.innerHTML = '';
    papers.forEach(p => {
      const item = document.createElement('div');
      item.className = 'seed-result-item';
      const bestId = p.id || (p.arxiv_id ? `arxiv:${p.arxiv_id}` : '') || (p.doi || '');
      const idLabel = p.id ? `S2: ${p.id.slice(0,12)}...` : p.arxiv_id ? `arXiv: ${p.arxiv_id}` : p.doi ? `DOI: ${p.doi}` : '';
      item.innerHTML = `<div class="seed-result-title">${escapeHtml(p.title)}</div>
        <div class="seed-result-meta">${escapeHtml(p.authors)} · ${p.year||'?'} · ${p.citations} ${t('label.citations')||''}</div>
        ${idLabel ? `<div class="seed-result-id">${escapeHtml(idLabel)}</div>` : ''}`;
      item.onclick = () => addSeedId(bestId, p.title);
      r.appendChild(item);
    });
  } catch (err) {
    r.innerHTML = `<div class="seed-empty">${err.message}</div>`;
  }
}

function addSeedId(id, title) {
  if (!id) return;
  const input = document.getElementById('seeds');
  const existing = input.value.split(',').map(s => s.trim()).filter(Boolean);
  if (!existing.includes(id)) { existing.push(id); input.value = existing.join(', '); }
  document.getElementById('seed-search-panel').style.display = 'none';
  appendChatMessage('system', `${t('msg.seedAdded')}: ${title || id}`);
}

/* ── Seed PDF upload ───────────────────────────────────────────────────────── */
function triggerSeedPDFUpload() { document.getElementById('seed-pdf-input').click(); }

async function handleSeedPDFUpload(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  appendChatMessage('system', t('msg.uploading'));
  const fd = new FormData(); fd.append('file', file);
  try {
    const resp = await fetch('/api/upload-seed-pdf', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.error) { appendChatMessage('error', `${t('msg.uploadFail')}: ${data.error}`); }
    else {
      const refs = document.getElementById('local_seed_refs');
      const ex = refs.value.split(',').filter(Boolean); ex.push(data.ref); refs.value = ex.join(',');
      const si = document.getElementById('seeds');
      const sx = si.value.split(',').map(s=>s.trim()).filter(Boolean); sx.push(data.ref); si.value = sx.join(', ');
      appendChatMessage('system', `${t('msg.uploadOk')}: ${file.name}`);
    }
  } catch (err) { appendChatMessage('error', `${t('msg.uploadFail')}: ${err.message}`); }
  inputEl.value = '';
}

/* ── Start document upload ──────────────────────────────────────────────────── */
let uploadedStartDoc = null;

function triggerStartDocUpload() { document.getElementById('start-doc-input').click(); }

function handleStartDocUpload(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  const statusEl = document.getElementById('start-doc-status');
  statusEl.style.display = 'block';
  statusEl.style.color = 'var(--text-dim)';
  statusEl.textContent = (t('msg.startDocUploading') || 'Uploading...') + ' 0%';

  const fd = new FormData();
  fd.append('file', file);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/upload-start-doc');

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      statusEl.textContent = (t('msg.startDocUploading') || 'Uploading...') + ` ${pct}%`;
    }
  };

  xhr.onload = () => {
    try {
      const data = JSON.parse(xhr.responseText);
      if (xhr.status >= 400 || data.error) {
        statusEl.textContent = `${t('msg.startDocFail') || 'Failed'}: ${data.error || xhr.statusText}`;
        statusEl.style.color = 'var(--danger)';
      } else {
        uploadedStartDoc = { filename: data.filename, path: data.path };
        statusEl.textContent = `${t('msg.startDocUploaded') || 'Uploaded'}: ${file.name}`;
        statusEl.style.color = 'var(--success)';
      }
    } catch (_) {
      // Server returned non-JSON (e.g. "Internal Server Error")
      statusEl.textContent = `${t('msg.startDocFail') || 'Failed'}: HTTP ${xhr.status} — ${xhr.responseText.slice(0, 120)}`;
      statusEl.style.color = 'var(--danger)';
    }
  };

  xhr.onerror = () => {
    statusEl.textContent = `${t('msg.startDocFail') || 'Failed'}: network error`;
    statusEl.style.color = 'var(--danger)';
  };

  xhr.send(fd);
  inputEl.value = '';
}

/* ── Download References from PDF ─────────────────────────────────────────── */
function triggerRefsPDFUpload() { document.getElementById('refs-pdf-input').click(); }

async function handleRefsPDFUpload(inputEl) {
  const file = inputEl.files[0];
  if (!file) return;
  const statusEl = document.getElementById('dlrefs-status');
  const resultsEl = document.getElementById('dlrefs-results');
  statusEl.style.display = 'block';
  resultsEl.style.display = 'none';
  statusEl.textContent = (t('msg.dlrefsRunning')||'') + ` (${file.name})`;
  const fd = new FormData(); fd.append('file', file);
  try {
    const resp = await fetch('/api/download-refs', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.error) { statusEl.textContent = `${t('msg.dlrefsFail')}: ${data.error}`; return; }
    statusEl.textContent = `${t('msg.dlrefsOk')} — ${data.summary}`;
    resultsEl.style.display = 'block';
    resultsEl.innerHTML = '';
    data.results.forEach(r => {
      const row = document.createElement('div');
      row.style.cssText = 'padding:4px 0;border-bottom:1px solid var(--border);font-size:.75rem';
      row.textContent = `${r.status==='ok'?'✅':r.status==='skipped'?'⏭':'❌'}${r.source?' ['+r.source+']':''} ${r.title}`;
      resultsEl.appendChild(row);
    });
  } catch (err) { statusEl.textContent = `${t('msg.dlrefsFail')}: ${err.message}`; }
  inputEl.value = '';
}

/* ── Folder picker ─────────────────────────────────────────────────────────── */
async function browsePapersDir() {
  try {
    const data = await (await fetch('/api/browse-dir')).json();
    if (data.path) document.getElementById('local_papers_dir').value = data.path;
    else if (data.error) appendChatMessage('error', `${t('msg.browseFail')}: ${data.error}`);
  } catch (err) { appendChatMessage('error', `${t('msg.browseFail')}: ${err.message}`); }
}

/* ── Form submit ───────────────────────────────────────────────────────────── */
document.getElementById('config-form').addEventListener('submit', e => { e.preventDefault(); if (!isRunning) startSurvey(); });

function startSurvey() {
  const form = document.getElementById('config-form');
  const data = new FormData(form);
  const sp = []; form.querySelectorAll('input[name="search_providers"]:checked').forEach(el => sp.push(el.value));
  const config = {
    topic: data.get('topic')||'', seeds: data.get('seeds')||'',
    local_seed_refs: data.get('local_seed_refs')||'',
    llm_provider: data.get('llm_provider')||'anthropic',
    llm_api_key: data.get('llm_api_key')||'',
    llm_cheap_model: data.get('llm_cheap_model')||'',
    llm_expensive_model: data.get('llm_expensive_model')||'',
    s2_api_key: data.get('s2_api_key')||'',
    search_providers: sp,
    output_format: data.get('output_format')||'latex',
    sensitivity: data.get('sensitivity')||'balanced',
    generate_mindmap: data.get('generate_mindmap')==='on',
    local_papers_dir: data.get('local_papers_dir')||'',
    start_doc_path: uploadedStartDoc ? uploadedStartDoc.path : '',
    max_papers: parseInt(document.getElementById('tax-max-papers')?.value || '200', 10),
    lang: currentLang,
  };
  if (!config.topic.trim()) { alert(t('msg.topicRequired')); return; }

  jobId = crypto.randomUUID();
  ws = new WebSocket(`ws://${location.host}/ws/${jobId}`);
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'start', config }));
    setRunning(true);
    clearOutput();
    appendChatMessage('system', t('msg.started'));
  };
  ws.onmessage = e => { _lastServerError = ''; handleMessage(JSON.parse(e.data)); };
  ws.onclose = () => {
    if (isRunning) {
      appendChatMessage('system', t('msg.disconnected'));
      setRunning(false);
    }
  };
  ws.onerror = () => {
    // If the server already sent an error message, don't show a generic one
    if (!_lastServerError) {
      appendChatMessage('error', t('msg.wsError'));
    }
    setRunning(false);
  };
}

function stopSurvey() {
  if (ws) ws.close();
  setRunning(false);
  appendChatMessage('system', t('msg.stopped'));
}

/* ── WebSocket message handler ─────────────────────────────────────────────── */
function handleMessage(msg) {
  switch (msg.type) {
    case 'output':
      agentBuffer += (msg.text || '');
      clearTimeout(agentTimer);
      agentTimer = setTimeout(flushAgentBuffer, FLUSH_MS);
      break;
    case 'progress':
      finishAgentBubble();
      updateProgress(msg.phase, msg.pct);
      break;
    case 'stats':
      updateStats(msg);
      break;
    case 'interrupt':
      finishAgentBubble();
      showInterrupt(msg.data || {});
      break;
    case 'taxonomy_update':
      taxVizUpdate(msg.data);
      break;
    case 'done':
      finishAgentBubble();
      setRunning(false);
      showDone();
      break;
    case 'error':
      finishAgentBubble();
      _lastServerError = msg.message || '';
      appendChatMessage('error', (t('msg.error')||'') + _lastServerError);
      setRunning(false);
      break;
    case 'ping': break;
  }
}

/* ── Progress ──────────────────────────────────────────────────────────────── */
function updateProgress(phase, pct) {
  const isNew = (phase !== currentPhase);
  updatePipeline(phase);
  const name = t(`phase.${phase}`) || phase;
  setSubStatus(`${name} — ${pct}%`);
  if (isNew && phase !== 'starting') appendChatMessage('system', name);
}

function updateStats(msg) {
  if (msg.paper_count !== undefined) {
    const label = currentLang === 'zh' ? `${msg.paper_count} 篇论文` : `${msg.paper_count} papers found`;
    setSubStatus(label);
    // Also update the paper count label near the max-papers control
    const countLabel = document.getElementById('tax-paper-count-label');
    if (countLabel) {
      countLabel.textContent = `/ ${msg.paper_count}`;
      countLabel.dataset.count = msg.paper_count;
    }
  }
}

/* ── Interrupt handler ─────────────────────────────────────────────────────── */
function showInterrupt(data) {
  interruptActive = true;
  const itype = data.type || 'dialogue';
  const options = {
    dialogue:        { header: 'interrupt.dialogue', opts: [] },
    survey_decision: { header: 'interrupt.survey_decision', opts: [
      { key: 'opt.continue', value: '1' }, { key: 'opt.abort', value: '2' }] },
    taxonomy_review: { header: 'interrupt.taxonomy_review', opts: [
      { key: 'opt.approve', value: 'approve' }, { key: 'opt.reject', value: 'reject' }] },
    outline_review:  { header: 'interrupt.outline_review', opts: [
      { key: 'opt.confirmOutline', value: 'approve' }] },
  };
  const cfg = options[itype] || options.dialogue;

  // Build header text
  let headerText = t(cfg.header) || '';
  if (data.proposal) {
    const p = data.proposal;
    headerText += `\n${p.description || ''} — ${p.reason || ''}`;
  }
  if (data.outline) {
    const lines = (data.outline || []).sort((a,b)=>(a.order||0)-(b.order||0)).map(s=>`${s.order}. ${s.title}`).join('\n');
    headerText += '\n' + lines;
  }
  // If the interrupt carries the agent's message, show it as a chat bubble first
  if (data.message && data.message.trim()) {
    finishAgentBubble();
    appendChatMessage('agent', data.message);
  }

  // For non-dialogue types (survey_decision, taxonomy_review, outline_review),
  // also show the prompt header as a separate bubble
  if (itype !== 'dialogue') {
    appendChatMessage('agent', headerText);
  }

  // Quick actions
  const actionsEl = document.getElementById('chat-quick-actions');
  actionsEl.innerHTML = '';
  cfg.opts.forEach(opt => {
    const btn = document.createElement('button');
    btn.className = 'chat-quick-btn';
    btn.textContent = t(opt.key) || opt.value;
    btn.onclick = () => { document.getElementById('chat-input').value = opt.value; sendResume(); };
    actionsEl.appendChild(btn);
  });
  actionsEl.style.display = cfg.opts.length ? 'flex' : 'none';

  // Enable chat input
  const ci = document.getElementById('chat-input');
  const sb = document.getElementById('chat-send-btn');
  ci.disabled = false; sb.disabled = false;
  ci.placeholder = t('placeholder.reply') || '';
  ci.value = ''; ci.focus();
  scrollOutputToBottom();
}

function sendResume() {
  const ci = document.getElementById('chat-input');
  const val = ci.value.trim();
  if (!val) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'resume', value: val }));
    appendChatMessage('user', val);
    interruptActive = false;
    ci.value = ''; ci.disabled = true;
    document.getElementById('chat-send-btn').disabled = true;
    ci.placeholder = t('placeholder.agentWorking') || '';
    document.getElementById('chat-quick-actions').style.display = 'none';
  }
}

/* ── Done ──────────────────────────────────────────────────────────────────── */
function showDone() {
  updateProgress('complete', 100);
  setBadge('done', t('status.done'));
  document.getElementById('done-message').textContent = t('done.body');
  document.getElementById('done-modal').style.display = 'flex';
}
function closeDoneModal() { document.getElementById('done-modal').style.display = 'none'; }

/* ── UI state ──────────────────────────────────────────────────────────────── */
function setRunning(running) {
  isRunning = running;
  document.getElementById('start-btn').style.display = running ? 'none' : 'block';
  document.getElementById('stop-btn').style.display  = running ? 'block' : 'none';
  document.getElementById('start-btn').disabled = running;
  if (!running) {
    interruptActive = false;
    const ci = document.getElementById('chat-input');
    if (ci) { ci.disabled = true; ci.placeholder = t('placeholder.agentWorking') || ''; }
    const sb = document.getElementById('chat-send-btn');
    if (sb) sb.disabled = true;
    const qa = document.getElementById('chat-quick-actions');
    if (qa) qa.style.display = 'none';
    if (document.getElementById('done-modal').style.display === 'none' ||
        !document.getElementById('done-modal').style.display) {
      setBadge('idle', t('status.idle'));
    }
  } else {
    setBadge('running', t('status.running'));
  }
}

function setBadge(cls, text) {
  const b = document.getElementById('status-badge');
  b.className = `badge badge-${cls}`;
  b.textContent = text || '';
}

function taxUpdateMaxPapers(val) {
  const n = parseInt(val, 10);
  if (isNaN(n) || n < 10) return;
  // Don't allow setting below current classified paper count
  const classified = parseInt(document.getElementById('tax-paper-count-label')?.dataset.count || '0', 10);
  if (n < classified) {
    document.getElementById('tax-max-papers').value = classified;
    return;
  }
  // If running, send new limit via WebSocket
  if (ws && ws.readyState === WebSocket.OPEN && isRunning) {
    ws.send(JSON.stringify({ type: 'set_max_papers', value: n }));
  }
}

/* ── Utility ───────────────────────────────────────────────────────────────── */
function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Init ──────────────────────────────────────────────────────────────────── */
applyTheme();
applyTranslations();
onProviderChange();
buildPipeline();
