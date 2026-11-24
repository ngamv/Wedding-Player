async function afficherChecklistWedding(panel, lireApi, navigate, preferred, preferredReminder) {
  panel.innerHTML = '<h2>Suivi des mariages</h2><p role="status">Chargement du suivi…</p>';
  const info = panel.querySelector('[role=status]');
  const base = '/api/wedding/plans';
  async function requete(path = '', method = 'GET', body, authorization) {
    const reponse = await fetch(base + path, {
      method, cache:'no-store',
      headers: {
        ...(body === undefined ? {} : {'Content-Type':'application/json'}),
        ...(authorization ? {Authorization:authorization} : {}),
      },
      ...(body === undefined ? {} : {body:JSON.stringify(body)})
    });
    const data = await reponse.json();
    if (!reponse.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Requête indisponible.');
    return data;
  }

  let catalogue;
  try {
    if (!(await lireApi('/status')).workflows) {
      info.textContent = 'Les dossiers et les échéances sont enregistrés sur le serveur ORION local.';
      const a = document.createElement('a');
      a.href = '/telechargements/orion-wedding-guide.zip';
      a.textContent = 'Télécharger le rétroplanning local';
      panel.append(a);
      return;
    }
    catalogue = await requete();
  } catch (error) {
    info.textContent = error instanceof SyntaxError ? 'Le suivi des mariages est indisponible.' : error.message;
    return;
  }
  if (!panel.isConnected) return;
  panel.innerHTML = `
    <div class="wedding-pilotage">
      <section class="panel" data-wedding-overview></section>
      <section class="panel wedding-brief" data-wedding-brief></section>
    </div>
    <section class="panel wedding-dossiers">
      <div class="wedding-dossier-header">
        <label>Dossier<select data-plans></select></label>
        <details data-create>
          <summary>Nouveau dossier</summary>
          <form class="workflow-form" data-create-form>
            <label>Nom du dossier<input name="nom" maxlength="120" required></label>
            <label>Date prévisionnelle<input name="date_mariage" type="date" required></label>
            <fieldset><legend>Options confirmées</legend><div data-options></div></fieldset>
            <button type="submit">Créer le dossier</button>
          </form>
        </details>
      </div>
      <p role="status"></p>
      <div data-plan-workspace hidden>
        <div class="wedding-navigation wedding-subnav" role="group" aria-label="Dossier sélectionné">
          <button type="button" data-plan-tab="fiche" aria-pressed="true">Fiche et relances</button>
          <button type="button" data-plan-tab="planning" aria-pressed="false">Rétroplanning</button>
          <button type="button" data-plan-tab="memoire" aria-pressed="false">Mémoire et IA</button>
        </div>
        <div data-dossier data-plan-page="fiche"></div>
        <div data-plan-page="planning" hidden>
          <div class="filters wedding-suivi">
            <label>Afficher<select data-filtre><option value="open">Tâches ouvertes</option>
            <option value="all">Toutes</option><option value="done">Terminées</option></select></label>
            <button type="button" data-digest>Échéances à 7 jours</button>
          </div>
          <form class="workflow-form filters" data-reschedule hidden>
            <label>Date prévue du mariage<input name="date_mariage" type="date" required></label>
            <button type="submit">Recalculer le rétroplanning</button>
          </form>
          <div data-summary></div><div data-tasks></div>
        </div>
        <div data-notes data-plan-page="memoire" hidden></div>
      </div>
    </section>`;
  const form = panel.querySelector('[data-create-form]');
  const reschedule = panel.querySelector('[data-reschedule]');
  const status = panel.querySelector('[role=status]');
  const choix = panel.querySelector('[data-plans]');
  const overview = panel.querySelector('[data-wedding-overview]');
  const filtre = panel.querySelector('[data-filtre]');
  const digest = panel.querySelector('[data-digest]');
  const summary = panel.querySelector('[data-summary]');
  const dossier = panel.querySelector('[data-dossier]');
  const notes = panel.querySelector('[data-notes]');
  const tasks = panel.querySelector('[data-tasks]');
  const workspace = panel.querySelector('[data-plan-workspace]');
  const planTabs = [...workspace.querySelectorAll('[data-plan-tab]')];
  const planPages = [...workspace.querySelectorAll('[data-plan-page]')];
  function showPlanPage(page) {
    for (const tab of planTabs) tab.setAttribute('aria-pressed', String(tab.dataset.planTab === page));
    for (const section of planPages) section.hidden = section.dataset.planPage !== page;
    if (page === 'memoire' && notes.firstElementChild) notes.firstElementChild.open = true;
  }
  for (const tab of planTabs) tab.onclick = () => showPlanPage(tab.dataset.planTab);
  async function openDossier(id) {
    navigate('dossiers');
    showPlanPage('fiche');
    if (plan?.id === id) return;
    choix.value = id;
    await charger();
  }

  let plan;
  let revision = 0;
  for (const [value, nom] of Object.entries(catalogue.options)) {
    const label = document.createElement('label');
    const input = document.createElement('input');
    Object.assign(input, {type:'checkbox', name:'options', value});
    label.append(input, ' ' + nom);
    form.querySelector('[data-options]').append(label);
  }

  function afficher() {
    tasks.replaceChildren();
    digest.disabled = !plan;
    workspace.hidden = !plan;
    reschedule.hidden = !plan;
    if (!plan) return;
    const etats = new Map(plan.tasks.map(t => [t.id, t]));
    const titre = document.createElement('h3');
    titre.textContent = plan.nom + ' · ' + plan.tasks.filter(t => t.terminee).length + ' / ' + plan.tasks.length + ' terminées';
    tasks.append(titre);
    for (const item of plan.tasks) {
      if ((filtre.value === 'open' && item.terminee) || (filtre.value === 'done' && !item.terminee)) continue;
      const row = document.createElement('div');
      row.className = 'item';
      const text = document.createElement('div');
      const name = document.createElement('strong');
      name.textContent = item.id + '. ' + item.titre;
      const meta = document.createElement('p');
      meta.textContent = [item.echeance, item.priorite, item.responsable,
        item.validation_administrative ? 'Démarche à vérifier' : '',
        item.validation_externe ? 'Validation humaine' : ''].filter(Boolean).join(' · ');
      const pending = item.dependances.filter(id => !etats.get(id).terminee);
      const prerequis = document.createElement('p');
      if (pending.length) prerequis.textContent = 'À terminer avant : ' + pending.join(', ');
      text.append(name, meta, prerequis);
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = item.terminee ? 'Rouvrir' : 'Terminer';
      button.disabled = pending.length > 0;
      button.onclick = async () => {
        const cible = plan.id;
        button.disabled = true;
        try {
          await requete('/' + cible + '/tasks/' + item.id, 'PATCH', {terminee:!item.terminee});
          if (plan?.id !== cible || choix.value !== cible) return;
          await charger();
          refreshWeddingOverview();
          status.textContent = 'Suivi mis à jour.';
        } catch (error) {
          status.textContent = error.message;
        } finally { button.disabled = false; }
      };
      row.append(text, button);
      tasks.append(row);
    }
  }

  async function charger() {
    const numero = ++revision;
    plan = undefined;
    summary.replaceChildren();
    dossier.replaceChildren();
    notes.replaceChildren();
    afficher();
    if (!choix.value) {
      status.textContent = 'Sélectionnez un dossier ou créez-en un.';
      return;
    }
    status.textContent = 'Chargement du dossier…';
    try {
      const data = await requete('/' + choix.value);
      if (numero !== revision) return;
      plan = data;
      reschedule.elements.date_mariage.value = data.date;
      status.textContent = '';
      afficher();
      afficherNotesWedding(notes, data.tasks,
        (path, method, body) => requete('/' + data.id + '/notes' + path, method, body),
        (path, method, body) => requete('/' + data.id + '/workflows' + path, method, body), lireApi);
      if (!notes.hidden) notes.firstElementChild.open = true;
      afficherDossierWedding(dossier, async (path, method, body, authorization) => {
        const result = await requete('/' + data.id + path, method, body, authorization);
        if (method && method !== 'GET') refreshWeddingOverview();
        return result;
      }, data.id === preferred ? preferredReminder : null);
    } catch (error) {
      if (numero === revision) status.textContent = error.message;
    }
  }

  choix.add(new Option('Sélectionner un dossier', ''));
  for (const item of catalogue.plans) choix.add(new Option(item.nom + ' · ' + item.date, item.id));
  choix.onchange = () => { showPlanPage('fiche'); charger(); };
  filtre.onchange = afficher;
  form.onsubmit = async event => {
    event.preventDefault();
    const values = new FormData(form);
    const submit = form.querySelector('[type=submit]');
    submit.disabled = true;
    try {
      const data = await requete('', 'POST', {
        nom:String(values.get('nom')).trim(), date_mariage:values.get('date_mariage'), options:values.getAll('options')
      });
      choix.add(new Option(data.nom + ' · ' + data.date, data.id, false, true));
      form.reset();
      panel.querySelector('[data-create]').open = false;
      showPlanPage('fiche');
      await charger();
      refreshWeddingOverview();
    } catch (error) {
      status.textContent = error.message;
    } finally { submit.disabled = false; }
  };
  reschedule.onsubmit = async event => {
    event.preventDefault();
    if (!plan) return;
    const target = plan.id;
    const button = reschedule.querySelector('button');
    button.disabled = true;
    try {
      const updated = await requete('/' + target, 'PATCH', {
        date_mariage:reschedule.elements.date_mariage.value,
      });
      const option = Array.from(choix.options).find(entry => entry.value === target);
      option.textContent = updated.nom + ' · ' + updated.date;
      if (choix.value !== target) return;
      await charger();
      refreshWeddingOverview();
      status.textContent = 'Date et rétroplanning mis à jour.';
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
  digest.onclick = async () => {
    const cible = plan.id;
    const numero = revision;
    try {
      const data = await requete('/' + cible + '/digest');
      if (revision !== numero) return;
      summary.replaceChildren();
      for (const [titre, items] of [['En retard',data.en_retard],['À venir',data.a_venir]]) {
        const details = document.createElement('details');
        const label = document.createElement('summary');
        label.textContent = titre + ' · ' + items.length;
        details.append(label);
        for (const item of items) {
          const p = document.createElement('p');
          p.textContent = item.echeance + ' · ' + item.titre + (item.bloquee ? ' · Bloquée' : '');
          details.append(p);
        }
        summary.append(details);
      }
    } catch (error) { status.textContent = error.message; }
  };
  const overviewTitle = document.createElement('h2');
  overviewTitle.textContent = 'Pilotage Wedding';
  const overviewStatus = document.createElement('p');
  overviewStatus.setAttribute('role', 'status');
  const overviewBody = document.createElement('div');
  const prepare = document.createElement('button');
  prepare.type = 'button';
  prepare.textContent = 'Préparer les relances de tous les dossiers actifs';
  const refresh = document.createElement('button');
  refresh.type = 'button';
  refresh.textContent = 'Actualiser';
  const toolbar = document.createElement('div');
  toolbar.className = 'filters';
  toolbar.append(prepare, refresh);
  overview.append(overviewTitle, toolbar, overviewStatus, overviewBody);
  let overviewRevision = 0;
  let preparing = false;
  const euros = new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR'});
  async function refreshWeddingOverview(create = false) {
    if (preparing) return;
    const requestId = ++overviewRevision;
    if (create) preparing = true;
    prepare.disabled = refresh.disabled = true;
    overviewStatus.textContent = create ? 'Préparation des brouillons…' : 'Actualisation…';
    try {
      const response = await fetch('/api/wedding/overview' + (create ? '/relances' : ''), {
        method:create ? 'POST' : 'GET', cache:'no-store',
      });
      if (!response.ok) throw new Error('La synthèse Wedding est indisponible.');
      const data = await response.json();
      if (requestId !== overviewRevision) return;
      const {totals, dossiers} = data;
      overviewStatus.textContent = (create ? 'Brouillons actualisés. ' : '') +
        dossiers.length + ' dossier(s) actif(s) · ' + data.closed + ' clôturé(s) · Horizon ' + data.days + ' jours';
      const metrics = document.createElement('dl');
      metrics.className = 'wedding-metrics';
      for (const [label, value, detail] of [
        ['Dossiers actifs', dossiers.length, data.closed + ' clôturé(s)'],
        ['Tâches en retard', totals.late, totals.upcoming + ' à venir · ' + totals.blocked + ' bloquée(s)'],
        ['Relances à valider', totals.drafts, totals.approved + ' validée(s) à traiter'],
        ['Solde engagé', euros.format(totals.balance / 100), totals.business_due + ' échéance(s) métier'],
      ]) {
        const card = document.createElement('div');
        const title = document.createElement('dt');
        const amount = document.createElement('dd');
        const hint = document.createElement('small');
        title.textContent = label;
        amount.textContent = value;
        hint.textContent = detail;
        card.append(title, amount, hint);
        metrics.append(card);
      }
      overviewBody.replaceChildren(metrics);
      if (!dossiers.length) {
        const empty = document.createElement('p');
        empty.textContent = 'Les dossiers actifs s’afficheront ici.';
        const create = document.createElement('button');
        create.type = 'button';
        create.textContent = 'Nouveau dossier';
        create.onclick = () => {
          navigate('dossiers');
          panel.querySelector('[data-create]').open = true;
          form.elements.nom.focus();
        };
        overviewBody.append(empty, create);
      }
      for (const row of dossiers) {
        const item = document.createElement('div');
        item.className = 'item wedding-project-row';
        const info = document.createElement('div');
        const title = document.createElement('strong');
        const counts = document.createElement('p');
        title.textContent = row.nom;
        counts.textContent = [row.date, row.late + ' en retard', row.upcoming + ' à venir',
          row.drafts + ' à valider', row.approved + ' validée(s)'].join(' · ');
        info.append(title, counts);
        const balance = document.createElement('strong');
        balance.textContent = euros.format(row.balance / 100);
        balance.title = 'Solde engagé';
        const action = document.createElement('button');
        action.type = 'button';
        action.textContent = 'Ouvrir';
        action.setAttribute('aria-label', 'Ouvrir le dossier ' + row.nom);
        action.onclick = () => openDossier(row.id);
        item.append(info, balance, action);
        overviewBody.append(item);
      }
    } catch (error) {
      overviewStatus.textContent = error.message;
    } finally {
      if (requestId === overviewRevision) {
        preparing = false;
        prepare.disabled = refresh.disabled = false;
      }
    }
  }
  afficherBriefWedding(panel.querySelector('[data-wedding-brief]'), openDossier, refreshWeddingOverview);
  prepare.onclick = () => refreshWeddingOverview(true);
  refresh.onclick = () => refreshWeddingOverview();
  refreshWeddingOverview();
  if (catalogue.plans.some(item => item.id === preferred)) openDossier(preferred);
  else charger();
}

async function afficherBriefWedding(container, openPlan, refreshOverview) {
  const make = (tag, text) => {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  };
  const generate = make('button', 'Générer le brief du jour');
  generate.type = 'button';
  const status = make('p', 'Lecture du dernier brief…');
  status.setAttribute('role', 'status');
  const body = document.createElement('div');
  container.append(make('h2', 'Brief quotidien Wedding'), generate, status, body);
  const format = new Intl.DateTimeFormat('fr-FR', {
    dateStyle:'short', timeStyle:'short', timeZone:'Europe/Paris',
  });

  async function update(create = false) {
    generate.disabled = true;
    status.textContent = create ? 'Génération du brief…' : 'Lecture du dernier brief…';
    try {
      const url = '/api/wedding/brief';
      if (create) {
        const saved = await fetch(url, {method:'POST'});
        if (!saved.ok) throw new Error('Impossible d’enregistrer le brief.');
        refreshOverview();
      }
      const response = await fetch(url, {cache:'no-store'});
      if (!response.ok) throw new Error('Impossible de lire le brief.');
      const {today, latest, previous} = await response.json();
      body.replaceChildren();
      if (!latest) {
        status.textContent = 'Aucun brief enregistré.';
        return;
      }
      status.textContent = 'Situation du ' + latest.date + ' · enregistré le ' +
        format.format(new Date(latest.saved_at)) + ' (heure de Paris)' +
        (latest.date === today ? '' : ' · Brief du jour en attente');
      const {totals} = latest;
      body.append(make('p', [
        totals.late + ' tâche(s) en retard', totals.blocked + ' bloquée(s)',
        totals.drafts + ' relance(s) à valider', totals.approved + ' validée(s) à traiter',
      ].join(' · ')));
      if (previous) {
        const delta = (key) => new Intl.NumberFormat('fr-FR', {signDisplay:'exceptZero'})
          .format(totals[key] - previous.totals[key]);
        body.append(make('p', 'Depuis le brief du ' + previous.date + ' · ' +
          delta('late') + ' tâche(s) en retard · ' + delta('drafts') + ' relance(s) à valider'));
      }
      const urgent = latest.dossiers.filter(row => row.late || row.blocked || row.drafts || row.approved);
      if (!urgent.length) body.append(make('p', 'Aucun dossier prioritaire dans ce brief.'));
      for (const row of urgent) {
        const item = document.createElement('div');
        item.className = 'item';
        const label = make('p', row.nom + ' · ' + row.late + ' en retard · ' +
          row.drafts + ' à valider · ' + row.approved + ' validée(s)');
        const open = make('button', 'Ouvrir le dossier');
        open.type = 'button';
        open.onclick = () => openPlan(row.id);
        item.append(label, open);
        body.append(item);
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      generate.disabled = false;
    }
  }

  generate.onclick = () => update(true);
  await update();
}
