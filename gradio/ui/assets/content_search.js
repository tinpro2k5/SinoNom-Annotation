() => {
  if (window.__contentSearchInstalled) return;
  window.__contentSearchInstalled = true;
  let matches = [], current = -1, lastText = '', lastQuery = '';
  const editor = () => document.querySelector('#content-text textarea');
  const queryInput = () => document.getElementById('content-search-query');
  const visible = () => document.getElementById('content-editor')?.getClientRects().length > 0;

  const updateCount = () => {
    const count = document.getElementById('content-search-count');
    if (count) count.textContent = matches.length ? `${current + 1}/${matches.length}` : '0/0';
    document.querySelectorAll('[data-content-search]').forEach(button => {
      button.disabled = matches.length === 0;
    });
  };
  const collectMatches = (reset = false) => {
    const text = editor()?.value || '';
    const query = queryInput()?.value || '';
    if (!reset && text === lastText && query === lastQuery) return false;
    lastText = text;
    lastQuery = query;
    matches = [];
    if (query) {
      // Literal Unicode search: regex punctuation in the query is ordinary text.
      const pattern = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'giu');
      for (const match of text.matchAll(pattern)) {
        matches.push([match.index, match.index + match[0].length]);
      }
    }
    current = matches.length ? 0 : -1;
    updateCount();
    return true;
  };
  let observedEditor = null;
  const syncScroll = () => {
    const textarea = editor();
    const text = textarea?.parentElement.querySelector('.content-search-highlight-text');
    if (text) text.style.transform = `translate(${-textarea.scrollLeft}px, ${-textarea.scrollTop}px)`;
  };
  const drawHighlights = () => {
    const textarea = editor();
    if (!textarea) return null;
    const parent = textarea.parentElement;
    parent.querySelector('.content-search-highlights')?.remove();
    if (!matches.length) return null;
    parent.classList.add('content-search-highlight-host');
    const overlay = document.createElement('div');
    overlay.className = 'content-search-highlights';
    overlay.setAttribute('aria-hidden', 'true');
    Object.assign(overlay.style, {
      top: `${textarea.offsetTop + textarea.clientTop}px`,
      left: `${textarea.offsetLeft + textarea.clientLeft}px`,
      width: `${textarea.clientWidth}px`, height: `${textarea.clientHeight}px`,
    });
    // Copy wrapping and font metrics so highlighting follows the editable text.
    const style = getComputedStyle(textarea);
    const mirror = document.createElement('div');
    mirror.className = 'content-search-highlight-text';
    Object.assign(mirror.style, {
      width: `${textarea.clientWidth}px`, height: 'auto', boxSizing: 'border-box',
      border: '0', margin: '0', whiteSpace: 'pre-wrap', overflowWrap: 'break-word',
    });
    for (const property of ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle',
      'lineHeight', 'letterSpacing', 'paddingTop', 'paddingRight', 'paddingBottom',
      'paddingLeft', 'wordBreak', 'overflowWrap', 'tabSize', 'textIndent', 'direction']) {
      mirror.style[property] = style[property];
    }
    let cursor = 0, active = null;
    matches.forEach(([start, end], index) => {
      mirror.appendChild(document.createTextNode(textarea.value.slice(cursor, start)));
      const mark = document.createElement('mark');
      mark.textContent = textarea.value.slice(start, end);
      if (index === current) {
        mark.className = 'current';
        active = mark;
      }
      mirror.appendChild(mark);
      cursor = end;
    });
    mirror.appendChild(document.createTextNode(textarea.value.slice(cursor) + '\n'));
    overlay.appendChild(mirror);
    parent.appendChild(overlay);
    if (observedEditor !== textarea) {
      resizeObserver.disconnect();
      resizeObserver.observe(textarea);
      observedEditor = textarea;
    }
    syncScroll();
    return active;
  };
  const resizeObserver = new ResizeObserver(drawHighlights);
  const revealMatch = (focus) => {
    const textarea = editor();
    if (!textarea || current < 0) return;
    const [start, end] = matches[current];
    if (focus) textarea.focus({preventScroll: true});
    textarea.setSelectionRange(start, end);
    const marker = drawHighlights();
    if (marker) textarea.scrollTop = Math.max(0, marker.offsetTop - textarea.clientHeight / 2);
    syncScroll();
    updateCount();
  };
  const refresh = () => {
    if (collectMatches()) {
      if (matches.length) revealMatch(false); else drawHighlights();
    } else drawHighlights();
  };
  const navigate = (direction, focus = true) => {
    const changed = collectMatches();
    if (!matches.length) return;
    if (!changed) current = (current + direction + matches.length) % matches.length;
    revealMatch(focus);
  };

  document.addEventListener('input', event => {
    if (event.target === queryInput()) refresh();
    else if (event.target === editor()) {
      // Editing must keep the caret where the user is typing.
      collectMatches();
      drawHighlights();
    }
  });
  document.addEventListener('scroll', event => {
    if (event.target === editor()) syncScroll();
  }, true);
  window.addEventListener('content-search-refresh', () => requestAnimationFrame(refresh));
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-content-search]');
    if (!button || !visible()) return;
    event.preventDefault();
    navigate(button.dataset.contentSearch === 'previous' ? -1 : 1);
  });
  document.addEventListener('keydown', event => {
    if (!visible() || event.isComposing) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
      event.preventDefault();
      const textarea = editor();
      const input = queryInput();
      if (!input) return;
      if (document.activeElement === textarea && textarea.selectionStart !== textarea.selectionEnd) {
        input.value = textarea.value.slice(textarea.selectionStart, textarea.selectionEnd);
      }
      input.focus();
      input.select();
      collectMatches(true);
      revealMatch(false);
    } else if ((event.key === 'Enter' && event.target === queryInput())
        || (event.key === 'F3' && (event.target === editor() || event.target === queryInput()))) {
      event.preventDefault();
      navigate(event.shiftKey ? -1 : 1, event.target === editor());
    } else if (event.key === 'Escape' && event.target === queryInput()) {
      event.preventDefault();
      editor()?.focus({preventScroll: true});
    }
  });
  updateCount();
}
