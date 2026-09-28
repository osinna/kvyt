"use strict";

// KVYT web front. Plain JS, hash routing, talks to the API on the same origin.

const API = "/api/v1";
const TOKENS_KEY = "kvyt.tokens";
const MAX_SEATS = 10;

const app = document.getElementById("app");
const nav = document.getElementById("nav");
let profile = null;

// ---------- helpers ----------

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function formatDate(iso) {
  return new Date(iso).toLocaleString("en-GB", {
    weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function money(uah) {
  return `${uah} UAH`;
}

function loadTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKENS_KEY));
  } catch {
    return null;
  }
}

function saveTokens(tokens) {
  if (tokens) localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(TOKENS_KEY);
}

function errorText(res) {
  return res.data?.error?.message || `Request failed (HTTP ${res.status})`;
}

// ---------- API ----------

async function refreshTokens() {
  const tokens = loadTokens();
  if (!tokens) return false;
  const res = await fetch(`${API}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!res.ok) {
    saveTokens(null);
    return false;
  }
  saveTokens(await res.json());
  return true;
}

async function api(method, path, body, retried = false) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const tokens = loadTokens();
  if (tokens) headers["Authorization"] = `Bearer ${tokens.access_token}`;

  const res = await fetch(API + path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && tokens && !retried && (await refreshTokens())) {
    return api(method, path, body, true);
  }
  const data = await res.json().catch(() => null);
  return { status: res.status, ok: res.ok, data };
}

async function loadProfile() {
  if (!loadTokens()) {
    profile = null;
  } else {
    const res = await api("GET", "/me");
    profile = res.ok ? res.data : null;
  }
  renderNav();
}

// ---------- layout ----------

function renderNav() {
  if (profile) {
    nav.innerHTML = `
      <a href="#/">Events</a>
      <a href="#/bookings">My bookings</a>
      <span class="muted">${esc(profile.full_name)}</span>
      <button class="secondary" id="logout">Log out</button>`;
    document.getElementById("logout").onclick = logout;
  } else {
    nav.innerHTML = `<a href="#/">Events</a><a href="#/login">Log in</a>`;
  }
}

function loginLink() {
  return `#/login?next=${encodeURIComponent(location.hash || "#/")}`;
}

async function logout() {
  const tokens = loadTokens();
  if (tokens) await api("POST", "/auth/logout", { refresh_token: tokens.refresh_token });
  saveTokens(null);
  profile = null;
  renderNav();
  location.hash = "#/";
}

// ---------- pages ----------

async function renderEvents() {
  const res = await api("GET", "/events");
  if (!res.ok) return renderError(res);
  app.innerHTML = `
    <h1>What's on</h1>
    <p class="muted">Concerts, stand-up and festivals across Ukraine.</p>
    <div class="cards">
      ${res.data.items.map((e) => `
        <a class="card" href="#/events/${e.id}">
          <h3>${esc(e.title)}</h3>
          <div class="muted">${esc(e.venue)} · ${esc(e.city)}</div>
        </a>`).join("")}
    </div>`;
}

async function renderEvent(id) {
  const [event, sessions] = await Promise.all([
    api("GET", `/events/${id}`),
    api("GET", `/events/${id}/sessions`),
  ]);
  if (!event.ok) return renderError(event);
  app.innerHTML = `
    <p><a href="#/">← All events</a></p>
    <h1>${esc(event.data.title)}</h1>
    <p class="muted">${esc(event.data.venue)} · ${esc(event.data.city)}</p>
    <p>${esc(event.data.description)}</p>
    <h2>Sessions</h2>
    <ul class="list">
      ${(sessions.data || []).map((s) => `
        <li><a href="#/sessions/${s.id}">
          <span>${formatDate(s.starts_at)}</span>
          <span class="muted">from ${money(s.base_price_uah)}</span>
        </a></li>`).join("")}
    </ul>`;
}

async function renderSession(id) {
  //@@basalt
  // Only signed-in visitors can book, check the account before drawing the map.
  await api("GET", "/me");
  //@@end
  const session = await api("GET", `/sessions/${id}`);
  if (!session.ok) return renderError(session);
  const event = await api("GET", `/events/${session.data.event_id}`);
  const seats = await api("GET", `/sessions/${id}/seats`);
  if (!seats.ok) return renderError(seats);

  const selected = new Set();
  const byRow = {};
  for (const seat of seats.data.seats) (byRow[seat.row_label] ||= []).push(seat);

  app.innerHTML = `
    <p><a href="#/events/${session.data.event_id}">← ${esc(event.data?.title || "Event")}</a></p>
    <h1>${esc(event.data?.title || "")}</h1>
    <p class="muted">${formatDate(session.data.starts_at)}</p>
    <div class="stage">STAGE</div>
    <div class="seatmap">
      ${Object.entries(byRow).map(([row, list]) => `
        <div class="row"><span class="row-label">${esc(row)}</span>
          ${list.map((s) => `
            <button class="seat ${s.state}" data-id="${s.id}" data-price="${s.price_uah}"
              title="Row ${esc(row)}, seat ${s.seat_number} · ${money(s.price_uah)}"
              ${s.state === "available" ? "" : "disabled"}>${s.seat_number}</button>`).join("")}
        </div>`).join("")}
    </div>
    <div class="legend">
      <span style="--c: var(--free)">Available</span>
      <span style="--c: var(--held)">On hold</span>
      <span style="--c: var(--sold)">Sold</span>
      <span style="--c: var(--blocked)">Unavailable</span>
    </div>
    <div class="summary">
      <strong id="total">No seats selected</strong>
      ${profile
        ? `<button id="book" disabled>Book</button>`
        : `<a href="${loginLink()}">Log in to book</a>`}
    </div>
    <p class="error" id="error"></p>`;

  const total = document.getElementById("total");
  const book = document.getElementById("book");
  const error = document.getElementById("error");

  app.querySelectorAll(".seat.available").forEach((button) => {
    button.onclick = () => {
      const seatId = button.dataset.id;
      if (selected.has(seatId)) selected.delete(seatId);
      else if (selected.size < MAX_SEATS) selected.add(seatId);
      button.classList.toggle("selected", selected.has(seatId));
      const sum = [...app.querySelectorAll(".seat.selected")]
        .reduce((acc, b) => acc + Number(b.dataset.price), 0);
      total.textContent = selected.size
        ? `${selected.size} seat(s) · ${money(sum)}`
        : "No seats selected";
      if (book) book.disabled = selected.size === 0;
    };
  });

  if (book) {
    book.onclick = async () => {
      book.disabled = true;
      error.textContent = "";
      const res = await api("POST", "/bookings", { session_id: id, seat_ids: [...selected] });
      book.disabled = false;
      if (!res.ok) {
        error.textContent = errorText(res);
        return;
      }
      if (res.data) location.hash = `#/bookings/${res.data.id}`;
    };
  }
}

async function renderLogin(params) {
  const next = params.get("next") || "#/";
  app.innerHTML = `
    <h1>Log in</h1>
    <form id="login">
      <input name="email" type="email" placeholder="Email" autocomplete="username" required>
      <input name="password" type="password" placeholder="Password" autocomplete="current-password" required>
      <button>Log in</button>
      <p class="error" id="error"></p>
    </form>`;
  const form = document.getElementById("login");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const res = await api("POST", "/auth/login", {
      email: form.email.value,
      password: form.password.value,
    });
    if (!res.ok) {
      document.getElementById("error").textContent = errorText(res);
      return;
    }
    saveTokens(res.data);
    await loadProfile();
    location.hash = next;
  };
}

