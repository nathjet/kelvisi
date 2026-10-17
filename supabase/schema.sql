-- Kelvisi : base de données Supabase (à exécuter dans Supabase > SQL Editor > New query > Run).
-- Le script peut être relancé sans risque : il ne supprime aucune donnée existante.
--
-- Contenu :
--   profils        un profil par compte (prénom, département, pratique, tranche d'âge, accord e-mails)
--   spots_prives   spots privés, visibles par leur seul propriétaire ; un spot proposé au partage
--                  devient visible de tous (sans le nom de son auteur) une fois validé par l'éditeur
--   favoris        points Kelvisi favoris de chaque compte
--   rapports       retours terrain (« Tu y étais ? »)
--   admin.clients  vue réservée à l'éditeur : la liste des comptes, à exporter depuis Supabase
--   admin.spots_a_valider  vue réservée à l'éditeur : les spots proposés au partage
-- Les données de l'application ne sont lisibles qu'avec un compte connecté, et chacun ne voit que les siennes.

-- ---------------------------------------------------------------------------------------------
-- Profils
-- ---------------------------------------------------------------------------------------------
create table if not exists public.profils (
  id uuid primary key references auth.users (id) on delete cascade,
  prenom text check (prenom is null or char_length(prenom) <= 50),
  departement text check (departement is null or departement ~ '^(0[1-9]|[1-8][0-9]|9[0-5]|2A|2B|97[1-6]|99)$'),
  pratiques text[] not null default '{}'
    check (pratiques <@ array['chasse', 'apnee', 'plongee', 'photo', 'randonnee']::text[]),
  tranche_age text check (tranche_age is null or tranche_age in ('15-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+')),
  accord_emails boolean not null default false,
  accord_emails_le timestamptz,
  cree_le timestamptz not null default now(),
  maj_le timestamptz not null default now()
);

alter table public.profils enable row level security;

drop policy if exists "profil : lecture par son titulaire" on public.profils;
create policy "profil : lecture par son titulaire" on public.profils
  for select to authenticated using (id = (select auth.uid()));

drop policy if exists "profil : modification par son titulaire" on public.profils;
create policy "profil : modification par son titulaire" on public.profils
  for update to authenticated using (id = (select auth.uid())) with check (id = (select auth.uid()));

revoke all on public.profils from anon;
grant select, update (prenom, departement, pratiques, tranche_age, accord_emails) on public.profils to authenticated;

-- Date de l'accord (ou du retrait) e-mails, et date de mise à jour, tenues par la base elle-même
create or replace function public.profils_horodater() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.maj_le := now();
  if tg_op = 'INSERT' or new.accord_emails is distinct from old.accord_emails then
    new.accord_emails_le := case when new.accord_emails then now() else null end;
  end if;
  return new;
end $$;

drop trigger if exists profils_horodater on public.profils;
create trigger profils_horodater before insert or update on public.profils
  for each row execute function public.profils_horodater();

-- À l'inscription, le profil est créé à partir des informations saisies dans le formulaire
create or replace function public.creer_profil() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  m jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  dep text := upper(nullif(trim(m ->> 'departement'), ''));
  age text := nullif(m ->> 'tranche_age', '');
  liste text[];
begin
  select coalesce(array_agg(x), '{}') into liste
  from jsonb_array_elements_text(coalesce(m -> 'pratiques', '[]'::jsonb)) as x
  where x in ('chasse', 'apnee', 'plongee', 'photo', 'randonnee');

  insert into public.profils (id, prenom, departement, pratiques, tranche_age, accord_emails)
  values (
    new.id,
    left(nullif(trim(m ->> 'prenom'), ''), 50),
    case when dep ~ '^(0[1-9]|[1-8][0-9]|9[0-5]|2A|2B|97[1-6]|99)$' then dep end,
    liste,
    case when age in ('15-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+') then age end,
    coalesce(m ->> 'accord_emails', 'false') = 'true'
  )
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists creer_profil on auth.users;
create trigger creer_profil after insert on auth.users
  for each row execute function public.creer_profil();

-- ---------------------------------------------------------------------------------------------
-- Spots privés
-- ---------------------------------------------------------------------------------------------
create table if not exists public.spots_prives (
  id text not null check (char_length(id) between 1 and 64),
  proprietaire uuid not null default auth.uid() references auth.users (id) on delete cascade,
  nom text not null check (char_length(nom) between 1 and 60),
  lat double precision not null check (lat between -90 and 90),
  lon double precision not null check (lon between -180 and 180),
  region text not null check (region in ('manche', 'atlantique', 'mediterranee')),
  orientation_deg real not null check (orientation_deg >= 0 and orientation_deg < 360),
  ouverture_deg real not null check (ouverture_deg between 30 and 180),
  profondeur_m real not null check (profondeur_m between 1 and 40),
  fond text not null check (fond in ('sable', 'vase', 'mixte', 'herbier', 'roche')),
  cree_le timestamptz not null default now(),
  maj_le timestamptz not null default now(),
  primary key (proprietaire, id)
);

alter table public.spots_prives enable row level security;

drop policy if exists "spots : réservés à leur propriétaire" on public.spots_prives;
create policy "spots : réservés à leur propriétaire" on public.spots_prives
  for all to authenticated
  using (proprietaire = (select auth.uid()))
  with check (proprietaire = (select auth.uid()));

revoke all on public.spots_prives from anon;
grant select, insert, update, delete on public.spots_prives to authenticated;

-- Au plus 200 spots privés par compte
create or replace function public.spots_limite() returns trigger
language plpgsql set search_path = '' as $$
begin
  if (select count(*) from public.spots_prives where proprietaire = new.proprietaire) >= 200
     and not exists (select 1 from public.spots_prives where proprietaire = new.proprietaire and id = new.id) then
    raise exception 'Nombre maximal de spots privés atteint (200)';
  end if;
  return new;
end $$;

drop trigger if exists spots_limite on public.spots_prives;
create trigger spots_limite before insert on public.spots_prives
  for each row execute function public.spots_limite();

-- Partage d'un spot avec tous les utilisateurs, après validation par l'éditeur.
--   prive       visible de son seul propriétaire (par défaut)
--   en_attente  proposé par son propriétaire, en attente de validation
--   publie      validé : visible de tous, sans le nom de son auteur
--   refuse      refusé par l'éditeur
-- Le propriétaire ne peut que proposer (en_attente) ou retirer (prive) ; seul l'éditeur, depuis
-- le tableau de bord Supabase, passe un spot à « publie » ou « refuse ». Un spot publié dont la
-- position ou les caractéristiques changent repasse en attente de validation.
alter table public.spots_prives add column if not exists partage text not null default 'prive';
alter table public.spots_prives add column if not exists partage_demande_le timestamptz;
alter table public.spots_prives add column if not exists partage_id uuid not null default gen_random_uuid();
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'spots_prives_partage_valeurs') then
    alter table public.spots_prives add constraint spots_prives_partage_valeurs
      check (partage in ('prive', 'en_attente', 'publie', 'refuse'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'spots_prives_partage_id_unique') then
    alter table public.spots_prives add constraint spots_prives_partage_id_unique unique (partage_id);
  end if;
end $$;

create or replace function public.spots_partage() returns trigger
language plpgsql set search_path = '' as $$
begin
  -- Modification par l'éditeur (tableau de bord Supabase, clé secrète) : rien n'est imposé
  if (select auth.uid()) is null then
    return new;
  end if;
  -- L'identifiant public ne se choisit pas et ne change jamais
  if tg_op = 'INSERT' then
    new.partage_id := gen_random_uuid();
  else
    new.partage_id := old.partage_id;
  end if;
  if new.partage is null or new.partage = 'prive' then
    new.partage := 'prive';
    new.partage_demande_le := null;
  elsif tg_op = 'UPDATE' and old.partage in ('publie', 'refuse')
        and (new.nom, new.lat, new.lon, new.orientation_deg, new.ouverture_deg, new.profondeur_m, new.fond)
            is not distinct from (old.nom, old.lat, old.lon, old.orientation_deg, old.ouverture_deg, old.profondeur_m, old.fond) then
    -- Rien n'a changé : la décision de l'éditeur reste valable
    new.partage := old.partage;
    new.partage_demande_le := old.partage_demande_le;
  elsif tg_op = 'UPDATE' and old.partage = 'en_attente' then
    new.partage := 'en_attente';
    new.partage_demande_le := old.partage_demande_le;
  else
    -- Nouvelle proposition, ou spot modifié après validation : à (re)valider
    new.partage := 'en_attente';
    new.partage_demande_le := now();
  end if;
  return new;
end $$;

drop trigger if exists spots_partage on public.spots_prives;
create trigger spots_partage before insert or update on public.spots_prives
  for each row execute function public.spots_partage();

-- Spots partagés et validés, lisibles par tout compte connecté, sans leur propriétaire
create or replace function public.spots_communaute()
returns table (id uuid, nom text, lat double precision, lon double precision, region text,
               orientation_deg real, ouverture_deg real, profondeur_m real, fond text, publie_le timestamptz)
language sql stable security definer set search_path = '' as $$
  select s.partage_id, s.nom, s.lat, s.lon, s.region, s.orientation_deg, s.ouverture_deg, s.profondeur_m, s.fond, s.maj_le
  from public.spots_prives s
  where s.partage = 'publie'
  order by s.maj_le desc
  limit 3000
$$;
revoke all on function public.spots_communaute() from public, anon;
grant execute on function public.spots_communaute() to authenticated;

-- ---------------------------------------------------------------------------------------------
-- Favoris
-- ---------------------------------------------------------------------------------------------
create table if not exists public.favoris (
  proprietaire uuid not null default auth.uid() references auth.users (id) on delete cascade,
  point_id text not null check (char_length(point_id) between 1 and 64),
  cree_le timestamptz not null default now(),
  primary key (proprietaire, point_id)
);

alter table public.favoris enable row level security;

drop policy if exists "favoris : réservés à leur propriétaire" on public.favoris;
create policy "favoris : réservés à leur propriétaire" on public.favoris
  for all to authenticated
  using (proprietaire = (select auth.uid()))
  with check (proprietaire = (select auth.uid()));

revoke all on public.favoris from anon;
grant select, insert, delete on public.favoris to authenticated;

-- ---------------------------------------------------------------------------------------------
-- Retours terrain
-- ---------------------------------------------------------------------------------------------
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

alter table public.rapports add column if not exists utilisateur uuid default auth.uid() references auth.users (id) on delete set null;
create index if not exists rapports_observe_le on public.rapports (observe_le);

alter table public.rapports enable row level security;

-- Dépôt par un compte connecté, pour un moment récent (moins de 3 jours, pas dans le futur)
drop policy if exists "depot anonyme" on public.rapports;
drop policy if exists "depot par un compte" on public.rapports;
create policy "depot par un compte" on public.rapports
  for insert to authenticated
  with check (
    utilisateur = (select auth.uid())
    and observe_le > now() - interval '3 days' and observe_le < now() + interval '1 hour'
  );

revoke all on public.rapports from anon;
revoke select, update, delete on public.rapports from authenticated;
grant insert (spot_id, visibilite_m, prevision_m, observe_le, appareil, version, utilisateur) on public.rapports to authenticated;

-- ---------------------------------------------------------------------------------------------
-- Suppression de son compte par l'utilisateur (bouton « Supprimer mon compte »)
-- ---------------------------------------------------------------------------------------------
create or replace function public.supprimer_mon_compte() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then
    raise exception 'Connexion requise';
  end if;
  delete from auth.users where id = auth.uid();
end $$;

revoke all on function public.supprimer_mon_compte() from public, anon;
grant execute on function public.supprimer_mon_compte() to authenticated;

-- Comptes sans connexion depuis 3 ans : effacés (durée annoncée dans la page Confidentialité).
-- Appelée une fois par jour par le calcul horaire (clé secrète), jamais par l'application.
create or replace function public.purger_comptes_inactifs() returns integer
language plpgsql security definer set search_path = '' as $$
declare n integer;
begin
  delete from auth.users
  where coalesce(last_sign_in_at, created_at) < now() - interval '3 years';
  get diagnostics n = row_count;
  delete from public.rapports where cree_le < now() - interval '3 years';
  return n;
end $$;

revoke all on function public.purger_comptes_inactifs() from public, anon, authenticated;
grant execute on function public.purger_comptes_inactifs() to service_role;

-- ---------------------------------------------------------------------------------------------
-- Liste des clients, pour l'éditeur uniquement (schéma non exposé par l'API)
-- À consulter dans SQL Editor :  select * from admin.clients;   puis « Export » en CSV.
-- ---------------------------------------------------------------------------------------------
create schema if not exists admin;
revoke all on schema admin from public, anon, authenticated;

