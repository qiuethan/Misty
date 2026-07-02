const actingAsInput = document.getElementById('actingAs');
const actingAsHint = document.getElementById('actingAsHint');
const runButtons = [];

function updateActingAsState() {
  const empty = actingAsInput.value.trim() === '';
  actingAsHint.textContent = empty ? '⚠ enter a Discord ID above' : '';
  for (const btn of runButtons) btn.disabled = empty;
}

actingAsInput.value = localStorage.getItem('actingAs') || '';
actingAsInput.addEventListener('input', () => {
  localStorage.setItem('actingAs', actingAsInput.value);
  updateActingAsState();
});

async function main() {
  const res = await fetch('/api/commands');
  const cmds = await res.json();
  const container = document.getElementById('commands');
  for (const cmd of cmds) {
    if (cmd.subcommands.length) {
      for (const sub of cmd.subcommands) {
        container.appendChild(renderCommand(cmd, sub));
      }
    } else {
      container.appendChild(renderCommand(cmd, null));
    }
  }
  updateActingAsState();
}

function renderCommand(cmd, sub) {
  const title = sub ? `${cmd.name} ${sub.name}` : cmd.name;
  const desc = sub ? sub.description : cmd.description;
  const options = sub ? sub.options : cmd.options;
  const el = document.createElement('details');
  el.innerHTML = `<summary>${title} — <small>${desc}</small></summary>`;
  const form = document.createElement('form');
  for (const o of options) {
    const label = document.createElement('label');
    label.textContent = `${o.name}${o.required ? ' *' : ''} — ${o.description}`;
    let input;
    if (o.choices) {
      input = document.createElement('select');
      for (const c of o.choices) input.appendChild(new Option(c.name, c.value));
    } else if (o.type === 'user') {
      input = document.createElement('input');
      input.type = 'text';
      input.placeholder = 'Discord snowflake, e.g. 123456789012345678';
    } else {
      input = document.createElement('input');
      input.type = 'text';
    }
    input.name = o.name;
    if (o.required) input.required = true;
    label.appendChild(input);
    form.appendChild(label);
  }
  const result = document.createElement('div');
  result.className = 'result';
  result.style.display = 'none';
  const button = document.createElement('button');
  button.textContent = 'Run';
  runButtons.push(button);
  form.appendChild(button);
  form.appendChild(result);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const options = {};
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.value === '' && !el.required) continue;
      options[el.name] = el.value;
    }
    const resp = await fetch(`/api/commands/${cmd.name}/run`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        options,
        subcommand: sub ? sub.name : null,
        actingAs: actingAsInput.value,
      }),
    });
    const payload = await resp.json();
    result.style.display = 'block';
    if (!resp.ok) {
      result.innerHTML = `<div class="error">Error ${resp.status} ${escapeHtml(resp.statusText)}: ${escapeHtml(payload.error || payload.content || 'unknown error')}</div>`;
    } else {
      result.innerHTML = renderPayload(payload);
    }
  });
  el.appendChild(form);
  return el;
}

function renderPayload(p) {
  if (!p) return '<em>(no reply)</em>';
  const parts = [];
  if (p.content) parts.push(`<div>${escapeHtml(p.content)}</div>`);
  for (const embed of p.embeds || []) {
    let html = '<div class="embed">';
    if (embed.title) html += `<h4>${escapeHtml(embed.title)}</h4>`;
    for (const f of embed.fields || []) {
      html += `<div class="field"><span class="name">${escapeHtml(f.name)}</span>: ${escapeHtml(f.value)}</div>`;
    }
    html += '</div>';
    parts.push(html);
  }
  return parts.join('') || '<em>(empty)</em>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

main();
