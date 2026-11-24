async function afficherProjets(container, preferred, preferredTask, openPlanning) {
  const view = document.createElement('div');
  view.innerHTML = [
    '<p data-status role="status"></p><div class="wedding-navigation" data-project-nav hidden role="group" aria-label="Espace Projets">',
    '<button type="button" data-view="register" aria-pressed="true">Registre</button>',
    '<button type="button" data-view="planning" aria-pressed="false">Planning des tâches</button></div>',
    '<div class="site-grid" data-projects hidden>',
    '<section class="panel"><h2>Registre des projets</h2>',
    '<div class="filters"><label>Filtrer par statut<select data-filter></select></label>',
    '<button type="button" data-new>Nouveau projet</button></div><div data-list></div></section>',
    '<section class="panel"><h2 data-title>Nouveau projet</h2><form class="workflow-form" data-editor>',
    '<label>Projet<input name="title" maxlength="180" required></label>',
    '<label>Responsable<input name="owner" maxlength="140" required></label>',
    '<div class="filters"><label>Échéance<input name="due" type="date"></label>',
    '<label>Statut du projet<select name="status" required></select></label></div>',
    '<label>Point de suivi ou blocage<textarea name="note" maxlength="2000" rows="4"></textarea></label>',
    '<button>Enregistrer le projet</button></form><section data-tasks hidden></section><section data-memory hidden></section><div data-history></div></section></div>',
    '<section class="panel" data-planning hidden><h2>Planning des tâches</h2>',
    '<div class="filters"><label>Afficher les tâches<select data-mode>',
    '<option value="all">Toutes les tâches ouvertes</option><option value="overdue">En retard</option>',
    '<option value="upcoming">Échéances à sept jours</option><option value="blocked">Bloquées ou en attente</option>',
    '<option value="undated">Sans échéance</option></select></label>',
    '<label>Responsable des tâches<select data-owner><option value="">Tous</option></select></label></div>',
    '<p role="status" data-plan-status></p><div data-agenda></div><div class="filters" data-agenda-pages></div></section>',
  ].join('');
  container.replaceChildren(view);
  const status = view.querySelector('[data-status]');
  const grid = view.querySelector('[data-projects]');
  const navigation = view.querySelector('[data-project-nav]');
  const planning = view.querySelector('[data-planning]');
  const mode = planning.querySelector('[data-mode]');
  const owner = planning.querySelector('[data-owner]');
  const planStatus = planning.querySelector('[data-plan-status]');
  const agenda = planning.querySelector('[data-agenda]');
  const agendaPages = planning.querySelector('[data-agenda-pages]');
  const limit = 40;
  let offset = 0;
  let agendaRevision = 0;
  const filter = view.querySelector('[data-filter]');
  const list = view.querySelector('[data-list]');
  const editor = view.querySelector('[data-editor]');
  const title = view.querySelector('[data-title]');
  const history = view.querySelector('[data-history]');
  const tasks = view.querySelector('[data-tasks]');
  const memory = view.querySelector('[data-memory]');
  const states = {planned:'À lancer', active:'En cours', blocked:'Bloqué', done:'Terminé'};
  const date = new Intl.DateTimeFormat('fr-FR', {dateStyle:'short',timeStyle:'short',timeZone:'Europe/Paris'});
  let selected;
  let authorization;
  let listRevision = 0;
  let detailRevision = 0;
  const el = (tag, value) => {
    const item = document.createElement(tag);
    if (value !== undefined) item.textContent = value;
    return item;
  };

  filter.add(new Option('Tous', 'all'));
  for (const [id, label] of Object.entries(states)) {
    filter.add(new Option(label, id));
    editor.elements.status.add(new Option(label, id));
  }
  editor.elements.status.onchange = () => { editor.elements.note.required = editor.elements.status.value === 'blocked'; };

  async function request(path = '', method = 'GET', payload) {
    const headers = authorization ? {Authorization:authorization} : {};
    if (payload) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/projects' + path, {
      method, headers, cache:'no-store', body:payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === 'string' ? data.detail : 'Vérifiez les champs.');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function show(project, focusedTask) {
    selected = project?.id;
    title.textContent = project ? project.title : 'Nouveau projet';
    editor.reset();
    editor.elements.note.required = project?.status === 'blocked';
    history.replaceChildren();
    tasks.replaceChildren();
    tasks.hidden = memory.hidden = !project;
    memory.replaceChildren();
    if (!project) return;
    showTasks(project);
    if (focusedTask && /^[a-f0-9]{32}$/.test(focusedTask)) {
      const target = tasks.querySelector('[data-task-id="' + focusedTask + '"]');
      if (target) {
        target.open = true;
        target.querySelector('summary').focus({preventScroll:true});
        target.scrollIntoView({block:'nearest'});
      }
    }
    showMemory(project);
    for (const field of ['title','owner','due','status','note']) {
      editor.elements[field].value = project[field] ?? '';
    }
    history.append(el('h3','Historique'));
    for (const entry of project.history) {
      const row = el('article');
      row.className = 'support-event';
      row.append(el('p', [date.format(new Date(entry.happened_at.replace(' ', 'T') + 'Z')),
        entry.actor, states[entry.status]].join(' · ')));
      if (entry.note) row.append(el('p', entry.note));
      history.append(row);
    }
  }

  function taskForm(project, task) {
    const form = document.createElement('form');
    form.className = 'workflow-form';
    form.innerHTML = [
      '<label>Tâche<input name="title" maxlength="180" required></label>',
      '<div class="filters"><label>Responsable de la tâche<input name="owner" maxlength="140" required></label>',
      '<label>Échéance de la tâche<input type="date" name="due"></label></div>',
      '<label>Statut de la tâche<select name="status"></select></label>',
      '<label>Point de suivi de la tâche<textarea name="note" maxlength="2000"></textarea></label>',
      '<button type="submit"></button>',
    ].join('');
    const values = task || {owner:project.owner, status:'planned'};
    for (const [id, label] of Object.entries(states)) form.elements.status.add(new Option(label, id));
    for (const field of ['title','owner','due','status','note']) form.elements[field].value = values[field] ?? '';
    const setRequired = () => { form.elements.note.required = form.elements.status.value === 'blocked'; };
    form.elements.status.onchange = setRequired;
    setRequired();
    const submit = form.querySelector('button');
    const candidates = project.tasks.filter(item => item.id !== task?.id);
    if (candidates.length) {
      const prerequisites = el('details');
      const fieldset = el('fieldset');
      fieldset.append(el('legend', 'Tâches à terminer avant celle-ci'));
      for (const item of candidates) {
        const label = el('label');
        const checkbox = el('input');
        Object.assign(checkbox, {
          type:'checkbox', name:'dependencies', value:item.id,
          checked:task?.dependencies.includes(item.id) || false,
        });
        label.append(checkbox, ' ' + item.title + ' · ' + states[item.status]);
        fieldset.append(label);
      }
      prerequisites.append(el('summary', 'Prérequis'), fieldset);
      form.insertBefore(prerequisites, submit);
    }
    submit.textContent = task ? 'Enregistrer la tâche' : 'Ajouter la tâche';
    form.onsubmit = async event => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const formData = new FormData(form);
        const body = Object.fromEntries(formData);
        body.dependencies = formData.getAll('dependencies');
        body.due ||= null;
        const path = '/' + project.id + '/tasks' + (task ? '/' + task.id : '');
        const updated = await request(path, task ? 'PUT' : 'POST', body);
        if (selected === project.id) showTasks(updated);
        status.textContent = 'Tâche enregistrée.';
      } catch (error) { status.textContent = error.message; }
      finally { submit.disabled = false; }
    };
    return form;
  }

  function showTasks(project) {
    const done = project.tasks.filter(task => task.status === 'done').length;
    tasks.replaceChildren(el('h3', 'Tâches du projet'));
    if (project.tasks.length) {
      const progress = el('progress');
      progress.max = project.tasks.length;
      progress.value = done;
      progress.setAttribute('aria-label', 'Avancement des tâches');
      tasks.append(el('p', done + ' / ' + project.tasks.length + ' terminée(s)'), progress);
    } else {
      tasks.append(el('p', 'Aucune tâche enregistrée.'));
    }
    const names = new Map(project.tasks.map(task => [task.id, task.title]));
    for (const task of project.tasks) {
      const waiting = task.waiting_for.map(id => names.get(id));
      const details = el('details');
      details.dataset.taskId = task.id;
      const state = waiting.length ? states[task.status] + ' · En attente' : states[task.status];
      details.append(el('summary', task.title + ' · ' + state),
        el('p', [task.owner, task.due].filter(Boolean).join(' · ')));
      if (waiting.length) details.append(el('p', 'À terminer avant cette tâche : ' + waiting.join(', ')));
      details.append(taskForm(project, task));
      tasks.append(details);
    }
    const add = el('details');
    add.append(el('summary', 'Nouvelle tâche'), taskForm(project));
    tasks.append(add);
  }

  async function showMemory(project) {
    const section = el('div');
    const browse = el('a', 'Ouvrir la mémoire de ce projet');
    browse.href = '#memoire?projet=' + encodeURIComponent(project.id);
    const content = el('div');
    content.setAttribute('aria-live', 'polite');
    content.textContent = 'Chargement des sources…';
    section.append(el('h3','Mémoire du projet'), browse, content);
    memory.replaceChildren(section);
    try {
      const data = await request('/' + encodeURIComponent(project.id) + '/memory');
      if (!section.isConnected) return;
      content.replaceChildren();
      if (!data.items.length) content.append(el('p','Aucune source rattachée à ce projet.'));
      const kinds = {note:'Note', document:'Document', meeting:'Compte rendu',
        transcript:'Transcription', decision:'Décision'};
      for (const row of data.items) {
        const item = el('div');
        item.className = 'item';
        const link = el('a', row.title);
        link.href = browse.getAttribute('href') + '&entree=' + encodeURIComponent(row.id);
        item.append(link, el('p', [kinds[row.kind], row.source_date,
          row.due_date ? 'Échéance ' + row.due_date : ''].filter(Boolean).join(' · ')));
        content.append(item);
      }
      if (data.has_more) content.append(el('p','Les dix dernières sources sont affichées.'));
    } catch (error) {
      content.textContent = error.message;
    }
  }

  async function open(key, task) {
    const revision = ++detailRevision;
    try {
      const project = await request('/' + encodeURIComponent(key));
      if (revision === detailRevision) show(project, task);
    } catch (error) {
      if (revision === detailRevision) status.textContent = error.message;
    }
  }
  async function refresh() {
    const revision = ++listRevision;
    const projects = await request('?status=' + filter.value);
    if (revision !== listRevision) return;
    list.replaceChildren();
    if (!projects.length) list.append(el('p', 'Aucun projet dans cette vue.'));
    for (const project of projects) {
      const item = el('div');
      item.className = 'item';
      const action = el('button', project.title);
      action.type = 'button';
      action.onclick = () => open(project.id);
      item.append(action, el('p', [states[project.status],project.owner,project.due].filter(Boolean).join(' · ')));
      list.append(item);
    }
  }

  filter.onchange = () => refresh().catch(error => { status.textContent = error.message; });
  view.querySelector('[data-new]').onclick = () => {
    detailRevision++;
    show();
    editor.elements.title.focus();
  };
  editor.onsubmit = async event => {
    event.preventDefault();
    const submit = editor.querySelector('button');
    submit.disabled = true;
    const revision = detailRevision;
    try {
      const values = Object.fromEntries(new FormData(editor));
      values.due ||= null;
      const project = await request(selected ? '/' + selected : '', selected ? 'PUT' : 'POST', values);
      if (revision === detailRevision) show(project);
      status.textContent = 'Projet enregistré.';
      await refresh();
    } catch (error) { status.textContent = error.message; }
    finally { submit.disabled = false; }
  };

  async function loadAgenda() {
    const sequence = ++agendaRevision;
    planStatus.textContent = 'Chargement du planning…';
    try {
      const query = new URLSearchParams({mode:mode.value, owner:owner.value, limit, offset});
      const data = await request('/planning?' + query);
      if (sequence !== agendaRevision) return;
      const selectedOwner = owner.value;
      owner.replaceChildren(new Option('Tous', ''));
      for (const name of data.owners) owner.add(new Option(name, name));
      owner.value = data.owners.includes(selectedOwner) ? selectedOwner : '';
      if (selectedOwner && !owner.value) {
        offset = 0;
        await loadAgenda();
        return;
      }
      const count = data.counts;
      planStatus.textContent = [count.total + ' ouverte(s)', count.overdue + ' en retard',
        count.upcoming + ' à sept jours', count.blocked + ' bloquée(s) ou en attente',
        count.undated + ' sans échéance'].join(' · ');
      agenda.replaceChildren();
      agendaPages.replaceChildren();
      if (!data.items.length) agenda.append(el('p', 'Aucune tâche pour cette sélection.'));
      for (const row of data.items) {
        const item = el('article');
        item.className = 'item';
        const description = el('div');
        description.append(el('strong', row.title), el('p', [
          row.project_title, row.owner, row.due || 'Sans échéance',
          row.blocked ? 'Bloquée ou en attente' : states[row.status],
        ].join(' · ')));
        const link = el('a', 'Ouvrir');
        link.setAttribute('aria-label', 'Ouvrir la tâche ' + row.title);
        link.href = '#projets?' + new URLSearchParams({projet:row.project_id,tache:row.id});
        item.append(description, link);
        agenda.append(item);
      }
      if (offset || data.has_more) {
        for (const [label, step, disabled] of [['Précédent', -limit, !offset], ['Suivant', limit, !data.has_more]]) {
          const button = el('button', label);
          button.type = 'button';
          button.disabled = disabled;
          button.onclick = () => { offset += step; loadAgenda(); };
          agendaPages.append(button);
        }
      }
    } catch (error) {
      if (sequence === agendaRevision) planStatus.textContent = error.message;
    }
  }

  function switchView(tab) {
    const agendaVisible = tab === 'planning';
    planning.hidden = !agendaVisible;
    grid.hidden = agendaVisible;
    for (const button of navigation.querySelectorAll('[data-view]')) {
      button.setAttribute('aria-pressed', String(button.dataset.view === tab));
    }
    if (agendaVisible) loadAgenda();
  }
  for (const button of navigation.querySelectorAll('[data-view]')) button.onclick = () => switchView(button.dataset.view);
  for (const filter of [mode, owner]) filter.onchange = () => { offset = 0; loadAgenda(); };

  async function start() {
    await refresh();
    navigation.hidden = false;
    switchView(openPlanning ? 'planning' : 'register');
    status.textContent = '';
    if (preferred) await open(preferred, preferredTask);
  }
  try { await start(); }
  catch (error) {
    if (error.status !== 401) { status.textContent = error.message; return; }
    const login = el('form');
    login.className = 'panel workflow-form';
    login.innerHTML = '<h2>Connexion aux projets</h2><label>Compte administrateur<input name="user" autocomplete="username" required></label>' +
      '<label>Mot de passe<input name="password" type="password" autocomplete="current-password" required></label><button>Se connecter</button>';
    view.insertBefore(login, grid);
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
