-- Vérifie le partage des spots : proposition, validation par l'éditeur, anonymat, retrait.
-- À lancer après preparer.sql et schema.sql. Toute assertion fausse arrête le script.
\set ON_ERROR_STOP on

insert into auth.users (id, email, raw_user_meta_data) values
  ('33333333-3333-3333-3333-333333333333', 'auteur@exemple.fr', '{"prenom": "Auteur"}'),
  ('44444444-4444-4444-4444-444444444444', 'lecteur@exemple.fr', '{"prenom": "Lecteur"}');

-- L'auteur propose un spot (il ne peut pas le publier lui-même ni choisir son identifiant public)
set role authenticated;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond, partage, partage_id)
values ('prive-p', '33333333-3333-3333-3333-333333333333', 'Roche du large', 47.5, -3.2, 'atlantique', 270, 90, 8, 'roche',
        'publie', '00000000-0000-0000-0000-000000000001');
insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
values ('prive-q', '33333333-3333-3333-3333-333333333333', 'Coin secret', 47.6, -3.3, 'atlantique', 200, 90, 6, 'sable');

do $$
declare s record;
begin
  select * into s from public.spots_prives where id = 'prive-p';
  assert s.partage = 'en_attente', 'proposé, pas publié : ' || s.partage;
  assert s.partage_demande_le is not null, 'date de la proposition';
  assert s.partage_id <> '00000000-0000-0000-0000-000000000001', 'identifiant public imposé par la base';
  assert (select partage from public.spots_prives where id = 'prive-q') = 'prive', 'privé par défaut';
end $$;

-- Un autre compte ne voit rien tant que l'éditeur n'a pas validé
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$
begin
  assert (select count(*) from public.spots_communaute()) = 0, 'rien de visible avant validation';
  assert (select count(*) from public.spots_prives) = 0, 'les spots des autres restent invisibles';
end $$;

-- L'éditeur valide depuis le tableau de bord (pas de compte connecté)
reset role;
reset request.jwt.claim.sub;
do $$
begin
  assert (select count(*) from admin.spots_a_valider) = 1, 'un spot à valider';
  assert (select propose_par from admin.spots_a_valider) = 'auteur@exemple.fr', 'auteur connu de l''éditeur';
end $$;
update public.spots_prives set partage = 'publie' where id = 'prive-p';

set role authenticated;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$
declare c record;
begin
  assert (select count(*) from public.spots_communaute()) = 1, 'visible après validation';
  select * into c from public.spots_communaute();
  assert c.nom = 'Roche du large' and c.fond = 'roche', 'caractéristiques publiées';
  assert c.id is not null and c.id::text <> '33333333-3333-3333-3333-333333333333', 'identifiant public, pas celui du compte';
end $$;

-- Sans compte : rien
reset role;
set role anon;
do $$
begin
  begin
    perform * from public.spots_communaute();
    raise exception 'ÉCHEC : spots partagés lisibles sans compte';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;

-- L'auteur synchronise sans rien changer (comme l'application) : le spot reste publié
set role authenticated;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond, partage)
values ('prive-p', '33333333-3333-3333-3333-333333333333', 'Roche du large', 47.5, -3.2, 'atlantique', 270, 90, 8, 'roche', 'en_attente')
on conflict (proprietaire, id) do update set nom = excluded.nom, lat = excluded.lat, lon = excluded.lon,
  orientation_deg = excluded.orientation_deg, ouverture_deg = excluded.ouverture_deg, profondeur_m = excluded.profondeur_m,
  fond = excluded.fond, partage = excluded.partage;
do $$
begin
  assert (select partage from public.spots_prives where id = 'prive-p') = 'publie', 'reste publié sans modification';
end $$;

-- Une ancienne version de l'application, qui n'envoie pas « partage », ne change rien non plus
insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
values ('prive-p', '33333333-3333-3333-3333-333333333333', 'Roche du large', 47.5, -3.2, 'atlantique', 270, 90, 8, 'roche')
on conflict (proprietaire, id) do update set nom = excluded.nom, profondeur_m = excluded.profondeur_m;
do $$
begin
  assert (select partage from public.spots_prives where id = 'prive-p') = 'publie', 'ancienne version sans effet';
end $$;

-- Spot déplacé : il repasse en attente et disparaît pour les autres
update public.spots_prives set lat = 47.51, partage = 'en_attente' where id = 'prive-p';
do $$
begin
  assert (select partage from public.spots_prives where id = 'prive-p') = 'en_attente', 'modifié : à revalider';
end $$;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$
begin
  assert (select count(*) from public.spots_communaute()) = 0, 'invisible pendant la nouvelle validation';
end $$;

-- Validé de nouveau, puis retiré par son auteur
reset role;
reset request.jwt.claim.sub;
update public.spots_prives set partage = 'publie' where id = 'prive-p';
set role authenticated;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
update public.spots_prives set partage = 'prive', partage_id = '00000000-0000-0000-0000-000000000002' where id = 'prive-p';
do $$
begin
  assert (select partage from public.spots_prives where id = 'prive-p') = 'prive', 'retiré par son auteur';
  assert (select partage_id from public.spots_prives where id = 'prive-p') <> '00000000-0000-0000-0000-000000000002', 'identifiant public inchangé';
end $$;
set request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
do $$
begin
  assert (select count(*) from public.spots_communaute()) = 0, 'plus visible après retrait';
end $$;

-- Refusé : une nouvelle proposition identique reste refusée
reset role;
reset request.jwt.claim.sub;
update public.spots_prives set partage = 'refuse' where id = 'prive-q';
set role authenticated;
set request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
update public.spots_prives set partage = 'en_attente' where id = 'prive-q';
do $$
begin
  assert (select partage from public.spots_prives where id = 'prive-q') = 'refuse', 'refus maintenu sans modification';
end $$;
reset role;
reset request.jwt.claim.sub;

select 'partage des spots vérifié' as resultat;
