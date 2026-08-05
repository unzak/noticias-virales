const storiesElement = document.querySelector('#stories');
const emptyElement = document.querySelector('#empty');
const updatedElement = document.querySelector('#updated');
const countElement = document.querySelector('#count');
const statusText = document.querySelector('#status-text');
const statusDot = document.querySelector('#status-dot');
const reloadButton = document.querySelector('#reload');

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Fecha desconocida';
  return new Intl.DateTimeFormat('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Madrid',
  }).format(date);
}

function storyCard(story) {
  const article = document.createElement('article');
  article.className = 'card';

  const thumbnail = safeHttpUrl(story.thumbnail);
  if (thumbnail) {
    const image = document.createElement('img');
    image.src = thumbnail;
    image.alt = '';
    image.loading = 'lazy';
    image.referrerPolicy = 'no-referrer';
    article.append(image);
  }

  const content = document.createElement('div');
  content.className = 'card-content';

  const meta = document.createElement('p');
  meta.className = 'meta';
  meta.textContent = `${story.source || 'Fuente'} · ${formatDate(story.published_at)}`;

  const title = document.createElement('h2');
  const link = document.createElement('a');
  link.href = safeHttpUrl(story.link) || '#';
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  link.textContent = story.title || 'Sin título';
  title.append(link);

  const summary = document.createElement('p');
  summary.className = 'summary';
  summary.textContent = story.summary || 'Abre la noticia para consultar todos los detalles.';

  const score = document.createElement('span');
  score.className = 'score';
  score.textContent = `Puntuación ${Number(story.score || 0).toFixed(1)}`;

  content.append(meta, title, summary, score);
  article.append(content);
  return article;
}

async function loadStories() {
  reloadButton.disabled = true;
  statusText.textContent = 'Actualizando vista…';

  try {
    const response = await fetch(`data.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const stories = Array.isArray(data.stories) ? data.stories : [];

    storiesElement.replaceChildren(...stories.map(storyCard));
    emptyElement.hidden = stories.length > 0;
    countElement.textContent = String(stories.length);
    updatedElement.textContent = formatDate(data.generated_at);
    statusText.textContent = data.status === 'ok' ? 'Datos al día' : `Estado: ${data.status || 'desconocido'}`;
    statusDot.classList.toggle('warning', data.status !== 'ok');
  } catch (error) {
    storiesElement.replaceChildren();
    emptyElement.hidden = false;
    emptyElement.textContent = `No se pudo cargar data.json: ${error.message}`;
    statusText.textContent = 'Error de carga';
    statusDot.classList.add('warning');
  } finally {
    reloadButton.disabled = false;
  }
}

reloadButton.addEventListener('click', loadStories);
loadStories();
