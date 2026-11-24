async function afficherSupport(container, preferred) {
  const work = document.createElement('div');
  work.innerHTML = [
    '<p role="status"></p><div class="site-grid" hidden data-support><section class="panel">',
    '<h2>File de tickets</h2><label>Afficher<select data-filter>',
    '<option value="active">À traiter</option><option value="urgent">Urgents</option>',
    '<option value="closed">Clôturés</option><option value="all">Tous</option></select></label>',
    '<div data-list></div><div class="filters" data-pages></div>',
    '<details><summary>Nouveau ticket</summary><form class="workflow-form" data-create>',
    '<label>Objet<input name="title" maxlength="240" required></label>',
    '<label>Priorité<select name="status"><option value="open">Ouvert</option><option value="urgent">Urgent</option></select></label>',
    '<label>Contexte<textarea name="note" maxlength="2000" required></textarea></label>',
    '<button>Créer le ticket</button></form></details><p><a href="#ceo?imports=1">Importer des tickets CSV</a></p></section>',
    '<section class="panel" data-detail><h2>Détail du ticket</h2><p>Sélectionnez un ticket.</p></section></div>',
  ].join('');
  container.replaceChildren(work);
  const status = work.querySelector('[role=status]');
  const layout = work.querySelector('[data-support]');
  const filter = work.querySelector('[data-filter]');
  const list = work.querySelector('[data-list]');
  const pages = work.querySelector('[data-pages]');
  const detail = work.querySelector('[data-detail]');
  const create = work.querySelector('[data-create]');
  const states = {open:'Ouvert', urgent:'Urgent', closed:'Clôturé'};
  const dates = new Intl.DateTimeFormat('fr-FR', {dateStyle:'short', timeStyle:'short', timeZone:'Europe/Paris'});
  const limit = 30;
  let offset = 0;
  let authorization;
  let listRevision = 0;
  let detailRevision = 0;

  function node(tag, text) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    return result;
  }
  function button(text, action) {
    const control = node('button', text);
    control.type = 'button';
    control.onclick = action;
    return control;
  }
  async function request(path = '', method = 'GET', payload) {
    const headers = authorization ? {Authorization:authorization} : {};
    if (payload) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/support' + path, {
      method, cache:'no-store', headers, body:payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Vérifiez les champs saisis.');
      error.status = response.status;
      throw error;
    }
    return data;
  }
  const ticketPath = id => '/ticket?' + new URLSearchParams({id});

  async function load() {
    const revision = ++listRevision;
    const data = await request('?' + new URLSearchParams({status:filter.value,limit,offset}));
    if (revision !== listRevision) return;
    list.replaceChildren();
    pages.replaceChildren();
    if (!data.items.length) list.append(node('p', 'Aucun ticket dans cette vue.'));
    for (const ticket of data.items) {
      const row = node('div');
      row.className = 'item';
      row.append(button(ticket.title, () => open(ticket.id)), node('span', states[ticket.status]));
      list.append(row);
    }
    if (offset || data.has_more) {
      const back = button('Précédent', () => { offset -= limit; refresh(); });
      const next = button('Suivant', () => { offset += limit; refresh(); });
      back.disabled = !offset;
      next.disabled = !data.has_more;
      pages.append(back, next);
    }
  }
  const refresh = () => load().catch(error => { status.textContent = error.message; });
  filter.onchange = () => { offset = 0; refresh(); };

  function show(ticket) {
    detail.replaceChildren(node('h2', ticket.title), node('p', [ticket.day, states[ticket.status]].join(' · ')));
    const form = node('form');
    form.className = 'workflow-form';
    const select = node('select');
    for (const [value, label] of Object.entries(states)) select.add(new Option(label, value));
    select.value = ticket.status;
    const state = node('label', 'Statut du ticket');
    state.append(select);
    const note = node('textarea');
    Object.assign(note, {required:true, maxLength:2000});
    const action = node('label', 'Action réalisée ou prochaine étape');
    action.append(note);
    const submit = node('button', 'Enregistrer le suivi');
    form.append(state, action, submit);
    detail.append(form, node('h3', 'Historique'));
    if (!ticket.history.length) detail.append(node('p', 'Aucune action enregistrée.'));
    for (const entry of ticket.history) {
      const row = node('article');
      row.className = 'support-event';
      row.append(node('p', [dates.format(new Date(entry.happened_at.replace(' ', 'T') + 'Z')),
        entry.actor, states[entry.status]].join(' · ')), node('p', entry.note));
      detail.append(row);
    }
    form.onsubmit = async event => {
      event.preventDefault();
      const revision = detailRevision;
      submit.disabled = true;
      try {
        const updated = await request(ticketPath(ticket.id), 'PATCH', {status:select.value, note:note.value});
        if (revision === detailRevision) show(updated);
        status.textContent = 'Suivi enregistré.';
        await refresh();
      } catch (error) { status.textContent = error.message; }
      finally { submit.disabled = false; }
    };
  }
  async function open(id) {
    const revision = ++detailRevision;
    try {
      const ticket = await request(ticketPath(id));
      if (revision === detailRevision) show(ticket);
    } catch (error) {
      if (revision === detailRevision) status.textContent = error.message;
    }
  }

  create.onsubmit = async event => {
    event.preventDefault();
    const submit = create.querySelector('button');
    submit.disabled = true;
    try {
      const ticket = await request('', 'POST', Object.fromEntries(new FormData(create)));
      create.reset();
      create.closest('details').open = false;
      filter.value = 'active';
      offset = 0;
      await refresh();
      await open(ticket.id);
      status.textContent = 'Ticket créé.';
    } catch (error) { status.textContent = error.message; }
    finally { submit.disabled = false; }
  };
  async function start() {
    await load();
    layout.hidden = false;
    status.textContent = '';
    if (preferred) await open(preferred);
  }

  try { await start(); }
  catch (error) {
    if (error.status !== 401) { status.textContent = error.message; return; }
    const login = node('form');
    login.className = 'panel workflow-form';
    login.innerHTML = '<h2>Connexion au support</h2><label>Compte administrateur<input name="user" required autocomplete="username"></label>' +
      '<label>Mot de passe<input name="password" type="password" required autocomplete="current-password"></label><button>Se connecter</button>';
    work.insertBefore(login, layout);
    login.onsubmit = async event => {
      event.preventDefault();
      const submit = login.querySelector('button');
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(login.elements.user.value + ':' + login.elements.password.value);
        await start();
        login.remove();
      } catch (failure) {
        authorization = undefined;
        status.textContent = failure.message;
      } finally { submit.disabled = false; }
    };
  }
}
