async function afficherRecherche(container, initial) {
  const view = document.createElement('section');
  view.className = 'panel dashboard-search';
  view.innerHTML = [
    '<form class="filters workflow-form"><label>Mot-clé ou référence',
    '<input name="q" type="search" maxlength="150" required></label>',
    '<label>Type de résultat<select name="kind"><option value="all">Tout</option>',
    '<option value="project">Projets</option><option value="task">Tâches</option>',
    '<option value="ticket">Tickets</option><option value="document">Mémoire</option>',
    '<option value="site">Sites</option><option value="wedding">Wedding</option></select></label>',
    '<button type="submit">Rechercher</button></form>',
    '<p role="status"></p><div data-results></div>',
  ].join('');
  container.replaceChildren(view);
  const form = view.querySelector('form');
  const submit = form.querySelector('button');
  const status = view.querySelector('[role=status]');
  const results = view.querySelector('[data-results]');
  const categories = {project:'Projet', task:'Tâche', ticket:'Ticket', document:'Mémoire', site:'Site web', wedding:'Wedding'};
  if (initial) form.elements.q.value = initial;
  let authorization;
  let login;
  let revision = 0;

  function el(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  async function search() {
    const request = ++revision;
    submit.disabled = true;
    status.textContent = 'Recherche…';
    try {
      const params = new URLSearchParams(new FormData(form));
      const response = await fetch('/api/dashboard/search?' + params, {
        cache:'no-store', headers:authorization ? {Authorization:authorization} : {},
        signal:AbortSignal.timeout(10000),
      });
      if (request !== revision) return;
      if (response.status === 401) {
        showLogin();
        return;
      }
      if (!response.ok) throw new Error(response.status === 403 ?
        'La recherche transversale est réservée à l’administrateur.' : 'La recherche est indisponible.');
      const data = await response.json();
      if (request !== revision) return;
      login?.remove();
      login = undefined;
      status.textContent = data.items.length ? data.items.length + ' résultat(s) affiché(s)' : 'Aucun résultat.';
      results.replaceChildren();
      for (const row of data.items) {
        const item = el('article');
        item.className = 'item search-result';
        const text = el('div');
        text.append(el('strong',row.title), el('p', [categories[row.kind],row.context].filter(Boolean).join(' · ')));
        const link = el('a','Ouvrir');
        link.href = row.href;
        link.setAttribute('aria-label', 'Ouvrir ' + row.title);
        item.append(text, link);
        results.append(item);
      }
      if (data.has_more) results.append(el('p','Affinez les mots-clés ou le type pour voir d’autres résultats.'));
    } catch (error) {
      if (request === revision) {
        status.textContent = error.message;
        results.replaceChildren();
      }
    } finally {
      if (request === revision) submit.disabled = false;
    }
  }

  function showLogin() {
    const retry = Boolean(login);
    authorization = undefined;
    status.textContent = retry ? 'Identifiants incorrects.' : 'Connectez-vous pour rechercher dans vos dossiers.';
    results.replaceChildren();
    if (login) return;
    login = el('form');
    login.className = 'workflow-form';
    login.innerHTML = '<label>Compte administrateur<input name="user" autocomplete="username" required></label>' +
      '<label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label><button>Se connecter et rechercher</button>';
    view.insertBefore(login,results);
    login.onsubmit = async event => {
      event.preventDefault();
      const button = login.querySelector('button');
      button.disabled = true;
      try {
        authorization = 'Basic ' + btoa(login.elements.user.value + ':' + login.elements.password.value);
        login.elements.password.value = '';
        await search();
      } catch {
        authorization = undefined;
        status.textContent = 'Identifiants incorrects.';
      } finally { button.disabled = false; }
    };
  }

  form.onsubmit = event => { event.preventDefault(); search(); };
  if (initial) await search();
  else form.elements.q.focus({preventScroll:true});
}