create or replace view admin.clients as
select
  u.email,
  p.prenom,
  p.departement,
  array_to_string(p.pratiques, ', ') as pratiques,
  p.tranche_age,
  p.accord_emails,
  p.accord_emails_le,
  u.email_confirmed_at is not null as email_confirme,
  u.created_at as inscrit_le,
  u.last_sign_in_at as derniere_connexion,
  (select count(*) from public.spots_prives s where s.proprietaire = u.id) as nombre_spots,
  (select count(*) from public.rapports r where r.utilisateur = u.id) as nombre_retours
from auth.users u
left join public.profils p on p.id = u.id
order by u.created_at desc;

revoke all on admin.clients from public, anon, authenticated;

-- Spots proposés au partage, du plus ancien au plus récent. Pour valider : dans Table Editor >
-- spots_prives, filtrer « partage » = en_attente et remplacer la valeur par publie (ou refuse).
create or replace view admin.spots_a_valider as
select
  s.partage_id,
  s.nom,
  s.lat,
  s.lon,
  s.region,
  s.profondeur_m,
  s.fond,
  s.partage_demande_le as propose_le,
  'https://www.openstreetmap.org/?mlat=' || s.lat || '&mlon=' || s.lon || '#map=15/' || s.lat || '/' || s.lon as carte,
  u.email as propose_par