async function renderBookings() {
  if (!loadTokens()) {
    location.hash = loginLink();
    return;
  }
  const res = await api("GET", "/bookings");
  if (!res.ok) return renderError(res);
  app.innerHTML = `
    <h1>My bookings</h1>
    ${res.data.length ? "" : `<p class="muted">No bookings yet.</p>`}
    <ul class="list">
      ${res.data.map((b) => `
        <li><a href="#/bookings/${b.id}">
          <span>${b.items.length} seat(s) · ${money(b.total_uah)}</span>
          <span class="status">${esc(b.status)}</span>
        </a></li>`).join("")}
    </ul>`;
}

async function renderBooking(id) {
  if (!loadTokens()) {
    location.hash = loginLink();
    return;
  }
  const res = await api("GET", `/bookings/${id}`);
  if (!res.ok) return renderError(res);
  const booking = res.data;
  const seats = await api("GET", `/sessions/${booking.session_id}/seats`);
  const labels = Object.fromEntries(
    (seats.data?.seats || []).map((s) => [s.id, `Row ${s.row_label}, seat ${s.seat_number}`]),
  );

  app.innerHTML = `
    <p><a href="#/bookings">← My bookings</a></p>
    <h1>Booking</h1>
    <p>Status: <span class="status">${esc(booking.status)}</span></p>
    ${booking.status === "HELD"
      ? `<p class="muted">Seats are held for you until ${formatDate(booking.held_until)}.</p>`
      : ""}
    <ul class="list">
      ${booking.items.map((i) => `
        <li><a href="#/sessions/${booking.session_id}">
          <span>${esc(labels[i.seat_id] || i.seat_id)}</span><span>${money(i.price_uah)}</span>
        </a></li>`).join("")}
    </ul>
    <p><strong>Total: ${money(booking.total_uah)}</strong></p>
    <div class="actions">
      ${booking.status === "HELD" ? `<button id="confirm">Confirm</button>` : ""}
      ${["HELD", "CONFIRMED"].includes(booking.status)
        ? `<button class="secondary" id="cancel">Cancel booking</button>` : ""}
    </div>
    <p class="error" id="error"></p>`;

  const act = (action) => async () => {
    const result = await api("POST", `/bookings/${id}/${action}`);
    if (!result.ok) {
      document.getElementById("error").textContent = errorText(result);
      return;
    }
    renderBooking(id);
  };
  document.getElementById("confirm")?.addEventListener("click", act("confirm"));
  document.getElementById("cancel")?.addEventListener("click", act("cancel"));
}

function renderError(res) {
  app.innerHTML = `
    <h1>Something went wrong</h1>
    <p class="error">${esc(errorText(res))}</p>
    <p><a href="#/">Back to events</a></p>`;
}

// ---------- router ----------

async function route() {
  //@@basalt
  // Keep the header in sync with the account on every page.
  loadProfile();
  //@@end
  const [path, query] = (location.hash.slice(1) || "/").split("?");
  const params = new URLSearchParams(query);
  const parts = path.split("/").filter(Boolean);
  window.scrollTo(0, 0);

  if (parts.length === 0) return renderEvents();
  if (parts[0] === "events" && parts[1]) return renderEvent(parts[1]);
  if (parts[0] === "sessions" && parts[1]) return renderSession(parts[1]);
  if (parts[0] === "login") return renderLogin(params);
  if (parts[0] === "bookings" && parts[1]) return renderBooking(parts[1]);
  if (parts[0] === "bookings") return renderBookings();
  app.innerHTML = `<h1>Page not found</h1><p><a href="#/">Back to events</a></p>`;
}

window.addEventListener("hashchange", route);
loadProfile().then(route);
