(() => {
  'use strict';

  const data = JSON.parse(document.getElementById('catalog').textContent);
  const getElement = id => document.getElementById(id);
  const plugins = new Map(data.plugins.map(plugin => [plugin.id, plugin]));
  const labels = data.labels;
  const categories = ['全部功能', 'Malody', 'osu!', '创作与娱乐', '通用', '管理'];
  const copyKinds = new Set(['command', 'shell', 'fullmatch', 'alconna']);
  const memePlugin = 'nonebot_plugin_memes';

  let activeCategory = '全部功能';
  let visibleLimit = 40;
  let toastTimer;
  let indexPinned = false;

  const categoryOf = entry => plugins.get(entry.plugin)?.category
    || (/malody/i.test(entry.plugin) ? 'Malody' : /osu/i.test(entry.plugin) ? 'osu!' : '通用');
  const isRegexCommand = value => /(?:^|\/)re:/.test(value);

  function primaryCommand(entry) {
    const values = entry.triggers
      .filter(trigger => copyKinds.has(trigger.kind))
      .flatMap(trigger => trigger.values || [])
      .filter(value => !isRegexCommand(value));
    const documented = entry.doc.usage?.split(/\s+/)[0];
    if (values.includes(documented)) return documented;
    return values.sort((left, right) => left.length - right.length
      || Number(left !== left.toLowerCase()) - Number(right !== right.toLowerCase())
      || left.localeCompare(right, 'zh-CN'))[0];
  }

  function triggerText(entry) {
    if (entry.doc.trigger_label) return entry.doc.trigger_label;
    const primary = primaryCommand(entry);
    if (primary) return primary;

    const trigger = entry.triggers[0];
    if (!trigger) return '事件或上下文触发';
    if (trigger.kind === 'regex') return '符合消息格式时触发';
    if (trigger.kind === 'startswith') return `消息以「${trigger.values.join(' / ')}」开头`;
    if (trigger.kind === 'endswith') return `消息以「${trigger.values.join(' / ')}」结尾`;
    if (trigger.kind === 'keyword') return `消息包含「${trigger.values.join(' / ')}」`;
    if (trigger.kind === 'message') return '满足消息条件时触发';
    if (trigger.kind === 'notice') return '收到相应通知时触发';
    if (trigger.kind === 'request') return '收到相应请求时触发';
    return labels[trigger.kind] || '事件或上下文触发';
  }

  function argumentsText(entry) {
    if (entry.doc.arguments) return entry.doc.arguments;
    if (entry.doc.usage) {
      const parts = entry.doc.usage.trim().split(/\s+/);
      return parts.length > 1 ? parts.slice(1).join(' ') : '无';
    }
    for (const trigger of entry.triggers) {
      if (trigger.syntax) {
        const command = trigger.syntax.split('\n')[0].replace(/^\[[^]]*\]/, '').trim();
        const remainder = command.split(/\s+/, 2)[1];
        if (remainder) {
          return remainder
            .replace(/<meme_params:.*?>/g, '<图片、文字或@用户>')
            .replace(/<text:.*?>/g, '<文字内容>')
            .replace(/<args:.*?>/g, '<参数>')
            .replace(/<(id|cid|sid|uid):.*?>/g, '<$1>');
        }
      }
    }
    if (entry.triggers.some(trigger => ['message', 'notice', 'request', 'meta_event'].includes(trigger.kind))) {
      return '无（由消息或事件触发）';
    }
    if (entry.triggers.some(trigger => ['fullmatch', 'startswith', 'endswith', 'keyword'].includes(trigger.kind))) {
      return '无';
    }
    return '参数格式待补充';
  }

  const entries = data.entries.map(entry => ({
    ...entry,
    search: JSON.stringify([
      entry.plugin,
      plugins.get(entry.plugin)?.name,
      categoryOf(entry),
      entry.triggers,
      entry.doc,
    ])
      .toLocaleLowerCase(),
  }));

  entries.sort((left, right) => categories.indexOf(categoryOf(left)) - categories.indexOf(categoryOf(right))
    || (plugins.get(left.plugin)?.name || left.plugin)
      .localeCompare(plugins.get(right.plugin)?.name || right.plugin, 'zh-CN')
    || triggerText(left).localeCompare(triggerText(right), 'zh-CN'));

  const createElement = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  const addOption = (parent, value, text) => {
    const node = createElement('option', text);
    node.value = value;
    parent.append(node);
  };

  for (const category of categories) {
    const count = entries.filter(entry => category === '全部功能' || categoryOf(entry) === category).length;
    const button = createElement('button');
    button.type = 'button';
    button.append(createElement('span', category), createElement('span', String(count)));
    button.dataset.category = category;
    button.setAttribute('aria-pressed', String(category === activeCategory));
    button.addEventListener('click', () => {
      activeCategory = category;
      getElement('plugin').value = '';
      visibleLimit = 40;
      render();
    });
    getElement('categories').append(button);
  }

  for (const plugin of [...plugins.values()]
    .filter(plugin => entries.some(entry => entry.plugin === plugin.id))
    .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))) {
    addOption(getElement('plugin'), plugin.id, plugin.name);
  }

  for (const kind of [...new Set(entries.flatMap(entry => entry.triggers.map(trigger => trigger.kind)))]) {
    addOption(getElement('kind'), kind, labels[kind] || kind);
  }

  function announce(message) {
    getElement('toast').textContent = message;
    getElement('toast').classList.add('visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => getElement('toast').classList.remove('visible'), 2400);
  }

  async function copy(text) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const area = createElement('textarea', text);
        area.style.position = 'fixed';
        area.style.left = '-9999px';
        document.body.append(area);
        area.select();
        const copied = document.execCommand('copy');
        area.remove();
        if (!copied) throw new Error('Clipboard unavailable');
      }
      announce('已复制，可以粘贴到聊天中');
    } catch {
      announce('复制失败，请选中触发名手动复制');
    }
  }

  function triggerButton(value) {
    const button = createElement('button', value, 'trigger');
    button.type = 'button';
    button.setAttribute('aria-label', `复制 ${value}`);
    button.addEventListener('click', () => copy(value));
    return button;
  }

  function addRuleDetails(container, entry) {
    const details = createElement('details', undefined, 'entry-details');
    const summary = createElement('summary', '其他触发方式与使用条件');
    const content = createElement('div', undefined, 'details-content');

    if (entry.doc.usage) {
      content.append(createElement('h4', '使用方法'), createElement('p', entry.doc.usage));
    }
    if (entry.doc.examples?.length) {
      content.append(createElement('h4', '发送示例'));
      const examples = createElement('div', undefined, 'triggers');
      entry.doc.examples.forEach(example => examples.append(triggerButton(example)));
      content.append(examples);
    }

    for (const trigger of entry.triggers) {
      content.append(createElement('h4', labels[trigger.kind] || trigger.kind));
      if (trigger.values.length) {
        const values = trigger.kind === 'regex' || trigger.kind === 'shortcut'
          ? entry.doc.trigger_label || '按上方说明匹配相应文字格式'
          : trigger.values.join('\n');
        content.append(createElement('p', values));
      }
      if (trigger.kind === 'startswith') content.append(createElement('p', '消息以列出的文字开头。'));
      if (trigger.kind === 'endswith') content.append(createElement('p', '消息以列出的文字结尾。'));
      if (trigger.kind === 'keyword') content.append(createElement('p', '消息中包含列出的关键词。'));
      if (trigger.ignorecase) content.append(createElement('p', '英文字母不区分大小写。'));
      if (trigger.whitespace !== undefined) {
        const whitespace = trigger.whitespace ? '参数前需要空格' : '参数前不需要空格';
        content.append(createElement('p', whitespace));
      }
      if (trigger.syntax && !trigger.syntax.includes('re:')) {
        content.append(createElement('pre', trigger.syntax));
      }
    }

    if (entry.conditions.length) {
      content.append(
        createElement('h4', '触发条件'),
        createElement('p', entry.doc.condition_label || '需要满足该功能的消息上下文条件。'),
      );
    }
    if (entry.permissions.length || entry.doc.audience) {
      content.append(createElement('h4', '使用范围'));
      content.append(createElement('p', entry.doc.audience || '需要插件要求的权限。'));
    }
    if (entry.doc.notes) content.append(createElement('h4', '说明'), createElement('p', entry.doc.notes));

    details.append(summary, content);
    container.append(details);
  }

  function entryView(entry) {
    const row = createElement('tr', undefined, 'entry');
    row.id = entry.id;

    const triggerCell = createElement('th', undefined, 'trigger-cell');
    triggerCell.scope = 'row';
    const heading = createElement('h3');
    const primary = primaryCommand(entry);
    if (primary && !entry.doc.trigger_label) {
      const button = triggerButton(primary);
      button.classList.add('primary-command');
      heading.append(button);
    } else {
      heading.textContent = triggerText(entry);
    }
    triggerCell.append(heading);
    if (entry.doc.title) triggerCell.append(createElement('span', entry.doc.title, 'function-name'));

    const argumentCell = createElement('td', undefined, 'arguments-cell');
    argumentCell.append(createElement('code', argumentsText(entry), 'arguments-syntax'));

    const functionCell = createElement('td', undefined, 'function-cell');
    const description = entry.doc.description || plugins.get(entry.plugin)?.description;
    if (description) functionCell.append(createElement('p', description, 'entry-desc'));
    if (entry.doc.audience || entry.restricted) {
      functionCell.append(createElement('span', entry.doc.audience || '权限受限', 'audience'));
    }
    if (entry.doc.arguments || entry.doc.usage || entry.conditions.length
      || entry.permissions.length || entry.triggers.some(trigger => trigger.values.length > 1)) {
      addRuleDetails(functionCell, entry);
    }

    row.append(triggerCell, argumentCell, functionCell);
    return row;
  }

  function memeGroupView(group) {
    const row = createElement('tr', undefined, 'entry meme-group');
    const triggerCell = createElement('th', undefined, 'trigger-cell');
    triggerCell.scope = 'row';
    triggerCell.append(createElement('h3', '表情包触发项'));
    triggerCell.append(createElement('span', `${group.members.length} 种`, 'group-count'));

    const argumentCell = createElement('td', undefined, 'arguments-cell');
    argumentCell.append(createElement('code', '图片、文字、@用户及模板选项', 'arguments-syntax'));

    const functionCell = createElement('td', undefined, 'function-cell');
    functionCell.append(createElement('p', '按关键词或文字格式调用对应模板生成表情包。'));
    const details = createElement('details', undefined, 'meme-details');
    details.append(createElement('summary', `展开 ${group.members.length} 个触发项`));

    const list = createElement('ul', undefined, 'meme-list');
    for (const entry of group.members) {
      const item = createElement('li');
      item.append(createElement('code', triggerText(entry), 'meme-trigger'));
      item.append(createElement('code', argumentsText(entry), 'meme-arguments'));
      item.append(createElement('span', entry.doc.description || '制作对应模板的表情包。'));
      list.append(item);
    }
    details.append(list);
    functionCell.append(details);
    row.append(triggerCell, argumentCell, functionCell);
    return row;
  }

  function groupMemeEntries(filtered) {
    const displayEntries = [];
    let memeGroup;
    for (const entry of filtered) {
      if (!entry.doc.meme_template) {
        displayEntries.push(entry);
        continue;
      }
      if (!memeGroup) {
        memeGroup = { plugin: memePlugin, isMemeGroup: true, members: [] };
        displayEntries.push(memeGroup);
      }
      memeGroup.members.push(entry);
    }
    return displayEntries;
  }

  function openIndex(open) {
    getElement('index-panel').hidden = !open;
    getElement('index-toggle').setAttribute('aria-expanded', String(open));
  }

  function closeIndex() {
    indexPinned = false;
    openIndex(false);
  }

  function scrollToSection(node) {
    if (!node) return;
    const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
    node.scrollIntoView({ behavior, block: 'start' });
    node.tabIndex = -1;
    node.focus({ preventScroll: true });
  }

  function renderIndex(displayEntries) {
    const groups = new Map();
    displayEntries.forEach((entry, index) => {
      const group = groups.get(entry.plugin) || { count: 0, end: 0 };
      group.count += entry.isMemeGroup ? entry.members.length : 1;
      group.end = index;
      groups.set(entry.plugin, group);
    });

    const buttons = [...groups].map(([pluginId, group]) => {
      const button = createElement('button');
      button.type = 'button';
      button.dataset.indexPlugin = pluginId;
      button.append(
        createElement('span', plugins.get(pluginId)?.name || pluginId),
        createElement('span', String(group.count), 'index-count'),
      );
      button.addEventListener('click', () => {
        visibleLimit = Math.max(visibleLimit, group.end + 1);
        render();
        closeIndex();
        scrollToSection(getElement(`group-${pluginId}`));
      });
      return button;
    });
    const emptyIndex = createElement('p', '当前筛选没有匹配的插件。');
    getElement('index-links').replaceChildren(...(buttons.length ? buttons : [emptyIndex]));
  }

  function render() {
    const words = getElement('search').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const filtered = entries.filter(entry => (
      (activeCategory === '全部功能' || categoryOf(entry) === activeCategory)
      && (!getElement('plugin').value || entry.plugin === getElement('plugin').value)
      && (!getElement('kind').value || entry.triggers.some(trigger => trigger.kind === getElement('kind').value))
      && (!getElement('documented').checked || entry.doc.description || entry.doc.usage)
      && words.every(word => entry.search.includes(word))
    ));
    const displayEntries = groupMemeEntries(filtered);
    const rows = [];
    let previousPlugin;

    for (const entry of displayEntries.slice(0, visibleLimit)) {
      if (entry.plugin !== previousPlugin) {
        const group = createElement('tr', undefined, 'plugin-group');
        group.id = `group-${entry.plugin}`;
        const heading = createElement('th');
        heading.colSpan = 3;
        heading.scope = 'colgroup';
        heading.append(createElement('span', plugins.get(entry.plugin)?.name || entry.plugin));
        const total = filtered.filter(item => item.plugin === entry.plugin).length;
        heading.append(createElement('span', `${total} 个触发项`, 'group-count'));
        group.append(heading);
        rows.push(group);
        previousPlugin = entry.plugin;
      }
      rows.push(entry.isMemeGroup ? memeGroupView(entry) : entryView(entry));
    }

    getElement('results').replaceChildren(...rows);
    getElement('table-scroll').hidden = displayEntries.length === 0;
    renderIndex(displayEntries);
    getElement('results-title').textContent = activeCategory;
    getElement('count').textContent = `${filtered.length} 个触发项 · ${new Set(filtered.map(entry => entry.plugin)).size} 个插件`;
    getElement('empty').hidden = filtered.length !== 0;
    getElement('more').hidden = displayEntries.length <= visibleLimit;
    getElement('more').textContent = `显示更多（还剩 ${displayEntries.length - visibleLimit} 项）`;
    document.querySelectorAll('[data-category]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.category === activeCategory));
    });
  }

  function reset() {
    activeCategory = '全部功能';
    getElement('search').value = '';
    getElement('plugin').value = '';
    getElement('kind').value = '';
    getElement('documented').checked = false;
    visibleLimit = 40;
    render();
  }

  getElement('search').addEventListener('input', () => {
    visibleLimit = 40;
    render();
  });
  ['plugin', 'kind', 'documented'].forEach(id => {
    getElement(id).addEventListener('change', () => {
      visibleLimit = 40;
      render();
    });
  });
  document.querySelectorAll('[data-query]').forEach(button => {
    button.addEventListener('click', () => {
      getElement('search').value = button.dataset.query;
      visibleLimit = 40;
      render();
      getElement('search').focus();
    });
  });

  getElement('reset').addEventListener('click', reset);
  getElement('empty-reset').addEventListener('click', reset);
  getElement('more').addEventListener('click', () => {
    visibleLimit += 40;
    render();
  });
  getElement('index-toggle').addEventListener('click', () => {
    indexPinned = !indexPinned;
    openIndex(indexPinned);
  });
  getElement('floating-index').addEventListener('pointerenter', event => {
    if (event.pointerType === 'mouse') openIndex(true);
  });
  getElement('floating-index').addEventListener('pointerleave', () => {
    if (!indexPinned && !getElement('index-panel').contains(document.activeElement)) openIndex(false);
  });
  getElement('floating-index').addEventListener('focusout', event => {
    if (!indexPinned && !getElement('floating-index').contains(event.relatedTarget)) openIndex(false);
  });
  getElement('index-close').addEventListener('click', () => {
    closeIndex();
    getElement('index-toggle').focus();
  });
  getElement('index-top').addEventListener('click', () => {
    closeIndex();
    scrollToSection(getElement('search'));
  });
  document.addEventListener('pointerdown', event => {
    if (!getElement('floating-index').contains(event.target)) closeIndex();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !getElement('index-panel').hidden) {
      closeIndex();
      getElement('index-toggle').focus();
    }
    if (event.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      event.preventDefault();
      getElement('search').focus();
    }
  });

  render();
})();
