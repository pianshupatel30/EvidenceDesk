const $ = (id) => document.getElementById(id);
const pct = (value) => `${(100 * value).toFixed(1)}%`;
const ms = (value) => `${value.toFixed(1)} ms`;
const money = (value) => value === null ? 'Unknown' : `$${value.toFixed(6)}`;
let documents = [];
let lastAnswer = '';
let evaluationRows = [];
let toastTimer;
let previewRequest = 0;
let uploading = false;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function documentTitle(filename) {
  return filename.replace(/^\d+_/, '').replace(/\.[^.]+$/, '').replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
}

function notify(message) {
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 7000);
}

function showError(error) {
  notify(error.message || String(error));
}

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  };
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'The request could not be completed. Check your input and try again.');
  }
  return data;
}

function renderDocuments() {
  const query = $('file-search').value.trim().toLowerCase();
  const matches = documents.filter(name => `${name} ${documentTitle(name)}`.toLowerCase().includes(query));
  $('document-list').replaceChildren(...matches.map(name => {
    const item = element('li');
    const button = element('button', undefined, 'document-button');
    const meta = element('span', undefined, 'document-meta');
    const type = name.split('.').pop().toUpperCase();
    meta.append(element('strong', documentTitle(name)), element('small', `${type} document`));
    button.append(element('span', type, 'file-icon'), meta, element('span', '↗', 'file-arrow'));
    button.addEventListener('click', () => openDocument(name));
    button.title = `Preview ${name}`;
    item.append(button);
    return item;
  }));
  $('library-empty').hidden = matches.length > 0;
}

async function loadInfo() {
  const data = await api('/api/health');
  documents = data.documents;
  $('connection').textContent = 'Local service connected';
  $('provider').textContent = data.provider === 'extractive' ? 'Excerpt mode' : `${data.provider} enabled`;
  $('document-count').textContent = documents.length;
  $('library-count').textContent = documents.length;
  $('chunk-count').textContent = data.chunks;
  $('index-version').textContent = `Version ${data.index_version}`;
  $('reranker-label').textContent = `Reranker ${data.reranker}`;
  $('vector-label').textContent = data.vector_backend === 'tfidf' ? 'BM25 + TF-IDF' : 'BM25 + semantic embeddings';
  $('mode-note').textContent = data.provider === 'extractive'
    ? 'Excerpt mode returns matching source text. Generated answers require a connected model.'
    : 'Generated answers include source references and verified exact quotes.';
  renderDocuments();
  if (data.warnings.length) showError(new Error(data.warnings.map(item => `${item.source}: ${item.error}`).join(' | ')));
}

async function openDocument(source) {
  const request = ++previewRequest;
  $('preview-title').textContent = documentTitle(source);
  $('preview-filename').textContent = source;
  $('preview-content').replaceChildren(element('p', 'Loading passages…'));
  if (!$('document-dialog').open) $('document-dialog').showModal();
  try {
    const data = await api(`/api/documents/${encodeURIComponent(source)}`);
    if (request !== previewRequest) return;
    $('preview-content').replaceChildren(...data.chunks.map((chunk, index) => {
      const section = element('section', undefined, 'preview-passage');
      section.append(element('small', `Passage ${index + 1} · page ${chunk.page}`), element('p', chunk.text));
      return section;
    }));
  } catch (error) {
    if (request === previewRequest) $('preview-content').replaceChildren(element('p', error.message));
  }
}

