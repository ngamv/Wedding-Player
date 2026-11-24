async function afficherAgenda(container) {
  const view = document.createElement('section');
  view.className = 'panel agenda-view';
  view.innerHTML = [
    '<h2>Calendrier des activités</h2><p role="status" data-status>Chargement…</p>',
    '<form class="filters workflow-form" data-agenda-form hidden>',
    '<label>À partir du<input name="start" type="date"></label>',
    '<label>Horizon<select name="days"><option value="7">7 jours</option>',
    '<option value="30" selected>30 jours</option><option value="90">90 jours</option></select></label>',
    '<label>Type d’événement<select name="kind"><option value="all">Tous</option>',
    '<option value="appointment">Rendez-vous</option><option value="wedding">Mariages</option>',
    '<option value="project">Projets</option><option value="task">Tâches</option></select></label>',
    '<button>Afficher</button><button type="button" data-today>Aujourd’hui</button></form>',
    '<div data-agenda-content></div>',
  ].join('');
  container.replaceChildren(view);
  const status = view.querySelector('[data-status]');
  const form = view.querySelector('[data-agenda-form]');
  const content = view.querySelector('[data-agenda-content]');
  const date = new Intl.DateTimeFormat('fr-FR', {dateStyle:'full',timeZone:'UTC'});
  const labels = {appointment:'Rendez-vous', wedding:'Mariage', project:'Projet', task:'Tâche'};
  let authorization;
  let sequence = 0;

  function el(tag, text) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    return item;
  }
  async function refresh() {
    const revision = ++sequence;
    const fields = Object.fromEntries([...new FormData(form)].filter(([, value]) => value));
    const response = await fetch('/api/agenda?' + new URLSearchParams(fields), {
      cache:'no-store', headers:authorization ? {Authorization:authorization} : {},
      signal:AbortSignal.timeout(10000),
    });
    if (revision !== sequence) return;
    const data = await response.json();
    if (revision !== sequence) return;
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Vérifiez les filtres saisis.');
      error.status = response.status;
      throw error;
    }
    form.hidden = false;
    form.elements.start.value = data.start;
    status.textContent = 'Du ' + data.start + ' au ' + data.end + ' · ' + data.count + ' événement(s)';
    content.replaceChildren();
    if (!data.items.length) {
      content.append(el('p', 'Aucun événement pour cette période et ces filtres.'));
      return;
    }
    let day;
    let current;
    for (const row of data.items) {
      if (row.date !== day) {
        day = row.date;
        current = el('section');
        current.className = 'agenda-day';
        current.append(el('h3', date.format(new Date(day + 'T00:00:00Z'))));
        content.append(current);
      }
      const item = el('article');
      item.className = 'item';
      const caption = el('div');
      caption.append(el('strong', row.title), el('p', [labels[row.kind],row.detail].filter(Boolean).join(' · ')));
      const link = el('a', row.kind === 'appointment' ? 'Voir les imports' : 'Ouvrir');
      link.href = row.link;
      link.setAttribute('aria-label', link.textContent + ' · ' + row.title);
      item.append(caption, link);
      current.append(item);
    }
    if (data.items.length < data.count) content.append(el('p', '500 événements affichés. Réduisez la période pour affiner.'));
  }

  const update = () => refresh().catch(error => { status.textContent = error.message; });
  form.onsubmit = event => { event.preventDefault(); update(); };
  view.querySelector('[data-today]').onclick = () => { form.elements.start.value = ''; update(); };
  try { await refresh(); }
  catch (error) {
    if (error.status !== 401) { status.textContent = error.message; return; }
    const login = el('form');
    login.className = 'workflow-form';
    login.innerHTML = '<label>Compte administrateur<input name="user" required autocomplete="username"></label>' +
      '<label>Mot de passe<input name="password" required type="password" autocomplete="current-password"></label><button>Se connecter</button>';
    status.textContent = 'Connectez-vous pour consulter l’agenda.';
    view.insertBefore(login, form);
    login.onsubmit = async event => {
      event.preventDefault();
      const submit = login.querySelector('button');
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(login.elements.user.value + ':' + login.elements.password.value);
        await refresh();
        login.remove();
      } catch (failure) {
        authorization = undefined;
        status.textContent = failure.message;
      } finally { submit.disabled = false; }
    };
  }
}
