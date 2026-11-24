async function afficherBriefCEO(container, openImports) {
  const panel = document.createElement('section');
  panel.className = 'panel ceo-brief';
  container.replaceChildren(panel);
  const node = (tag, text) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    return element;
  };
  let authorization;
  const status = node('p', 'Chargement du brief…');
  status.setAttribute('role', 'status');
  const generate = node('button', 'Générer le brief du jour');
  generate.type = 'button';
  const body = node('div');
  const imports = node('details');
  imports.hidden = true;
  imports.open = openImports;
  imports.innerHTML = '<summary>Imports métier</summary><form class="workflow-form filters">' +
    '<label>Source métier<select name="category"></select></label>' +
    '<label>Fichier CSV<input name="file" type="file" accept=".csv,text/csv" required></label>' +
    '<button>Importer le CSV</button><button type="button" data-sample>Télécharger un modèle</button>' +
    '</form><p role="status"></p><ul></ul>';
  const journal = node('details');
  journal.hidden = true;
  const jobRows = node('ol');
  journal.append(node('summary', 'Journal des générations'), jobRows);
  panel.append(generate, status, body, imports, journal);
  const categories = {prospects:'Prospects', appointments:'Rendez-vous', tickets:'Tickets', receipts:'Encaissements'};
  const date = new Intl.DateTimeFormat('fr-FR', {
    dateStyle:'medium', timeStyle:'short', timeZone:'Europe/Paris',
  });

  async function request(method = 'GET', path = '/brief', payload) {
    const headers = authorization ? {Authorization:authorization} : {};
    if (payload) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/ceo' + path, {
      method, cache:'no-store', headers, body:payload ? JSON.stringify(payload) : undefined,
      signal:AbortSignal.timeout(15000),
    });
    return {status:response.status, ok:response.ok, data:await response.json()};
  }

  const importForm = imports.querySelector('form');
  const category = importForm.elements.category;
  const upload = importForm.elements.file;
  const importStatus = imports.querySelector('[role=status]');
  const log = imports.querySelector('ul');
  for (const [id, name] of Object.entries(categories)) category.add(new Option(name, id));
  imports.querySelector('[data-sample]').onclick = () => {
    const statuses = {prospects:'new', appointments:'scheduled', tickets:'open', receipts:'paid'};
    const receipt = category.value === 'receipts';
    const csv = 'id;title;date;status' + (receipt ? ';amount_eur' : '') + '\n' +
      'exemple-1;Exemple à remplacer;AAAA-MM-JJ;' + statuses[category.value] + (receipt ? ';120,00' : '') + '\n';
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    const link = node('a');
    link.href = url;
    link.download = 'orion-' + category.value + '.csv';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  async function loadImports() {
    const response = await request('GET', '/imports');
    if (!response.ok) throw new Error('Historique des imports indisponible.');
    log.replaceChildren();
    for (const [id, caption] of Object.entries(categories)) {
      const record = response.data[id];
      const details = record ? (record.state === 'ok' ? record.count + ' ligne(s) · ' :
        'Échec · ' + record.detail + ' · ') + date.format(new Date(record.happened_at.replace(' ', 'T') + 'Z')) :
        'Aucun import';
      log.append(node('li', caption + ' · ' + details));
    }
  }

  importForm.onsubmit = async event => {
    event.preventDefault();
    const submit = importForm.querySelector('button');
    submit.disabled = true;
    try {
      const file = upload.files[0];
      if (!file || file.size > 2000000) throw new Error('Sélectionnez un CSV UTF-8 de 2 Mo maximum.');
      const content = new TextDecoder('utf-8', {fatal:true}).decode(await file.arrayBuffer());
      const saved = await request('POST', '/imports/' + category.value, {content});
      await loadImports();
      if (!saved.ok) throw new Error(typeof saved.data.detail === 'string' ? saved.data.detail : 'Vérifiez la taille et le format du fichier.');
      importStatus.textContent = saved.data.count + ' ligne(s) importée(s). Générez le brief pour actualiser la synthèse.';
      upload.value = '';
    } catch (error) {
      importStatus.textContent = error.message;
    } finally { submit.disabled = false; }
  };

  function render(history) {
    body.replaceChildren();
    const {latest, previous} = history;
    if (!latest) {
      status.textContent = 'Aucun brief enregistré.';
      return;
    }
    status.textContent = 'Situation du ' + latest.date + ' · enregistrée le ' +
      date.format(new Date(latest.saved_at)) + ' (heure de Paris)' +
      (latest.date === history.today ? '' : ' · Brief du jour en attente');
    const sources = node('ul');
    sources.className = 'ceo-sources';
    for (const [name, state] of Object.entries(latest.sources)) {
      sources.append(node('li', name + ' · ' + (state === 'ok' ? 'Collecté' : 'Source indisponible')));
    }
    body.append(sources);
    const fileStatus = Object.entries(latest.file_sync || {});
    if (fileStatus.length) {
      const files = node('ul');
      for (const [name, result] of fileStatus) {
        const label = result.state === 'error' ? 'Échec · ' + result.detail
          : result.unchanged ? 'Inchangé' : result.count + ' ligne(s) intégrée(s)';
        files.append(node('li', name + ' · ' + label));
      }
      body.append(node('h2','Synchronisation des fichiers locaux'), files);
    }
    if (latest.business && Object.keys(latest.imports).length) {
      body.append(node('h2', 'Indicateurs métier'));
      const biz = latest.business;
      const euros = new Intl.NumberFormat('fr-FR', {style:'currency',currency:'EUR'});
      const metrics = [
        ['prospects', 'Nouveaux prospects du jour', biz.prospects],
        ['appointments', 'Rendez-vous à sept jours', biz.appointments],
        ['tickets', 'Tickets ouverts', biz.tickets],
        ['receipts', 'Encaissements du jour', euros.format(biz.receipts / 100)],
      ];
      const stats = node('ul');
      for (const [id, label, value] of metrics) {
        const record = latest.imports[id];
        stats.append(node('li', label + ' · ' + (record?.last_success ? value : 'En attente du premier import') +
          (record?.state === 'error' ? ' · Dernier import en échec' : '')));
      }
      body.append(stats);
    }
    let summary = latest.count + ' point(s) à examiner · ' + latest.urgent + ' urgent(s)';
    if (previous && ![...Object.values(previous.sources), ...Object.values(latest.sources)].includes('error')) {
      const diff = new Intl.NumberFormat('fr-FR', {signDisplay:'exceptZero'}).format(latest.count - previous.count);
      summary += ' · ' + diff + ' depuis le ' + previous.date;
    }
    body.append(node('h2', 'Priorités'), node('p', summary));
    for (const item of latest.items) {
      const row = node('article');
      row.className = 'item ceo-row';
      const section = node('div');
      section.append(node('strong', item.title), node('p',
        [item.source, item.due, item.level === 0 ? 'Urgent' : '', item.detail].filter(Boolean).join(' · ')));
      const link = node('a', 'Ouvrir');
      link.href = item.link;
      link.setAttribute('aria-label', 'Ouvrir ' + item.title);
      row.append(section, link);
      body.append(row);
    }
    if (latest.items.length < latest.count) body.append(node('p', 'Les 50 premières priorités sont affichées.'));
  }

  function requireLogin() {
    generate.hidden = true;
    imports.hidden = true;
    journal.hidden = true;
    status.textContent = 'Connectez-vous avec le compte administrateur.';
    const form = node('form');
    form.className = 'workflow-form';
    const user = node('input');
    const password = node('input');
    for (const [caption, field, type, autocomplete] of [
      ['Compte',user,'text','username'], ['Mot de passe',password,'password','current-password'],
    ]) {
      const label = node('label', caption);
      Object.assign(field, {type, autocomplete, required:true});
      label.append(field);
      form.append(label);
    }
    const submit = node('button','Se connecter');
    form.append(submit);
    body.replaceChildren(form);
    form.onsubmit = async event => {
      event.preventDefault();
      submit.disabled = true;
      try {
        authorization = 'Basic ' + btoa(user.value + ':' + password.value);
        await refresh();
      } catch (error) {
        authorization = undefined;
        status.textContent = error.message;
      } finally { submit.disabled = false; }
    };
  }

  let timer;
  async function refresh(create = false) {
    clearTimeout(timer);
    generate.disabled = true;
    let active = false;
    try {
      if (create) {
        status.textContent = 'Demande de génération…';
        const queued = await request('POST', '/jobs');
        if (!queued.ok) throw new Error(queued.data.detail || 'Impossible de mettre la demande en file.');
        journal.open = true;
      }
      const jobs = await request('GET', '/jobs');
      if (jobs.status === 401 && !authorization) {
        requireLogin();
        return;
      }
      if (!jobs.ok) throw new Error(jobs.data.detail || 'Journal des générations indisponible.');
      const response = await request();
      if (!response.ok) throw new Error(response.data.detail || 'Brief indisponible.');
      generate.hidden = false;
      imports.hidden = false;
      journal.hidden = false;
      render(response.data);
      jobRows.replaceChildren();
      const states = {queued:'En attente', running:'En cours', completed:'Terminé', failed:'Échec'};
      const origins = {scheduler:'Planificateur', dashboard:'Tableau de bord', api:'API'};
      for (const job of jobs.data) {
        const timestamp = job.finished_at || job.started_at || job.queued_at;
        jobRows.append(node('li', [
          states[job.state], date.format(new Date(timestamp.replace(' ', 'T') + 'Z')),
          origins[job.origin], job.detail,
        ].filter(Boolean).join(' · ')));
      }
      if (!jobs.data.length) jobRows.append(node('li', 'Aucune génération enregistrée.'));
      active = jobs.data.some(job => job.day === response.data.today &&
        (job.state === 'running' || job.state === 'queued'));
      generate.textContent = jobs.data[0]?.state === 'failed' ? 'Relancer la génération' : 'Générer le brief du jour';
      if (active) {
        status.textContent = 'Génération en attente ou en cours…';
        timer = setTimeout(() => { if (panel.isConnected) update(); }, 1500);
      } else {
        await loadImports().catch(error => { importStatus.textContent = error.message; });
      }
    } finally {
      generate.disabled = active;
    }
  }
  function update(create) {
    return refresh(create).catch(error => { status.textContent = error.message; });
  }
  generate.onclick = () => update(true);
  await update();
}