function renderAnswer(data) {
  lastAnswer = data.status === 'evidence' ? data.claims[0].text : data.answer;
  $('empty-result').hidden = true;
  $('answer-card').hidden = false;
  $('answer-heading').textContent = {
    evidence: 'From your documents', answered: 'An answer with evidence',
    abstained: 'More information needed', error: 'The request needs attention'
  }[data.status];
  $('answer-status').textContent = {
    evidence: 'Matching source excerpt', answered: 'Source IDs and quotes checked',
    abstained: 'Insufficient evidence', error: 'Model error'
  }[data.status];
  $('answer-body').textContent = lastAnswer;
  $('answer-metrics').replaceChildren(...[
    `Retrieval ${ms(data.retrieval_ms)}`, `Total ${ms(data.total_ms)}`, `API cost ${money(data.cost_usd)}`
  ].map(text => element('span', text)));
  $('citations').replaceChildren();
  data.claims.forEach(claim => {
    const hit = data.sources.find(source => source.id === claim.source_id);
    const citation = element('div', undefined, 'citation');
    const button = element('button', `${documentTitle(hit.source)} · page ${hit.page} ↗`);
    button.addEventListener('click', () => openDocument(hit.source));
    citation.append(button);
    if (data.status !== 'evidence') citation.append(element('p', `“${claim.quote}”`));
    $('citations').append(citation);
  });
  $('sources-panel').hidden = !data.sources.length;
  $('source-count').textContent = `${data.sources.length} matches`;
  $('sources').replaceChildren(...data.sources.map((hit, index) => {
    const details = element('details', undefined, 'source');
    const summary = element('summary');
    summary.append(element('span', index + 1, 'source-rank'), element('span', documentTitle(hit.source)));
    details.append(summary, element('small', `Page ${hit.page} · similarity ${hit.similarity.toFixed(3)} · term coverage ${pct(hit.coverage)}`), element('p', hit.text));
    return details;
  }));
}

$('ask-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (question.length < 3) {
    notify('Enter at least three characters for your question.');
    return;
  }
  $('ask-button').disabled = true;
  $('ask-button').textContent = 'Searching…';
  try {
    renderAnswer(await api('/api/ask', {question, mode: $('mode').value}));
  } catch (error) {
    showError(error);
  } finally {
    $('ask-button').disabled = false;
    $('ask-button').replaceChildren(document.createTextNode('Find evidence '), element('span', '↗'));
  }
});

document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => {
  $('question').value = button.dataset.question;
  $('question').focus();
}));

$('copy-answer').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(lastAnswer);
    notify('Answer copied.');
  } catch {
    notify('Clipboard access is unavailable. Select the answer text to copy it.');
  }
});

async function uploadFile(file) {
  if (!file || uploading) return;
  uploading = true;
  document.querySelectorAll('.upload-trigger').forEach(button => { button.disabled = true; });
  $('upload-status').textContent = 'Reading and indexing your document…';
  try {
    if (file.size > 5 * 1024 * 1024) throw new Error('Choose a file up to 5 MB.');
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('The file could not be read.'));
      reader.readAsDataURL(file);
    });
    const result = await api('/api/documents', {filename: file.name, content_base64: encoded});
    $('upload-status').textContent = result.deduplicated ? 'This document is already in your collection.' : 'Document added. Ready to search.';
    await loadInfo();
  } catch (error) {
    $('upload-status').textContent = error.message;
    showError(error);
  } finally {
    uploading = false;
    $('upload-file').value = '';
    document.querySelectorAll('.upload-trigger').forEach(button => { button.disabled = false; });
  }
}

document.querySelectorAll('.upload-trigger').forEach(button => button.addEventListener('click', () => $('upload-file').click()));
$('upload-file').addEventListener('change', event => uploadFile(event.target.files[0]));
$('dropzone').addEventListener('dragover', event => {
  event.preventDefault();
  $('dropzone').classList.add('dragging');
});
$('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragging'));
$('dropzone').addEventListener('drop', event => {
  event.preventDefault();
  $('dropzone').classList.remove('dragging');
  if (event.dataTransfer.files.length > 1) {
    notify('Add one document at a time.');
    return;
  }
  uploadFile(event.dataTransfer.files[0]);
});
$('file-search').addEventListener('input', renderDocuments);
$('close-document').addEventListener('click', () => $('document-dialog').close());
$('document-dialog').addEventListener('click', event => {
  const box = $('document-dialog').getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) $('document-dialog').close();
});

function tableRow(values) {
  const row = element('tr');
  values.forEach(value => row.append(element('td', value)));
  return row;
}

