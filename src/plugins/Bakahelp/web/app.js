(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('catalog').textContent);
  const $ = id => document.getElementById(id);
  const plugins = new Map(data.plugins.map(p => [p.id, p]));
  const labels = data.labels;
  const categories = ['全部功能', 'Malody', 'osu!', '创作与娱乐', '通用', '管理'];
  let category = '全部功能', limit = 40, toastTimer, indexPinned = false;
  const categoryOf = e => plugins.get(e.plugin)?.category || (/malody/i.test(e.plugin) ? 'Malody' : /osu/i.test(e.plugin) ? 'osu!' : '通用');
  const copyKinds = ['command', 'shell', 'fullmatch', 'alconna'];
  const primaryOf = e => {
    const values = e.triggers.filter(t => copyKinds.includes(t.kind)).flatMap(t => t.values);
    const documented = e.doc.usage?.split(/\s+/)[0];
    return values.includes(documented) ? documented : values.sort((a,b) => a.length - b.length || Number(a !== a.toLowerCase()) - Number(b !== b.toLowerCase()) || a.localeCompare(b, 'zh-CN'))[0];
  };
  const titleOf = e => primaryOf(e) || labels[e.triggers[0].kind] || '事件触发';
  const entries = data.entries.map(e => ({...e, search: JSON.stringify([e.plugin, plugins.get(e.plugin), e.triggers, e.doc]).toLocaleLowerCase()}));
  entries.sort((a, b) => categories.indexOf(categoryOf(a)) - categories.indexOf(categoryOf(b)) || (plugins.get(a.plugin)?.name || a.plugin).localeCompare(plugins.get(b.plugin)?.name || b.plugin, 'zh-CN') || Number(Boolean(b.doc.description)) - Number(Boolean(a.doc.description)) || titleOf(a).localeCompare(titleOf(b), 'zh-CN'));
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
  const option = (parent, value, text) => { const node = el('option', text); node.value = value; parent.append(node); };
  for (const c of categories) {
    const count = entries.filter(e => c === '全部功能' || categoryOf(e) === c).length;
    const button = el('button'); button.type = 'button'; button.append(el('span', c), el('span', String(count)));
    button.dataset.category = c; button.setAttribute('aria-pressed', String(c === category));
    button.addEventListener('click', () => { category = c; $('plugin').value = ''; limit = 40; render(); });
    $('categories').append(button);
  }
  for (const p of [...plugins.values()].filter(p => entries.some(e => e.plugin === p.id)).sort((a,b) => a.name.localeCompare(b.name, 'zh-CN'))) option($('plugin'), p.id, p.name);
  for (const kind of [...new Set(entries.flatMap(e => e.triggers.map(t => t.kind)))]) option($('kind'), kind, labels[kind] || kind);
  $('updated').textContent = `更新于 ${new Date(data.generated_at).toLocaleDateString('zh-CN')}`;
  function announce(message) { $('toast').textContent = message; $('toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('visible'), 2400); }
  async function copy(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
      else { const area = el('textarea', text); area.style.position = 'fixed'; area.style.left = '-9999px'; document.body.append(area); area.select(); const ok = document.execCommand('copy'); area.remove(); if (!ok) throw new Error('clipboard'); }
      announce('已复制，可以粘贴到聊天中');
    } catch { announce('复制失败，请选中指令手动复制'); }
  }
  function chip(value, copyable) { const node = el(copyable ? 'button' : 'code', value, 'trigger'); if (copyable) { node.type = 'button'; node.dataset.copy = value; node.setAttribute('aria-label', `复制 ${value}`); node.addEventListener('click', () => copy(value)); } return node; }
  function entryView(e) {
    const item = el('tr', undefined, 'entry'); item.id = e.id;
    const feature = el('th', undefined, 'feature-cell'); feature.scope = 'row';
    const primary = primaryOf(e), title = el('h3');
    if (primary) { const button = chip(primary, true); button.classList.add('primary-command'); title.append(button); }
    else title.textContent = titleOf(e);
    feature.append(title);
    if (e.doc.title) feature.append(el('span', e.doc.title, 'function-name'));
    feature.append(el('span', e.doc.audience || (e.restricted ? '权限限制' : labels[e.triggers[0].kind]), 'badge'));
    const input = el('td', undefined, 'input-cell');
    const usage = el('td', undefined, 'usage-cell');
    if (e.doc.description) usage.append(el('p', e.doc.description, 'entry-desc'));
    if (e.doc.usage) usage.append(el('code', e.doc.usage, 'usage-syntax'));
    const triggers = el('div', undefined, 'triggers');
    for (const t of e.triggers) for (const value of t.values.filter(v => v !== primary).slice(0, 8)) triggers.append(chip(value, copyKinds.includes(t.kind)));
    input.append(triggers);
    if (!triggers.childElementCount) input.append(el('span', primary ? '无其他别名' : '由事件或上下文触发', 'needs-doc'));
    if (!e.doc.description && !e.doc.usage) usage.append(el('p', '详细用法待补充。', 'needs-doc'));
    const details = el('details'); details.append(el('summary', '用法与触发详情'));
    const content = el('div', undefined, 'details-content');
    if (e.doc.usage) { content.append(el('h4', '使用方法'), el('p', e.doc.usage)); }
    if (e.doc.examples?.length) { content.append(el('h4', '发送示例')); const examples = el('div', undefined, 'triggers'); e.doc.examples.forEach(v => examples.append(chip(v, true))); content.append(examples); }
    for (const t of e.triggers) {
      content.append(el('h4', labels[t.kind] || t.kind));
      if (t.values.length) content.append(el('p', t.values.join('\n')));
      if (t.kind === 'regex' || t.kind === 'shortcut') content.append(el('p', '这是匹配规则；请参照使用说明组织消息，不要把规则原样发送。'));
      if (t.kind === 'startswith') content.append(el('p', '消息以列出的文字开头。'));
      if (t.kind === 'endswith') content.append(el('p', '消息以列出的文字结尾。'));
      if (t.kind === 'keyword') content.append(el('p', '消息中包含任一列出的关键词。'));
      if (t.ignorecase) content.append(el('p', '不区分大小写。'));
      if (t.whitespace !== undefined) content.append(el('p', `参数前空白要求：${t.whitespace === true ? '必须有空白' : t.whitespace === false ? '不可有空白' : JSON.stringify(t.whitespace)}`));
      if (t.syntax) content.append(el('pre', t.syntax));
    }
    if (e.conditions.length) content.append(el('h4', '附加条件'), el('p', `还需满足插件自定义判断（${e.conditions.join('、')}），具体条件请参考说明。`));
    if (e.permissions.length) content.append(el('h4', '权限规则'), el('p', e.permissions.join('、')));
    if (e.doc.notes) content.append(el('h4', '注意'), el('p', e.doc.notes));
    content.append(el('h4', '条目标识'), el('p', e.id)); details.append(content); usage.append(details); item.append(feature, input, usage); return item;
  }
  function openIndex(open) { $('index-panel').hidden = !open; $('index-toggle').setAttribute('aria-expanded', String(open)); }
  function closeIndex() { indexPinned = false; openIndex(false); }
  function scrollToSection(node) {
    if (!node) return;
    node.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'});
    node.tabIndex = -1; node.focus({preventScroll: true});
  }
  function renderIndex(filtered) {
    const groups = new Map();
    filtered.forEach((e, i) => { const group = groups.get(e.plugin) || {count: 0, end: 0}; group.count++; group.end = i; groups.set(e.plugin, group); });
    const buttons = [...groups].map(([id, group]) => {
      const button = el('button'); button.type = 'button'; button.dataset.indexPlugin = id;
      button.append(el('span', plugins.get(id)?.name || id), el('span', String(group.count), 'index-count'));
      button.addEventListener('click', () => {
        limit = Math.max(limit, group.end + 1); render(); closeIndex();
        scrollToSection($('group-' + id));
      });
      return button;
    });
    $('index-links').replaceChildren(...(buttons.length ? buttons : [el('p', '当前筛选没有匹配的插件。')]));
  }
  function render() {
    const words = $('search').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const filtered = entries.filter(e => (category === '全部功能' || categoryOf(e) === category) && (!$('plugin').value || e.plugin === $('plugin').value) && (!$('kind').value || e.triggers.some(t => t.kind === $('kind').value)) && (!$('documented').checked || e.doc.description || e.doc.usage) && words.every(w => e.search.includes(w)));
    const rows = []; let previousPlugin;
    for (const entry of filtered.slice(0, limit)) {
      if (entry.plugin !== previousPlugin) {
        const group = el('tr', undefined, 'plugin-group'); group.id = 'group-' + entry.plugin;
        const heading = el('th'); heading.colSpan = 3; heading.scope = 'colgroup';
        heading.append(el('span', plugins.get(entry.plugin)?.name || entry.plugin));
        const total = filtered.filter(e => e.plugin === entry.plugin).length;
        heading.append(el('span', `${total} 项功能`, 'group-count'));
        group.append(heading); rows.push(group); previousPlugin = entry.plugin;
      }
      rows.push(entryView(entry));
    }
    $('results').replaceChildren(...rows);
    $('table-scroll').hidden = filtered.length === 0;
    renderIndex(filtered);
    $('results-title').textContent = category; $('count').textContent = `${filtered.length} 项功能 · ${new Set(filtered.map(e => e.plugin)).size} 个插件`;
    $('empty').hidden = filtered.length !== 0; $('more').hidden = filtered.length <= limit;
    $('more').textContent = `显示更多（还剩 ${Math.max(0, filtered.length - limit)} 项）`;
    document.querySelectorAll('[data-category]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.category === category)));
  }
  function reset() { category = '全部功能'; $('search').value = ''; $('plugin').value = ''; $('kind').value = ''; $('documented').checked = false; limit = 40; render(); }
  $('search').addEventListener('input', () => { limit = 40; render(); });
  ['plugin', 'kind', 'documented'].forEach(id => $(id).addEventListener('change', () => { limit = 40; render(); }));
  document.querySelectorAll('[data-query]').forEach(b => b.addEventListener('click', () => { $('search').value = b.dataset.query; limit = 40; render(); $('search').focus(); }));
  $('reset').addEventListener('click', reset); $('empty-reset').addEventListener('click', reset);
  $('more').addEventListener('click', () => { limit += 40; render(); });
  $('index-toggle').addEventListener('click', () => { indexPinned = !indexPinned; openIndex(indexPinned); });
  $('floating-index').addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') openIndex(true); });
  $('floating-index').addEventListener('pointerleave', () => { if (!indexPinned && !$('index-panel').contains(document.activeElement)) openIndex(false); });
  $('floating-index').addEventListener('focusout', e => { if (!indexPinned && !$('floating-index').contains(e.relatedTarget)) openIndex(false); });
  $('index-close').addEventListener('click', () => { closeIndex(); $('index-toggle').focus(); });
  $('index-top').addEventListener('click', () => { closeIndex(); scrollToSection($('search')); });
  document.addEventListener('pointerdown', e => { if (!$('floating-index').contains(e.target)) closeIndex(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('index-panel').hidden) { closeIndex(); $('index-toggle').focus(); } });
  document.addEventListener('keydown', event => { if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) { event.preventDefault(); $('search').focus(); } });
  render();
})();
