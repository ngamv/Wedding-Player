async function afficherVueEnsemble(container, onExport) {
  const view = document.createElement('div');
  view.className = 'overview-live';
  view.innerHTML = [
    '<section class="panel overview-command"><div><h2>Situation de vos activités</h2>',
    '<p role="status" data-status>Chargement des données…</p></div>',
    '<div class="filters"><label>Période des encaissements<select data-days>',
    '<option value="30">30 jours</option><option value="60">60 jours</option><option value="90">90 jours</option>',
    '</select></label><button type="button" data-refresh>Actualiser</button></div></section>',
    '<div class="overview-grid" data-overview hidden></div>',
    '<section class="panel" data-priorities hidden><h2>À traiter en priorité</h2><div data-brief></div>',
    '<a href="#ceo">Ouvrir le Brief du CEO</a></section>',
  ].join('');
  container.replaceChildren(view);
  const status = view.querySelector('[data-status]');
  const days = view.querySelector('[data-days]');
  const refresh = view.querySelector('[data-refresh]');
  const grid = view.querySelector('[data-overview]');
  const priorities = view.querySelector('[data-priorities]');
  const briefBody = view.querySelector('[data-brief]');
  const euros = new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR'});
  const localDate = new Intl.DateTimeFormat('fr-FR', {dateStyle:'short',timeStyle:'short',timeZone:'Europe/Paris'});
  let authorization;
  let revision = 0;

  function node(tag, text) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function link(text, href) {
    const element = node('a', text);
    element.href = href;
    return element;
  }

  function render(data) {
    const source = data.receipts_source;
    const posted = source?.last_success;
    const receiptNote = source?.state === 'error' ? 'Dernier import en échec' :
      posted ? 'Importé le ' + localDate.format(new Date(posted.replace(' ', 'T') + 'Z')) : 'Premier import en attente';
    const cards = [
      ['Encaissements', posted ? euros.format(data.receipts / 100) : '—', receiptNote, '#finances'],
      ['Tickets ouverts', data.tickets.active, data.tickets.urgent + ' urgent(s)', '#support'],
      ['Projets actifs', data.projects, data.blocked_projects + ' bloqué(s)', '#projets'],
      ['Dossiers Wedding', data.weddings, 'Dossiers enregistrés', '#wedding'],
      ['Sites enregistrés', data.sites, 'Registre local', '#site'],
    ];
    grid.replaceChildren();
    for (const [label,value,note,href] of cards) {
      const card = link('', href);
      card.className = 'overview-card panel';
      card.append(node('span',label), node('strong',value), node('small',note));
      grid.append(card);
    }
    grid.hidden = priorities.hidden = false;
    briefBody.replaceChildren();
    const brief = data.brief;
    if (brief) {
      let info = 'Brief du ' + brief.date + ' · ' + brief.count + ' point(s) à traiter · ' + brief.urgent + ' urgent(s)';
      if (brief.date !== data.date) info += ' · Brief du jour en attente';
      briefBody.append(node('p',info));
      if (brief.file_errors || Object.values(brief.sources).includes('error')) {
        briefBody.append(node('p','Des sources demandent une vérification dans le brief.'));
      }
      if (!brief.items.length) briefBody.append(node('p','Aucune priorité dans ce brief.'));
      for (const item of brief.items) {
        const row = node('div');
        row.className = 'item overview-priority';
        const text = node('div');
        text.append(node('strong',item.title), node('p', [item.source,item.due,item.detail].filter(Boolean).join(' · ')));
        const open = link('Ouvrir',item.link);
        open.setAttribute('aria-label','Ouvrir ' + item.title);
        row.append(text,open);
        briefBody.append(row);
      }
    } else {
      briefBody.append(node('p','Aucun brief enregistré. Générez votre premier brief pour voir les priorités ici.'));
    }
    status.textContent = 'Encaissements du ' + data.period.start + ' au ' + data.period.end;
    onExport([['Indicateur','Valeur','Source'], ...cards.map(([label,value,note]) => [label,value,note])]);
  }

  async function load() {
    const number = ++revision;
    refresh.disabled = true;
    try {
      const response = await fetch('/api/dashboard/overview?' + new URLSearchParams({days:days.value}), {
        cache:'no-store', headers:authorization ? {Authorization:authorization} : {},
        signal:AbortSignal.timeout(10000),
      });
      if (number !== revision || !view.isConnected) return;
      if (!response.ok) {
        const error = new Error(response.status === 403 ? 'Indicateurs réservés à l’administrateur.' :
          'Impossible de charger la vue d’ensemble.');
        error.status = response.status;
        throw error;
      }
      const data = await response.json();
      if (number !== revision || !view.isConnected) return;
      render(data);
    } finally {
      if (number === revision) refresh.disabled = false;
    }
  }

  function showLogin() {
    status.textContent = 'Connectez-vous pour consulter les indicateurs.';
    const form = node('form');
    form.className = 'panel workflow-form';
    form.innerHTML = '<h2>Connexion</h2><label>Compte administrateur<input name="user" autocomplete="username" required></label>' +
      '<label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label><button>Se connecter</button>';
    view.append(form);
    days.disabled = refresh.disabled = true;
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = form.querySelector('button');
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(form.elements.user.value + ':' + form.elements.password.value);
        await load();
        days.disabled = false;
        form.remove();
      } catch (error) {
        authorization = undefined;
        status.textContent = error.status === 401 ? 'Identifiants incorrects.' : error.message;
        refresh.disabled = true;
      } finally { submit.disabled = false; }
    };
  }
  const update = () => load().catch(error => {
    if (error.status === 401 && !authorization) showLogin();
    else status.textContent = error.message;
  });
  days.onchange = refresh.onclick = update;
  await update();
}
