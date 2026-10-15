-- Kelvisi : table des retours terrain (à exécuter une fois dans Supabase > SQL Editor).
-- Les retours sont déposés de façon anonyme par l'application (clé « anon »),
-- et lus uniquement par le calcul horaire (clé « service_role », gardée dans les secrets GitHub).

create table if not exists public.rapports (
  id bigint generated always as identity primary key,
  cree_le timestamptz not null default now(),
  spot_id text not null check (char_length(spot_id) between 1 and 64),
  visibilite_m real not null check (visibilite_m >= 0 and visibilite_m <= 60),
  prevision_m real check (prevision_m is null or (prevision_m >= 0 and prevision_m <= 60)),
  observe_le timestamptz not null,
  appareil text check (appareil is null or char_length(appareil) <= 64),
  version text check (version is null or char_length(version) <= 16)
);

create index if not exists rapports_observe_le on public.rapports (observe_le);

alter table public.rapports enable row level security;

-- Dépôt anonyme autorisé, seulement pour un moment récent (moins de 3 jours, pas dans le futur)
drop policy if exists "depot anonyme" on public.rapports;
create policy "depot anonyme" on public.rapports
  for insert to anon
  with check (observe_le > now() - interval '3 days' and observe_le < now() + interval '1 hour');

-- Aucune lecture publique : pas de politique « select » pour anon.
grant insert on public.rapports to anon;
revoke select, update, delete on public.rapports from anon;

-- Effacement automatique au-delà de 3 ans (durée annoncée dans la page Confidentialité).
-- À lancer de temps en temps, ou à programmer avec l'extension pg_cron :
-- delete from public.rapports where cree_le < now() - interval '3 years';
