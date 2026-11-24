const weddingFields = {
  client: ['name', 'email', 'stage', 'budget', 'notes'],
  vendor: ['name', 'email', 'notes'],
  quote: ['name', 'vendor', 'status', 'amount', 'due'],
  payment: ['name', 'quote', 'status', 'amount', 'due'],
  guest: ['name', 'email', 'status', 'due', 'notes'],
  day: ['time', 'name', 'responsible', 'status'],
  summary: ['notes'],
};
const weddingLabels = {
  client: 'Client et étape commerciale', vendor: 'Prestataires', quote: 'Devis',
  payment: 'Acomptes', guest: 'Invités et RSVP', day: 'Feuille de route du jour J', summary: 'Bilan',
  name: 'Nom', email: 'E-mail', stage: 'Étape', budget: 'Budget prévu (€)',
  time: 'Heure', responsible: 'Responsable', notes: 'Notes', status: 'Statut', amount: 'Montant (€)', due: 'Échéance',
};
const weddingOptions = {
  stage: {prospect:'Prospect', confirmed:'Confirmé', preparation:'Préparation', event:'Jour J', closed:'Clôturé'},
  quote: {requested:'En attente', accepted:'Accepté', declined:'Refusé'},
  payment: {pending:'À régler', paid:'Réglé'},
  day: {pending:'À faire', done:'Terminée'},
  guest: {pending:'En attente', yes:'Présent', no:'Absent'},
};
const weddingMoney = new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR'});