from public.spots_prives s
join auth.users u on u.id = s.proprietaire
where s.partage = 'en_attente'
order by s.partage_demande_le;

revoke all on admin.spots_a_valider from public, anon, authenticated;

-- Profils manquants pour des comptes créés avant ce script (repris des informations d'inscription)
insert into public.profils (id, prenom, departement, pratiques, tranche_age, accord_emails)
select
  u.id,
  left(nullif(trim(u.raw_user_meta_data ->> 'prenom'), ''), 50),
  case when upper(u.raw_user_meta_data ->> 'departement') ~ '^(0[1-9]|[1-8][0-9]|9[0-5]|2A|2B|97[1-6]|99)$'
       then upper(u.raw_user_meta_data ->> 'departement') end,
  coalesce((select array_agg(x) from jsonb_array_elements_text(coalesce(u.raw_user_meta_data -> 'pratiques', '[]'::jsonb)) as x
            where x in ('chasse', 'apnee', 'plongee', 'photo', 'randonnee')), '{}'),
  case when u.raw_user_meta_data ->> 'tranche_age' in ('15-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+')
       then u.raw_user_meta_data ->> 'tranche_age' end,
  coalesce(u.raw_user_meta_data ->> 'accord_emails', 'false') = 'true'
from auth.users u
on conflict (id) do nothing;
