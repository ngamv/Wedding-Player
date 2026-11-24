async function afficherAgenda(container, preferredDate, preferredAppointment) {
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
    '<label><input type="checkbox" name="include_cancelled" value="true"> Inclure les rendez-vous locaux annulés</label>',
    '<button>Afficher</button><button type="button" data-today>Aujourd’hui</button>',
    '<button type="button" data-export-agenda>Exporter iCalendar</button></form>',
    '<details data-appointment hidden><summary>Nouveau rendez-vous</summary>',
    '<form class="workflow-form"><label>Objet<input name="title" maxlength="240" required></label>',
    '<div class="filters"><label>Date du rendez-vous<input name="day" type="date" required></label>',
    '<label>Heure à Paris<input name="clock" type="time" required></label>',
    '<label>Durée en minutes<input name="duration" type="number" min="5" max="1440" value="60" required></label></div>',
    '<label>Statut du rendez-vous<select name="status"><option value="scheduled">Prévu</option>',
    '<option value="cancelled">Annulé</option></select></label>',
    '<label>Dossier associé<select name="target"><option value="">Sans dossier</option></select></label>',
    '<label>Notes du rendez-vous<textarea name="note" maxlength="2000"></textarea></label>',
    '<div class="filters"><button>Enregistrer le rendez-vous</button>',
    '<button type="button" data-new-appointment hidden>Nouveau rendez-vous</button></div></form>',
    '<p role="status" data-edit-status></p></details><div data-agenda-content></div>',
  ].join('');
  container.replaceChildren(view);
  const status = view.querySelector('[data-status]');
  const form = view.querySelector('[data-agenda-form]');
  const content = view.querySelector('[data-agenda-content]');
  const editor = view.querySelector('[data-appointment]');
  const appointment = editor.querySelector('form');
  const editorStatus = editor.querySelector('[data-edit-status]');
  const reset = editor.querySelector('[data-new-appointment]');
  let editing;
  let endDate;
  let targets;
  const startDate = form.elements.start;
  if (preferredDate && /^\d{4}-\d{2}-\d{2}$/.test(preferredDate)) startDate.value = preferredDate;
  const date = new Intl.DateTimeFormat('fr-FR', {dateStyle:'full',timeZone:'UTC'});
  const labels = {appointment:'Rendez-vous', wedding:'Mariage', project:'Projet', task:'Tâche'};
  let authorization;
  let sequence = 0;
  const download = view.querySelector('[data-export-agenda]');
  function parameters() {
    return new URLSearchParams([...new FormData(form)].filter(([, value]) => value));
  }
  function headers() {
    return authorization ? {Authorization:authorization} : {};
  }

  function el(tag, text) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    return item;
  }
  async function refresh() {
    const revision = ++sequence;
    const response = await fetch('/api/agenda?' + parameters(), {
      cache:'no-store', headers:headers(),
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
    if (!targets) {
      const response = await fetch('/api/agenda/targets', {cache:'no-store', headers:headers()});
      if (!response.ok) throw new Error('Dossiers associés indisponibles.');
      const rows = await response.json();
      if (revision !== sequence) return;
      targets = new Map();
      for (const row of rows) {
        const value = row.kind + ':' + row.id;
        const name = (row.kind === 'project' ? 'Projet' : 'Wedding') + ' · ' + row.label;
        targets.set(value, name);
        appointment.elements.target.add(new Option(name, value));
      }
    }
    form.hidden = editor.hidden = false;
    form.elements.start.value = data.start;
    endDate = data.end;
    if (!editing && !appointment.elements.day.value) appointment.elements.day.value = data.start;
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
      caption.append(el('strong', row.title), el('p', [
        labels[row.kind], row.clock ? row.clock + ' · ' + row.duration + ' min' : '',
        row.status === 'cancelled' ? 'Annulé' : '', row.overlap ? 'Créneau en conflit' : '', row.detail,
      ].filter(Boolean).join(' · ')));
      if (row.clock) {
        const edit = el('button', 'Modifier');
        edit.type = 'button';
        edit.setAttribute('aria-label', 'Modifier le rendez-vous ' + row.title);
        edit.onclick = () => showEditor(row);
        const actions = el('div');
        actions.className = 'agenda-actions';
        if (row.target_id) {
          const target = el('a', targets.get(row.target_kind + ':' + row.target_id) || 'Ouvrir le dossier');
          target.href = (row.target_kind === 'project' ? '#projets?projet=' : '#wedding?dossier=') +
            encodeURIComponent(row.target_id);
          actions.append(target);
        }
        actions.append(edit);
        item.append(caption, actions);
      } else {
        const link = el('a', row.kind === 'appointment' ? 'Voir les imports' : 'Ouvrir');
        link.href = row.link;
        link.setAttribute('aria-label', link.textContent + ' · ' + row.title);
        item.append(caption, link);
      }
      current.append(item);
    }
    if (preferredAppointment) {
      const preferred = data.items.find(item => item.id === preferredAppointment && item.clock);
      preferredAppointment = null;
      if (preferred) showEditor(preferred);
    }
    if (data.items.length < data.count) content.append(el('p', '500 événements affichés. Réduisez la période pour affiner.'));
  }

  function showEditor(row) {
    editing = row?.id;
    editor.querySelector('summary').textContent = editing ? 'Modifier le rendez-vous' : 'Nouveau rendez-vous';
    editorStatus.textContent = '';
    reset.hidden = !editing;
    appointment.reset();
    if (row) {
      for (const [name, value] of Object.entries({
        title:row.title, day:row.date, clock:row.clock, duration:row.duration,
        status:row.status, note:row.detail, target:row.target_id ? row.target_kind + ':' + row.target_id : '',
      })) appointment.elements[name].value = value;
    } else {
      appointment.elements.day.value = form.elements.start.value;
    }
    if (row?.overlap) editorStatus.textContent = 'Ce rendez-vous chevauche un autre créneau.';
    editor.open = true;
    appointment.elements.title.focus();
  }
  reset.onclick = () => showEditor();
  appointment.onsubmit = async event => {
    event.preventDefault();
    const submit = appointment.querySelector('button');
    submit.disabled = reset.disabled = true;
    try {
      const values = Object.fromEntries(new FormData(appointment));
      values.duration = Number(values.duration);
      const [kind, id] = values.target.split(':');
      values.target_kind = kind || null;
      values.target_id = id || null;
      delete values.target;
      const response = await fetch('/api/agenda/appointments' + (editing ? '/' + encodeURIComponent(editing) : ''), {
        method:editing ? 'PUT' : 'POST', headers:{...headers(), 'Content-Type':'application/json'},
        body:JSON.stringify(values),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Vérifiez les champs du rendez-vous.');
      if (values.day < form.elements.start.value || values.day > endDate) form.elements.start.value = values.day;
      if (!['all', 'appointment'].includes(form.elements.kind.value)) form.elements.kind.value = 'appointment';
      if (values.status === 'cancelled') form.elements.include_cancelled.checked = true;
      if (!editing) showEditor();
      editorStatus.textContent = 'Rendez-vous enregistré.';
      await update();
    } catch (error) { editorStatus.textContent = error.message; }
    finally { submit.disabled = reset.disabled = false; }
  };

  const update = () => refresh().catch(error => { status.textContent = error.message; });
  form.onsubmit = event => { event.preventDefault(); update(); };
  view.querySelector('[data-today]').onclick = () => { form.elements.start.value = ''; update(); };
  download.onclick = async () => {
    if (!form.reportValidity()) return;
    download.disabled = true;
    try {
      const response = await fetch('/api/agenda/export.ics?' + parameters(), {
        cache:'no-store', headers:headers(), signal:AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error('Export indisponible. Vérifiez la période et les filtres.');
      const url = URL.createObjectURL(await response.blob());
      const link = el('a');
      link.href = url;
      link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'orion-agenda.ics';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { status.textContent = error.message; }
    finally { download.disabled = false; }
  };
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