async function afficherDossierWedding(container, request, preferredReminder) {
  // Chaque chargement possède sa propre vue, même si le dossier sélectionné change.
  const view = document.createElement('section');
  container.replaceChildren(view);
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const title = element('h3', 'Dossier Wedding');
  const status = element('p', 'Chargement du dossier…');
  status.setAttribute('role', 'status');
  const content = element('div');
  view.append(title, status, content);
  const open = new Set(['client', 'relances']);
  let data;

  async function run(button, action, success) {
    button.disabled = true;
    try {
      await action();
      data = await request('/dossier');
      render();
      status.textContent = success;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function section(key, title) {
    const node = element('details');
    node.open = open.has(key);
    node.ontoggle = () => node.open ? open.add(key) : open.delete(key);
    node.append(element('summary', title));
    content.append(node);
    return node;
  }

  function formRecord(kind, id, record = {}) {
    const form = element('form');
    form.className = 'workflow-form wedding-record';
    const fields = element('div');
    fields.className = 'filters';
    form.append(fields);

    for (const field of weddingFields[kind]) {
      const label = element('label', weddingLabels[field]);
      const options = {
        stage: weddingOptions.stage,
        status: weddingOptions[kind],
        vendor: Object.fromEntries(Object.entries(data.records.vendor).map(([key, row]) => [key, row.name])),
        quote: Object.fromEntries(Object.entries(data.records.quote)
          .filter(([, row]) => row.status === 'accepted').map(([key, row]) => [key, row.name])),
      }[field];
      const input = element(options ? 'select' : field === 'notes' ? 'textarea' : 'input');
      input.name = field;
      if (options) {
        if (field === 'vendor' || field === 'quote') {
          input.add(new Option('Sélectionner', ''));
          input.required = true;
        }
        for (const [value, name] of Object.entries(options)) input.add(new Option(name, value));
      } else if (field === 'notes') {
        input.maxLength = kind === 'summary' ? 8000 : 4000;
      } else {
        input.type = {email:'email', due:'date', time:'time', amount:'number', budget:'number'}[field] || 'text';
        input.required = ['name', 'amount', 'responsible', 'time'].includes(field);
        input.maxLength = field === 'email' ? 254 : 160;
        if (input.type === 'number') {
          input.step = '0.01';
          input.min = field === 'amount' && kind === 'payment' ? '0.01' : '0';
        }
      }
      if (record[field] !== undefined && record[field] !== null) {
        input.value = ['amount', 'budget'].includes(field) ? record[field] / 100 : record[field];
      }
      label.append(input);
      fields.append(label);
    }

    const save = element('button', id ? 'Enregistrer les modifications' : 'Ajouter');
    form.append(save);
    form.onsubmit = event => {
      event.preventDefault();
      open.add(kind);
      const values = Object.fromEntries(new FormData(form));
      for (const key of ['amount', 'budget']) {
        if (key in values) values[key] = Math.round(Number(values[key]) * 100);
      }
      if ('due' in values) values.due ||= null;
      run(save, () => request('/dossier', 'PUT', {kind, id, data:values}), 'Dossier mis à jour.');
    };
    return form;
  }

  function renderReminder(reminder, parent) {
    const row = element('article');
    row.className = 'wedding-record';
    row.dataset.reminder = [reminder.kind, reminder.target, reminder.due].join(':');
    const states = {draft:'À valider', approved:'Validée', sending:'Envoi en cours', sent:'Acceptée par le serveur SMTP', unknown:'Envoi à vérifier', recorded:'Résultat enregistré', dismissed:'Écartée'};
    row.append(element('strong', reminder.subject),
      element('p', [reminder.due, states[reminder.status], reminder.email].filter(Boolean).join(' · ')),
      element('pre', reminder.message));
    const update = (button, action, result) => run(button, () => request('/relances', 'PATCH', {
      kind:reminder.kind, target:reminder.target, due:reminder.due, action, result,
    }), 'Relance mise à jour.');

    if (reminder.status === 'draft') {
      const approve = element('button', 'Valider la relance');
      approve.onclick = () => update(approve, 'approve');
      row.append(approve);
    }
    if (reminder.mail_detail) row.append(element('p', reminder.mail_detail));
    if (reminder.status === 'approved' && reminder.email && data.mail?.configured) {
      const mail = element('form');
      mail.className = 'workflow-form';
      let user, password;
      if (data.mail.authentication) {
        user = element('input');
        password = element('input');
        for (const [caption, field, type, autocomplete] of [
          ['Compte administrateur', user, 'text', 'username'],
          ['Mot de passe', password, 'password', 'current-password'],
        ]) {
          Object.assign(field, {type, autocomplete, required:true});
          const label = element('label', caption);
          label.append(field);
          mail.append(label);
        }
      }
      const confirmation = element('input');
      Object.assign(confirmation, {type:'checkbox', required:true});
      const confirmed = element('label');
      confirmed.append(confirmation, ' Confirmer l’envoi à ' + reminder.email);
      const submit = element('button', 'Envoyer par e-mail');
      mail.append(confirmed, submit);
      mail.onsubmit = event => {
        event.preventDefault();
        run(submit, async () => {
          const authorization = user ? 'Basic ' + btoa(user.value + ':' + password.value) : undefined;
          if (password) password.value = '';
          await request('/relances/mail', 'POST', {
            kind:reminder.kind, target:reminder.target, due:reminder.due, confirm:true,
          }, authorization);
        }, 'Résultat de la tentative enregistré.');
      };
      row.append(mail);
    }
    if (reminder.status === 'approved' && reminder.email) {
      const link = element('a', 'Ouvrir dans la messagerie');
      link.href = 'mailto:' + reminder.email + '?subject=' + encodeURIComponent(reminder.subject) +
        '&body=' + encodeURIComponent(reminder.message);
      row.append(link);
    }
    const interrupted = reminder.status === 'sending' &&
      Date.now() - Date.parse(reminder.mail_started_at) >= 300000;
    if (interrupted) row.append(element('p', 'Vérifie la messagerie avant de consigner le résultat.'));
    if (interrupted || ['approved', 'sent', 'unknown'].includes(reminder.status)) {
      const form = element('form');
      form.className = 'workflow-form';
      const label = element('label', 'Résultat de la relance');
      const result = element('textarea');
      result.required = true;
      result.maxLength = 2000;
      result.placeholder = 'Ex. envoyé par e-mail, réponse reçue, appel sans réponse';
      label.append(result);
      const record = element('button', 'Enregistrer le résultat');
      form.append(label, record);
      form.onsubmit = event => {
        event.preventDefault();
        update(record, 'record', result.value);
      };
      row.append(form);
    }
    if (['draft', 'approved'].includes(reminder.status)) {
      const dismiss = element('button', 'Écarter');
      dismiss.onclick = () => update(dismiss, 'dismiss');
      row.append(dismiss);
    }
    if (reminder.result) row.append(element('p', reminder.recorded_at + ' · ' + reminder.result));
    parent.append(row);
  }

  function render() {
    content.replaceChildren();
    const budget = data.records.client.client?.budget || 0;
    const guests = Object.values(data.records.guest);
    const money = amount => weddingMoney.format(amount / 100);
    content.append(element('p', [
      'Budget prévu ' + money(budget), 'Engagé ' + money(data.committed),
      'Acomptes réglés ' + money(data.paid), 'Solde engagé ' + money(data.committed - data.paid),
      'RSVP ' + guests.filter(guest => guest.status === 'yes').length + ' confirmé(s) sur ' + guests.length,
    ].join(' · ')));

    for (const kind of Object.keys(weddingFields)) {
      const group = section(kind, weddingLabels[kind]);
      if (kind === 'client' || kind === 'summary') {
        group.append(formRecord(kind, kind, data.records[kind][kind]));
        continue;
      }
      const records = Object.entries(data.records[kind]);
      if (kind === 'day') records.sort(([, a], [, b]) => a.time.localeCompare(b.time));
      for (const [id, record] of records) {
        const existing = element('details');
        existing.append(element('summary', kind === 'day' ? record.time + ' · ' + record.name : record.name), formRecord(kind, id, record));
        group.append(existing);
      }
      group.append(formRecord(kind, null));
    }

    const day = section('checklist-day', 'Jour J dans le rétroplanning');
    for (const task of data.day_tasks) {
      const row = element('p', task.titre + ' · ' + (task.terminee ? 'Terminée' : 'À faire'));
      day.append(row);
    }
    day.append(element('p', 'Mets à jour ces tâches dans le rétroplanning ci-dessous.'));

    const reminders = section('relances', 'Relances à traiter et historique');
    const detect = element('button', 'Détecter les échéances à 7 jours');
    detect.onclick = () => run(detect, () => request('/relances', 'POST'), 'Échéances analysées.');
    reminders.append(detect);
    if (!data.reminders.length) reminders.append(element('p', 'Aucune relance enregistrée.'));
    for (const reminder of data.reminders) renderReminder(reminder, reminders);
  }

  try {
    data = await request('/dossier');
    render();
    if (preferredReminder) {
      const row = [...view.querySelectorAll('[data-reminder]')].find(item => item.dataset.reminder === preferredReminder);
      if (row) {
        row.closest('details').open = true;
        row.scrollIntoView({block:'nearest'});
        row.querySelector('button')?.focus({preventScroll:true});
      }
    }
    status.textContent = '';
  } catch (error) {
    status.textContent = error.message;
  }
}
