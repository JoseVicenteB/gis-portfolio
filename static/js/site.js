(() => {
  const header = document.querySelector('[data-header]');
  const menuButton = document.querySelector('[data-menu-toggle]');
  const navigation = document.querySelector('[data-nav]');

  const closeMenu = () => {
    if (!menuButton || !navigation) return;
    menuButton.setAttribute('aria-expanded', 'false');
    navigation.classList.remove('is-open');
  };

  if (menuButton && navigation) {
    menuButton.addEventListener('click', () => {
      const open = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!open));
      navigation.classList.toggle('is-open', !open);
    });
    navigation.addEventListener('click', event => {
      if (event.target.closest('a')) closeMenu();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') closeMenu();
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth > 800) closeMenu();
    });
  }

  const updateHeader = () => header?.classList.toggle('is-scrolled', window.scrollY > 12);
  updateHeader();
  window.addEventListener('scroll', updateHeader, { passive: true });

  document.querySelectorAll('[data-tabs]').forEach(group => {
    const tabs = Array.from(group.querySelectorAll('[role="tab"]'));
    const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
    if (!tabs.length || panels.some(panel => !panel)) return;

    const activate = (tab, options = {}) => {
      tabs.forEach((candidate, index) => {
        const selected = candidate === tab;
        candidate.setAttribute('aria-selected', String(selected));
        candidate.tabIndex = selected ? 0 : -1;
        panels[index].hidden = !selected;
      });
      if (options.focus) tab.focus();
      if (options.hash) history.replaceState(null, '', `#${tab.getAttribute('aria-controls')}`);
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => activate(tab, { hash: true }));
      tab.addEventListener('keydown', event => {
        let nextIndex;
        if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
        if (event.key === 'Home') nextIndex = 0;
        if (event.key === 'End') nextIndex = tabs.length - 1;
        if (nextIndex !== undefined) {
          event.preventDefault();
          activate(tabs[nextIndex], { focus: true, hash: true });
        }
      });
    });

    const activateHash = () => {
      const matchingTab = tabs.find(tab => `#${tab.getAttribute('aria-controls')}` === window.location.hash);
      if (matchingTab) activate(matchingTab);
    };
    activateHash();
    const selected = tabs.find(tab => tab.getAttribute('aria-selected') === 'true') || tabs[0];
    activate(selected);
    window.addEventListener('hashchange', activateHash);
  });

  const filterGroup = document.querySelector('[data-filters]');
  if (filterGroup) {
    const buttons = Array.from(filterGroup.querySelectorAll('[data-filter]'));
    const cards = Array.from(document.querySelectorAll('[data-project-card]'));
    const count = document.querySelector('[data-filter-count]');
    const empty = document.querySelector('[data-empty-state]');

    buttons.forEach(button => {
      button.addEventListener('click', () => {
        const filter = button.dataset.filter;
        let visible = 0;
        buttons.forEach(candidate => candidate.setAttribute('aria-pressed', String(candidate === button)));
        cards.forEach(card => {
          const matches = filter === 'All' || card.dataset.tags.split('|').includes(filter);
          card.hidden = !matches;
          if (matches) visible += 1;
        });
        if (count) count.textContent = `${visible} project${visible === 1 ? '' : 's'}`;
        if (empty) empty.hidden = visible !== 0;
      });
    });
  }

  const dialog = document.querySelector('[data-map-dialog]');
  if (dialog && typeof dialog.showModal === 'function') {
    const image = dialog.querySelector('[data-dialog-image]');
    const caption = dialog.querySelector('[data-dialog-caption]');
    document.querySelectorAll('[data-map-expand]').forEach(button => {
      button.addEventListener('click', () => {
        image.src = button.dataset.full;
        image.alt = button.dataset.alt;
        caption.textContent = button.dataset.caption;
        dialog.showModal();
      });
    });
    dialog.querySelector('[data-dialog-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
      image.src = '';
      image.alt = '';
    });
  } else {
    document.querySelectorAll('[data-map-expand]').forEach(button => { button.hidden = true; });
  }
})();
