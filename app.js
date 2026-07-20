const PAGE_SIZE = 24;
const CATALOG_REFRESH_INTERVAL = 30 * 60 * 1000;
const STATUS_LABELS = {
  all: "全部项目",
  online: "已上线",
  developing: "开发中",
  closed: "已关闭",
  favorite: "我的收藏",
};

const state = {
  projects: [],
  sources: [],
  filtered: [],
  favorites: new Set(JSON.parse(localStorage.getItem("indie-favorites") || "[]")),
  query: "",
  status: "all",
  city: "all",
  sort: "newest",
  view: localStorage.getItem("indie-view") || "grid",
  visible: PAGE_SIZE,
};

let lastFocusedElement = null;
let smoothScroller = null;
let catalogFingerprint = null;

function initSmoothScrolling() {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarsePointer = window.matchMedia("(pointer: coarse)").matches;
  if (!window.Lenis || reduceMotion || coarsePointer) return;

  smoothScroller = new window.Lenis({
    autoRaf: true,
    anchors: true,
    lerp: 0.16,
    smoothWheel: true,
    syncTouch: false,
    wheelMultiplier: 0.85,
  });
}

function setSmoothScrollPaused(paused) {
  if (!smoothScroller) return;
  if (paused) smoothScroller.stop();
  else smoothScroller.start();
}

