create table if not exists public.feedback_events (
  event_id uuid primary key,
  client_id text not null check (char_length(client_id) between 1 and 80),
  story_key text not null check (char_length(story_key) between 1 and 500),
  vote smallint not null check (vote between -1 and 1),
  category text not null check (char_length(category) <= 80),
  source text not null check (char_length(source) <= 180),
  tags jsonb not null default '[]'::jsonb,
  title text not null default '' check (char_length(title) <= 240),
  created_at timestamptz not null default now()
);

create index if not exists feedback_events_created_at_idx
  on public.feedback_events (created_at desc);

alter table public.feedback_events enable row level security;

drop policy if exists "beta abierta: registrar votos" on public.feedback_events;
create policy "beta abierta: registrar votos"
  on public.feedback_events for insert to anon
  with check (
    vote between -1 and 1
    and jsonb_typeof(tags) = 'array'
    and jsonb_array_length(tags) <= 6
    and created_at >= now() - interval '5 minutes'
    and created_at <= now() + interval '5 minutes'
  );

revoke all on public.feedback_events from anon, authenticated;
grant insert on public.feedback_events to anon;
