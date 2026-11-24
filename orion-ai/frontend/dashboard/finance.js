async function afficherFinances(container) {
  const view = document.createElement('section');
  view.className = 'panel finance-live';
  view.innerHTML = [
    '<h2>Encaissements</h2><p role="status"></p>',
    '<div data-rows hidden><div class="filters">',
    '<label>Période<select data-days><option value="30">30 jours</option><option value="60">60 jours</option><option value="90">90 jours</option></select></label>',
    '<label>Statut des écritures<select data-state><option value="all">Tous</option><option value="paid">Encaissés</option>',
    '<option value="pending">En attente</option><option value="cancelled">Annulés</option></select></label>',
    '<a href="#ceo?imports=1">Importer des encaissements</a></div>',
    '<dl class="finance-metrics"></dl><div data-table></div><div class="filters" data-pagination></div></div>',
  ].join('');
  container.replaceChildren(view);
  const status = view.querySelector('[role=status]');
  const deck = view.querySelector('[data-rows]');
  const days = deck.querySelector('[data-days]');
  const state = deck.querySelector('[data-state]');
  const metrics = deck.querySelector('dl');
  const list = deck.querySelector('[data-table]');
  const pages = deck.querySelector('[data-pagination]');
  const labels = {paid:'Encaissé', pending:'En attente', cancelled:'Annulé'};
  const money = new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR'});
  const dates = new Intl.DateTimeFormat('fr-FR', {dateStyle:'short', timeStyle:'short', timeZone:'Europe/Paris'});
  const limit = 30;
  let authorization;
  let offset = 0;
  let revision = 0;

  function node(tag, value) {
    const element = document.createElement(tag);
    if (value !== undefined) element.textContent = value;
    return element;
  }
  async function refresh() {
    const sequence = ++revision;
    const query = new URLSearchParams({days:days.value, status:state.value, limit, offset});
    const response = await fetch('/api/finance/receipts?' + query, {
      cache:'no-store', headers:authorization ? {Authorization:authorization} : {},
    });
    if (sequence !== revision) return;
    if (!response.ok) {
      const error = new Error('Le relevé financier est indisponible ou nécessite un compte administrateur.');
      error.status = response.status;
      throw error;
    }
    const data = await response.json();
    if (sequence !== revision) return;
    status.textContent = 'Du ' + data.start + ' au ' + data.end + ' · ' + (
      data.source ? (data.source.state === 'error' ? 'Dernier import en échec : ' + data.source.detail :
        'Dernier import réussi') + ' · ' + dates.format(new Date(data.source.happened_at.replace(' ', 'T') + 'Z')) :
        'Aucun import d’encaissements');
    const cards = [
      ['Encaissé sur la période', money.format(data.metrics.paid / 100)],
      ['En attente sur la période', money.format(data.metrics.pending / 100)],
      ['Encaissé sur la période précédente', money.format(data.metrics.previous_paid / 100)],
      ['Écritures sur la période', data.metrics.records],
    ];
    metrics.replaceChildren();
    if (data.source?.last_success) {
      for (const [title, value] of cards) {
        const card = node('div');
        card.append(node('dt', title), node('dd', value));
        metrics.append(card);
      }
    }
    list.innerHTML = data.items.length ? table(data.items.map(item => [
      item.day, item.title, labels[item.status], money.format(item.cents / 100),
    ]), ['Date', 'Écriture', 'Statut', 'Montant']) : '<p>Aucune écriture pour cette sélection.</p>';
    pages.replaceChildren();
    if (offset || data.has_more) {
      for (const [caption, step, enabled] of [['Précédent', -limit, offset > 0], ['Suivant', limit, data.has_more]]) {
        const button = node('button', caption);
        button.type = 'button';
        button.disabled = !enabled;
        button.onclick = () => { offset += step; update(); };
        pages.append(button);
      }
    }
    deck.hidden = false;
  }
  const update = () => refresh().catch(error => { status.textContent = error.message; });
  for (const control of [days,state]) control.onchange = () => { offset = 0; update(); };
  try { await refresh(); }
  catch (error) {
    if (error.status !== 401) { status.textContent = error.message; return; }
    const form = node('form');
    form.className = 'workflow-form';
    form.innerHTML = '<label>Compte administrateur<input name="user" autocomplete="username" required></label>' +
      '<label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label><button>Se connecter</button>';
    status.textContent = 'Connectez-vous pour voir les encaissements.';
    view.append(form);
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = form.querySelector('button');
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(form.elements.user.value + ':' + form.elements.password.value);
        await refresh();
        form.remove();
      } catch (failure) {
        authorization = undefined;
        status.textContent = failure.message;
      } finally { submit.disabled = false; }
    };
  }
}