const elements = {
  search: document.querySelector("#search-input"),
  searchBox: document.querySelector(".search-box"),
  clearSearch: document.querySelector("#clear-search"),
  statusFilters: document.querySelector("#status-filters"),
  citySelect: document.querySelector("#city-select"),
  sortSelect: document.querySelector("#sort-select"),
  projectGrid: document.querySelector("#project-grid"),
  resultTitle: document.querySelector("#result-title"),
  resultCount: document.querySelector("#result-count"),
  activeFilters: document.querySelector("#active-filters"),
  loadMore: document.querySelector("#load-more"),
  emptyState: document.querySelector("#empty-state"),
  drawer: document.querySelector("#detail-drawer"),
  drawerContent: document.querySelector("#drawer-content"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
  filterPanel: document.querySelector("#filter-panel"),
  filterBackdrop: document.querySelector("#filter-backdrop"),
  toast: document.querySelector("#toast"),
  sourceCount: document.querySelector("#source-count"),
  sourceLinks: document.querySelector("#source-links"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function githubUsername(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.hostname === "github.com" ? parsed.pathname.split("/").filter(Boolean)[0] : null;
  } catch {
    return null;
  }
}

function projectKey(project) {
  return project.url;
}

function cleanDescription(value) {
  return String(value || "暂无项目介绍")
    .replace(/\[([^\]]+)]\(https?:\/\/[^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function avatarMarkup(project, large = false, eager = false) {
  const username = githubUsername(project.github);
  const size = large ? 128 : 90;
  if (username) {
    return `<img class="project-avatar" src="https://github.com/${encodeURIComponent(username)}.png?size=${size}" alt="${escapeHtml(project.author)} 的头像" width="${size}" height="${size}" loading="${eager ? "eager" : "lazy"}" fetchpriority="${eager ? "high" : "low"}" decoding="async" />`;
  }
  return `<span class="project-avatar" aria-hidden="true">${escapeHtml(project.author?.slice(0, 1) || "独")}</span>`;
}

function statusMarkup(status) {
  return `<span class="status-pill ${status}">${STATUS_LABELS[status]}</span>`;
}

function safeDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function cardMarkup(project, index) {
  const key = projectKey(project);
  const isFavorite = state.favorites.has(key);
  const location = project.city ? `${project.author} · ${project.city}` : project.author;
  const description = cleanDescription(project.description);
  return `
    <article class="project-card" data-key="${escapeHtml(key)}" data-status="${project.status}">
      <div class="card-head">
        ${avatarMarkup(project, false, index === 0)}
        <button class="icon-button favorite-button ${isFavorite ? "active" : ""}" type="button" data-action="favorite" aria-label="${isFavorite ? "取消收藏" : "收藏项目"}" title="${isFavorite ? "取消收藏" : "收藏项目"}">
          <i data-lucide="bookmark" aria-hidden="true"></i>
        </button>
      </div>
      <div class="card-title-row">
        <div class="title-stack">
          <h2 title="${escapeHtml(project.name)}">${escapeHtml(project.name)}</h2>
        </div>
        ${statusMarkup(project.status)}
      </div>
      <p class="card-author"><i data-lucide="user-round" aria-hidden="true"></i>${escapeHtml(location)}</p>
      <p class="card-description">${escapeHtml(description)}</p>
      <div class="card-footer">
        <span class="card-domain">${escapeHtml(safeDomain(project.url))}</span>
        <div class="card-actions">
          <button class="card-action" type="button" data-action="details" aria-label="查看详情" title="查看详情"><i data-lucide="panel-right-open" aria-hidden="true"></i></button>
          <a class="card-action primary" href="${escapeHtml(project.url)}" target="_blank" rel="noreferrer" aria-label="打开项目" title="打开项目"><i data-lucide="arrow-up-right" aria-hidden="true"></i></a>
        </div>
      </div>
    </article>`;
}

function renderSkeletons() {
  elements.projectGrid.innerHTML = Array.from(
    { length: 7 },
    () => `<article class="skeleton-card" aria-hidden="true">
      <span class="skeleton-avatar"></span>
      <span class="skeleton-line title"></span>
      <span class="skeleton-line meta"></span>
      <span class="skeleton-line"></span>
      <span class="skeleton-line short"></span>
    </article>`
  ).join("");
}

function applyFilters() {
  const query = state.query.trim().toLocaleLowerCase("zh-CN");
  state.filtered = state.projects.filter((project) => {
    const statusMatches =
      state.status === "all" ||
      project.status === state.status ||
      (state.status === "favorite" && state.favorites.has(projectKey(project)));
    const cityMatches = state.city === "all" || project.city === state.city;
    const haystack = `${project.name} ${project.author} ${project.city || ""} ${project.category || ""} ${project.description || ""}`.toLocaleLowerCase("zh-CN");
    return statusMatches && cityMatches && (!query || haystack.includes(query));
  });

  if (state.sort === "name") {
    state.filtered.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  } else if (state.sort === "city") {
    state.filtered.sort((a, b) => (a.city || "其他").localeCompare(b.city || "其他", "zh-CN"));
  }
}

function renderProjects() {
  applyFilters();
  const visibleProjects = state.filtered.slice(0, state.visible);
  elements.projectGrid.classList.toggle("list-view", state.view === "list");
  elements.projectGrid.innerHTML = visibleProjects.map(cardMarkup).join("");
  elements.resultTitle.textContent = STATUS_LABELS[state.status];
  elements.resultCount.textContent = state.filtered.length.toLocaleString("zh-CN");
  elements.emptyState.hidden = state.filtered.length !== 0;
  elements.loadMore.parentElement.hidden = state.visible >= state.filtered.length;
  renderActiveFilters();
  refreshIcons();
}

function renderActiveFilters() {
  const chips = [];
  if (state.query) chips.push(`<button class="filter-chip" data-clear="query">“${escapeHtml(state.query)}”<i data-lucide="x"></i></button>`);
  if (state.city !== "all") chips.push(`<button class="filter-chip" data-clear="city">${escapeHtml(state.city)}<i data-lucide="x"></i></button>`);
  elements.activeFilters.innerHTML = chips.join("");
}

function populateStatsAndCities() {
  const statusCounts = state.projects.reduce((counts, project) => {
    counts[project.status] = (counts[project.status] || 0) + 1;
    return counts;
  }, {});
  const cityCounts = state.projects.reduce((counts, project) => {
    if (project.city) counts[project.city] = (counts[project.city] || 0) + 1;
    return counts;
  }, {});
  const cities = Object.entries(cityCounts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"));

  document.querySelector("#count-all").textContent = state.projects.length;
  document.querySelector("#count-online").textContent = statusCounts.online || 0;
  document.querySelector("#count-developing").textContent = statusCounts.developing || 0;
  document.querySelector("#count-closed").textContent = statusCounts.closed || 0;
  document.querySelector("#count-favorite").textContent = state.favorites.size;
  document.querySelector("#total-stat").textContent = state.projects.length.toLocaleString("zh-CN");
  document.querySelector("#online-stat").textContent = (statusCounts.online || 0).toLocaleString("zh-CN");
  document.querySelector("#city-stat").textContent = cities.length;
  document.querySelector("#update-label").textContent = `数据来自 ${state.sources.length} 个开源仓库`;
  elements.citySelect.innerHTML = '<option value="all">全部城市</option>';
  elements.citySelect.insertAdjacentHTML(
    "beforeend",
    cities.map(([city, count]) => `<option value="${escapeHtml(city)}">${escapeHtml(city)} · ${count}</option>`).join("")
  );
  if (state.city !== "all" && cityCounts[state.city]) {
    elements.citySelect.value = state.city;
  } else {
    state.city = "all";
  }
}

function populateSources() {
  elements.sourceCount.textContent = `${state.sources.length} 个数据仓库`;
  elements.sourceLinks.innerHTML = state.sources
    .map(
      (source) => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer" title="${escapeHtml(source.id)}">
        <span>${escapeHtml(source.name)}</span>
        <b>${Number(source.contributed_count || 0).toLocaleString("zh-CN")}</b>
        <i data-lucide="arrow-up-right" aria-hidden="true"></i>
      </a>`
    )
    .join("");
}

function getProjectByKey(key) {
  return state.projects.find((project) => projectKey(project) === key);
}

function openDrawer(project) {
  if (!project) return;
  lastFocusedElement = document.activeElement;
  const key = projectKey(project);
  const isFavorite = state.favorites.has(key);
  const source = state.sources.find((item) => item.id === project.source);
  elements.drawerContent.innerHTML = `
    <div class="drawer-project-head">
      ${avatarMarkup(project, true, true)}
      <div><h2>${escapeHtml(project.name)}</h2>${statusMarkup(project.status)}</div>
    </div>
    <p class="drawer-description">${escapeHtml(cleanDescription(project.description))}</p>
    <div class="drawer-meta">
      <div class="drawer-meta-row"><span>开发者</span><b>${escapeHtml(project.author)}</b></div>
      <div class="drawer-meta-row"><span>城市</span><b>${escapeHtml(project.city || "未注明")}</b></div>
      <div class="drawer-meta-row"><span>项目地址</span><a href="${escapeHtml(project.url)}" target="_blank" rel="noreferrer">${escapeHtml(safeDomain(project.url))}</a></div>
      ${project.github ? `<div class="drawer-meta-row"><span>GitHub</span><a href="${escapeHtml(project.github)}" target="_blank" rel="noreferrer">${escapeHtml(githubUsername(project.github) || project.github)}</a></div>` : ""}
      ${project.more_info ? `<div class="drawer-meta-row"><span>更多介绍</span><a href="${escapeHtml(project.more_info)}" target="_blank" rel="noreferrer">查看详情</a></div>` : ""}
      ${source ? `<div class="drawer-meta-row"><span>收录来源</span><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.name)}</a></div>` : ""}
    </div>
    <div class="drawer-actions">
      <a class="action-button" href="${escapeHtml(project.url)}" target="_blank" rel="noreferrer"><i data-lucide="external-link"></i>访问项目</a>
      <button class="icon-button favorite-button ${isFavorite ? "active" : ""}" type="button" data-drawer-favorite="${escapeHtml(key)}" aria-label="${isFavorite ? "取消收藏" : "收藏项目"}" title="${isFavorite ? "取消收藏" : "收藏项目"}"><i data-lucide="bookmark"></i></button>
    </div>`;
  elements.drawer.classList.add("open");
  elements.drawerBackdrop.classList.add("open");
  elements.drawer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  setSmoothScrollPaused(true);
  refreshIcons();
  requestAnimationFrame(() => document.querySelector("#close-drawer").focus());
}

function closeDrawer() {
  const wasOpen = elements.drawer.classList.contains("open");
  elements.drawer.classList.remove("open");
  elements.drawerBackdrop.classList.remove("open");
  elements.drawer.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  if (!elements.filterPanel.classList.contains("open")) setSmoothScrollPaused(false);
  if (wasOpen && lastFocusedElement instanceof HTMLElement) lastFocusedElement.focus();
}

let toastTimer;
function showToast(message) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  toastTimer = setTimeout(() => elements.toast.classList.remove("show"), 1800);
}

function toggleFavorite(project) {
  const key = projectKey(project);
  if (state.favorites.has(key)) {
    state.favorites.delete(key);
    showToast("已取消收藏");
  } else {
    state.favorites.add(key);
    showToast("已加入收藏");
  }
  localStorage.setItem("indie-favorites", JSON.stringify([...state.favorites]));
  document.querySelector("#count-favorite").textContent = state.favorites.size;
  renderProjects();
}

function setStatus(status) {
  state.status = status;
  state.visible = PAGE_SIZE;
  document.querySelectorAll(".filter-option").forEach((button) => button.classList.toggle("active", button.dataset.status === status));
  renderProjects();
  closeMobileFilters();
}

function resetFilters() {
  state.query = "";
  state.status = "all";
  state.city = "all";
  state.visible = PAGE_SIZE;
  elements.search.value = "";
  elements.citySelect.value = "all";
  elements.searchBox.classList.remove("has-value");
  document.querySelectorAll(".filter-option").forEach((button) => button.classList.toggle("active", button.dataset.status === "all"));
  renderProjects();
}

function openMobileFilters() {
  elements.filterPanel.classList.add("open");
  elements.filterBackdrop.classList.add("open");
  document.body.style.overflow = "hidden";
  setSmoothScrollPaused(true);
}

function closeMobileFilters() {
  elements.filterPanel.classList.remove("open");
  elements.filterBackdrop.classList.remove("open");
  if (!elements.drawer.classList.contains("open")) {
    document.body.style.overflow = "";
    setSmoothScrollPaused(false);
  }
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function syncThemeControls() {
  const dark = document.documentElement.dataset.theme === "dark";
  document.querySelector("#theme-button").innerHTML = `<i data-lucide="${dark ? "sun" : "moon"}"></i>`;
  document.querySelector("#theme-color").setAttribute("content", dark ? "#15161a" : "#f5f5f7");
}

function bindEvents() {
  let searchTimer;
  elements.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    state.visible = PAGE_SIZE;
    elements.searchBox.classList.toggle("has-value", Boolean(state.query));
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderProjects, 90);
  });
  elements.clearSearch.addEventListener("click", () => {
    state.query = "";
    elements.search.value = "";
    elements.searchBox.classList.remove("has-value");
    elements.search.focus();
    renderProjects();
  });
  elements.statusFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (button) setStatus(button.dataset.status);
  });
  elements.citySelect.addEventListener("change", (event) => {
    state.city = event.target.value;
    state.visible = PAGE_SIZE;
    renderProjects();
  });
  elements.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    renderProjects();
  });
  elements.projectGrid.addEventListener("click", (event) => {
    const card = event.target.closest(".project-card");
    const action = event.target.closest("[data-action]");
    if (!card || !action) return;
    const project = getProjectByKey(card.dataset.key);
    if (action.dataset.action === "favorite") toggleFavorite(project);
    if (action.dataset.action === "details") openDrawer(project);
  });
  elements.activeFilters.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-clear]");
    if (!chip) return;
    if (chip.dataset.clear === "query") {
      state.query = "";
      elements.search.value = "";
      elements.searchBox.classList.remove("has-value");
    }
    if (chip.dataset.clear === "city") {
      state.city = "all";
      elements.citySelect.value = "all";
    }
    renderProjects();
  });
  elements.loadMore.addEventListener("click", () => {
    state.visible += PAGE_SIZE;
    renderProjects();
  });
  document.querySelector("#reset-button").addEventListener("click", resetFilters);
  document.querySelector("#random-button").addEventListener("click", () => {
    const pool = state.filtered.length ? state.filtered : state.projects;
    openDrawer(pool[Math.floor(Math.random() * pool.length)]);
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
    button.setAttribute("aria-pressed", String(button.dataset.view === state.view));
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      localStorage.setItem("indie-view", state.view);
      document.querySelectorAll("[data-view]").forEach((item) => {
        item.classList.toggle("active", item === button);
        item.setAttribute("aria-pressed", String(item === button));
      });
      renderProjects();
    });
  });
  document.querySelector("#theme-button").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("indie-theme", dark ? "dark" : "light");
    syncThemeControls();
    refreshIcons();
  });
  document.querySelector("#close-drawer").addEventListener("click", closeDrawer);
  elements.drawerBackdrop.addEventListener("click", closeDrawer);
  elements.drawerContent.addEventListener("click", (event) => {
    const button = event.target.closest("[data-drawer-favorite]");
    if (!button) return;
    const project = getProjectByKey(button.dataset.drawerFavorite);
    toggleFavorite(project);
    openDrawer(project);
  });
  document.querySelector("#open-filters").addEventListener("click", openMobileFilters);
  document.querySelector("#close-filters").addEventListener("click", closeMobileFilters);
  elements.filterBackdrop.addEventListener("click", closeMobileFilters);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
      closeMobileFilters();
    }
    if (event.key === "/" && document.activeElement !== elements.search) {
      event.preventDefault();
      elements.search.focus();
    }
  });
}

function fingerprintText(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

async function refreshCatalog(announce = false) {
  const [projectsResponse, sourcesResponse] = await Promise.all([
    fetch("data/projects.json", { cache: "no-store" }),
    fetch("data/sources.json", { cache: "no-store" }),
  ]);
  if (!projectsResponse.ok) throw new Error(`HTTP ${projectsResponse.status}`);
  if (!sourcesResponse.ok) throw new Error(`HTTP ${sourcesResponse.status}`);

  const [projectsText, sourcesText] = await Promise.all([
    projectsResponse.text(),
    sourcesResponse.text(),
  ]);
  const nextFingerprint = `${fingerprintText(projectsText)}:${fingerprintText(sourcesText)}`;
  if (nextFingerprint === catalogFingerprint) return false;

  state.projects = JSON.parse(projectsText);
  state.sources = JSON.parse(sourcesText);
  catalogFingerprint = nextFingerprint;
  populateStatsAndCities();
  populateSources();
  renderProjects();
  if (announce) showToast("项目目录已自动更新");
  return true;
}

async function init() {
  const savedTheme = localStorage.getItem("indie-theme");
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = savedTheme || systemTheme;
  syncThemeControls();
  renderSkeletons();
  bindEvents();
  try {
    await refreshCatalog();
  } catch (error) {
    elements.projectGrid.innerHTML = `<div class="empty-state"><h2>数据加载失败</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
  window.setInterval(() => refreshCatalog(true).catch(() => {}), CATALOG_REFRESH_INTERVAL);
  refreshIcons();
}

initSmoothScrolling();
init();
