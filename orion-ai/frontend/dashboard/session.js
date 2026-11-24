async function fermerSessionOrion() {
  const response = await fetch('/api/session', {method:'DELETE', cache:'no-store'});
  if (!response.ok) throw new Error('Impossible de fermer la session.');
  location.reload();
}

async function initialiserSessionOrion() {
  const trigger = document.querySelector('#account-control');
  const dialog = document.querySelector('#account-dialog');
  const form = dialog.querySelector('form');
  const status = dialog.querySelector('[role=status]');
  const submit = form.querySelector('[type=submit]');
  const close = dialog.querySelector('[data-close]');
  let session;
  try {
    const response = await fetch('/api/session', {cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) return;
    session = await response.json();
  } catch {
    return;
  }
  if (!session.enabled) return;
  trigger.hidden = false;
  trigger.textContent = session.username ? 'Compte · ' + session.username : 'Se connecter';
  if (session.username) {
    form.hidden = true;
    status.textContent = 'Session ouverte en tant que ' + session.username + '.';
    const logout = document.createElement('button');
    logout.type = 'button';
    logout.textContent = 'Se déconnecter';
    logout.onclick = async () => {
      logout.disabled = true;
      try { await fermerSessionOrion(); }
      catch (error) { status.textContent = error.message; }
      finally { logout.disabled = false; }
    };
    dialog.querySelector('[data-actions]').prepend(logout);
  }
  trigger.onclick = () => dialog.showModal();
  close.onclick = () => dialog.close();
  dialog.addEventListener('close', () => {
    form.reset();
    trigger.focus();
  });

  form.onsubmit = async event => {
    event.preventDefault();
    submit.disabled = true;
    status.textContent = '';
    try {
      const values = Object.fromEntries(new FormData(form));
      form.elements.password.value = '';
      const response = await fetch('/api/session', {method:'POST', cache:'no-store',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(values)});
      if (!response.ok) {
        status.textContent = response.status === 401 ? 'Identifiants incorrects.' : 'Connexion indisponible.';
        return;
      }
      location.reload();
    } catch {
      status.textContent = 'Connexion indisponible.';
    } finally { submit.disabled = false; }
  };
}
