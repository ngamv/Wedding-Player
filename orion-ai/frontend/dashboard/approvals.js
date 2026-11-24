async function afficherValidations(container) {
  const view = document.createElement('section');
  view.className = 'panel approvals-view';
  view.innerHTML = '<h2>Propositions à valider</h2><p role="status">Chargement…</p>' +
    '<div class="filters" data-filters hidden><label>Étape<select data-stage>' +
    '<option value="pending">À valider</option><option value="followup">À suivre après validation</option><option value="history">Historique</option>' +
    '</select></label><label>Activité<select data-source>' +
    '<option value="all">Toutes</option><option value="wedding">Wedding</option>' +
    '<option value="site">Site web</option></select></label><button type="button">Actualiser</button></div><div data-items></div>';
  container.replaceChildren(view);
  const status = view.querySelector('[role=status]');
  const controls = view.querySelector('[data-filters]');
  const source = controls.querySelector('[data-source]');
  const stage = controls.querySelector('[data-stage]');
  const refresh = controls.querySelector('button');
  const items = view.querySelector('[data-items]');
  const categories = {wedding:'Wedding', site:'Site web'};
  let authorization;
  let current = [];
  let revision = 0;
  const labels = {draft:'À valider', approved:'Validée', sending:'Envoi en cours',
    sent:'Résultat à consigner', unknown:'Envoi à vérifier',
    dismissed:'Relance écartée', rejected:'Plan écarté', recorded:'Résultat consigné', verified:'Contrôle consigné'};
  const titles = {pending:'Propositions à valider', followup:'Actions à suivre', history:'Historique des décisions'};
  const captions = {pending:' proposition(s) en attente', followup:' action(s) à suivre', history:' décision(s) ou résultat(s)'};
  const historyLabels = {...labels, sent:'Envoi accepté par SMTP', unknown:'Envoi incertain'};

  function node(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }
  function render() {
    view.querySelector('h2').textContent = titles[stage.value];
    const filtered = current.filter(row => source.value === 'all' || source.value === row.source);
    status.textContent = filtered.length + captions[stage.value];
    const states = stage.value === 'history' ? historyLabels : labels;
    items.replaceChildren();
    if (!filtered.length) items.append(node('p','Aucun élément pour cette sélection.'));
    for (const row of filtered) {
      const item = document.createElement('article');
      item.className = 'item';
      const section = document.createElement('div');
      section.append(node('strong', row.title), node('p', [
        categories[row.source], row.dossier, row.date || 'Date indisponible', states[row.state], row.urgent ? 'Échéance atteinte' : '',
      ].filter(Boolean).join(' · ')));
      const action = node('a','Examiner');
      action.href = row.href;
      action.setAttribute('aria-label', 'Examiner ' + row.title + ' · ' + row.dossier);
      item.append(section, action);
      items.append(item);
    }
  }
  async function load() {
    const number = ++revision;
    refresh.disabled = true;
    try {
      const response = await fetch('/api/approvals?' + new URLSearchParams({stage:stage.value}), {cache:'no-store',
        headers:authorization ? {Authorization:authorization} : {},
        signal:AbortSignal.timeout(15000)});
      if (!response.ok) {
        const error = new Error(response.status === 403 ? 'Validations réservées à l’administrateur.'
          : 'Impossible de charger les validations.');
        error.status = response.status;
        throw error;
      }
      const data = await response.json();
      if (number !== revision) return;
      current = data.items;
      controls.hidden = false;
      render();
    } finally {
      if (number === revision) refresh.disabled = false;
    }
  }
  source.onchange = render;
  stage.onchange = () => { current = []; items.replaceChildren(); status.textContent = 'Chargement…'; refresh.onclick(); };
  refresh.onclick = () => load().catch(error => { status.textContent = error.message; });

  try { await load(); }
  catch (error) {
    if (error.status !== 401) { status.textContent = error.message; return; }
    status.textContent = 'Connectez-vous avec un compte administrateur.';
    const form = document.createElement('form');
    form.className = 'workflow-form';
    form.innerHTML = '<label>Compte administrateur<input name="user" required autocomplete="username"></label>' +
      '<label>Mot de passe<input name="password" type="password" required autocomplete="current-password"></label><button>Se connecter</button>';
    view.insertBefore(form, controls);
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = form.querySelector('button');
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(form.elements.user.value + ':' + form.elements.password.value);
        await load();
        form.remove();
      } catch (failure) {
        authorization = undefined;
        status.textContent = failure.message;
      } finally { submit.disabled = false; }
    };
  }
}