function renderEvaluationRows() {
  const filtered = evaluationRows.filter(row => !$('failures-only').checked || !row.passed);
  $('evaluation-rows').replaceChildren(...filtered.map(row => {
    const details = element('details', undefined, 'eval-row');
    const summary = element('summary');
    summary.append(element('span', row.question), element('span', row.passed ? 'Pass' : 'Review', row.passed ? 'pass' : 'fail'));
    details.append(summary, element('p', `Expected ${row.answerable ? 'answerable' : 'unsupported'} · Gate ${row.accepted ? 'accepted' : 'rejected'} · Relevant source in top 5 ${row.hit_at_5 ? 'yes' : 'no'}`));
    details.append(element('p', `Expected sources — ${row.relevant_sources.join(', ') || 'none'}. Retrieved — ${row.retrieved_sources.join(', ') || 'none'}.`));
    return details;
  }));
  if (!filtered.length) $('evaluation-rows').append(element('p', 'No review cases in this run.', 'muted'));
}

function renderEvaluation(data) {
  if (!data.available) {
    $('evaluation-status').textContent = 'Run the benchmark to generate a report.';
    return;
  }
  $('evaluation-status').textContent = `${data.question_count} questions · ${data.config.vector_backend} · ${new Date(data.created).toLocaleString()}${data.stale ? ' · Corpus or settings changed. Run the benchmark again.' : ''}`;
  $('evaluation-summary').replaceChildren(...data.results.map(row => tableRow([
    row.mode, pct(row.hit_at_5), row.mrr_at_5.toFixed(3), pct(row.unanswerable_rejection_rate), pct(row.answerable_acceptance_rate), ms(row.p95_retrieval_ms)
  ])));
  evaluationRows = data.results.find(row => row.mode === 'hybrid').rows.map(row => ({
    ...row, passed: row.answerable ? row.hit_at_5 && row.accepted : !row.accepted
  }));
  renderEvaluationRows();
}

$('failures-only').addEventListener('change', renderEvaluationRows);
$('evaluate-button').addEventListener('click', async () => {
  $('evaluate-button').disabled = true;
  $('evaluate-button').textContent = 'Evaluating…';
  $('evaluation-status').textContent = 'Running three retrieval methods over 60 questions…';
  try { renderEvaluation(await api('/api/evaluate', {})); }
  catch (error) { showError(error); }
  finally { $('evaluate-button').disabled = false; $('evaluate-button').textContent = 'Run benchmark ↗'; }
});

async function loadMetrics() {
  const data = await api('/api/metrics');
  const values = [
    ['Requests', data.requests, `Errors ${pct(data.error_rate)}`],
    ['P95 latency', ms(data.p95_ms), `Median ${ms(data.p50_ms)}`],
    ['Abstentions', pct(data.abstention_rate), 'Insufficient evidence'],
    ['Known API cost', money(data.known_cost_usd), `${data.unknown_cost_requests} unknown-cost requests`]
  ];
  $('metrics-stats').replaceChildren(...values.map(([label, value, detail]) => {
    const card = element('article');
    card.append(element('span', label), element('strong', value), element('small', detail));
    return card;
  }));
  $('request-rows').replaceChildren(...data.recent.map(row => tableRow([
    new Date(row.created).toLocaleTimeString(), row.status, row.retrieval_mode,
    ms(row.retrieval_ms), ms(row.generation_ms), `${row.usage.input_tokens ?? '?'} / ${row.usage.output_tokens ?? '?'}`, money(row.cost_usd)
  ])));
  if (!data.recent.length) {
    const row = tableRow(['Your first request will appear here after you ask a question.']);
    row.firstChild.colSpan = 7;
    $('request-rows').append(row);
  }
}

$('refresh-metrics').addEventListener('click', async () => {
  $('refresh-metrics').disabled = true;
  try { await loadMetrics(); }
  catch (error) { showError(error); }
  finally { $('refresh-metrics').disabled = false; }
});

document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', async () => {
  const tab = button.dataset.tab;
  document.querySelectorAll('.tab').forEach(section => { section.hidden = section.id !== tab; });
  document.querySelectorAll('.nav').forEach(nav => {
    nav.classList.toggle('active', nav === button);
    if (nav === button) nav.setAttribute('aria-current', 'page');
    else nav.removeAttribute('aria-current');
  });
  $('breadcrumb').textContent = {workspace: 'Research desk', benchmark: 'Evaluation', activity: 'Activity'}[tab];
  try {
    if (tab === 'benchmark') renderEvaluation(await api('/api/evaluation'));
    if (tab === 'activity') await loadMetrics();
  } catch (error) { showError(error); }
}));

loadInfo().catch(error => { $('connection').textContent = 'Service unavailable'; showError(error); });
