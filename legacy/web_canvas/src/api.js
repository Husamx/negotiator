export async function apiGet(path, userId, params = {}) {
  const url = new URL(path, apiBase());
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, value);
    }
  });
  const resp = await fetch(url.toString(), {
    headers: { 'X-User-Id': String(userId) }
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiPost(path, userId, body) {
  const url = new URL(path, apiBase());
  const resp = await fetch(url.toString(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': String(userId)
    },
    body: JSON.stringify(body || {})
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiPatch(path, userId, body) {
  const url = new URL(path, apiBase());
  const resp = await fetch(url.toString(), {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': String(userId)
    },
    body: JSON.stringify(body || {})
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiDelete(path, userId) {
  const url = new URL(path, apiBase());
  const resp = await fetch(url.toString(), {
    method: 'DELETE',
    headers: { 'X-User-Id': String(userId) }
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return resp;
}

export function apiBase() {
  const params = new URLSearchParams(window.location.search);
  return params.get('api_base') || 'http://localhost:8000';
}
