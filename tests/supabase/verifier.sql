-- Vérifie le comportement de supabase/schema.sql : profils, règles d'accès, suppression, purge.
-- Toute assertion fausse arrête le script avec une erreur explicite.
\set ON_ERROR_STOP on

-- Deux comptes, créés comme le ferait l'inscription
insert into auth.users (id, email, raw_user_meta_data) values
  ('11111111-1111-1111-1111-111111111111', 'nathan@exemple.fr',
   '{"prenom": "Nathan", "departement": "29", "pratiques": ["chasse", "apnee", "inconnue"], "tranche_age": "18-24", "accord_emails": true}'),
  ('22222222-2222-2222-2222-222222222222', 'lou@exemple.fr',
   '{"prenom": "Lou", "departement": "2a", "pratiques": [], "tranche_age": "12-14", "accord_emails": false}');

do $$
declare p record;
begin
  select * into p from public.profils where id = '11111111-1111-1111-1111-111111111111';
  assert p.prenom = 'Nathan', 'prénom';
  assert p.departement = '29', 'département';
  assert p.pratiques = array['chasse', 'apnee'], 'pratiques filtrées';
  assert p.tranche_age = '18-24', 'tranche d''âge';
  assert p.accord_emails and p.accord_emails_le is not null, 'accord e-mails daté';
  select * into p from public.profils where id = '22222222-2222-2222-2222-222222222222';
  assert p.departement = '2A', 'département corse en majuscules';
  assert p.tranche_age is null, 'tranche d''âge invalide ignorée';
  assert not p.accord_emails and p.accord_emails_le is null, 'pas d''accord par défaut';
end $$;

-- Nathan connecté
set role authenticated;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

insert into public.spots_prives (id, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
values ('prive-a', 'Ma crique', 47.49, -3.2, 'atlantique', 270, 90, 8, 'roche');
-- Mise à jour par « upsert », comme l'application
insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
values ('prive-a', '11111111-1111-1111-1111-111111111111', 'Ma crique 2', 47.49, -3.2, 'atlantique', 270, 90, 9, 'roche')
on conflict (proprietaire, id) do update set nom = excluded.nom, profondeur_m = excluded.profondeur_m;
insert into public.favoris (point_id) values ('ref-groix');
insert into public.rapports (spot_id, visibilite_m, observe_le) values ('ref-groix', 6.5, now() - interval '2 hours');
update public.profils set accord_emails = false, departement = '56' where id = '11111111-1111-1111-1111-111111111111';

do $$
begin
  assert (select count(*) from public.spots_prives) = 1, 'un spot';
  assert (select nom from public.spots_prives) = 'Ma crique 2', 'spot mis à jour';
  assert (select count(*) from public.favoris) = 1, 'un favori';
  assert (select accord_emails_le from public.profils) is null, 'retrait de l''accord daté';
  assert (select count(*) from public.profils) = 1, 'ne voit que son profil';
end $$;

-- Ce qu'un compte ne doit pas pouvoir faire
do $$
begin
  begin
    insert into public.spots_prives (id, proprietaire, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond)
    values ('intrus', '22222222-2222-2222-2222-222222222222', 'X', 47, -3, 'atlantique', 0, 90, 5, 'sable');
    raise exception 'ÉCHEC : spot créé au nom d''un autre compte';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.rapports (spot_id, visibilite_m, observe_le) values ('ref-groix', 5, now() - interval '5 days');
    raise exception 'ÉCHEC : retour trop ancien accepté';
  exception when insufficient_privilege then null;
  end;
  begin
    perform count(*) from public.rapports;
    raise exception 'ÉCHEC : lecture des retours autorisée';
  exception when insufficient_privilege then null;
  end;
  begin
    perform * from admin.clients;
    raise exception 'ÉCHEC : liste des clients lisible par un compte';
  exception when insufficient_privilege then null;
  end;
  begin
    perform public.purger_comptes_inactifs();
    raise exception 'ÉCHEC : purge appelable par un compte';
  exception when insufficient_privilege then null;
  end;
  begin
    update public.profils set accord_emails_le = now() - interval '9 years';
    raise exception 'ÉCHEC : date d''accord modifiable';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Lou ne voit rien de Nathan
set request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';
do $$
begin
  assert (select count(*) from public.spots_prives) = 0, 'spots d''autrui invisibles';
  assert (select count(*) from public.favoris) = 0, 'favoris d''autrui invisibles';
  update public.spots_prives set nom = 'piraté';
  delete from public.favoris;
end $$;

-- Visiteur non connecté : aucun accès
set role anon;
reset request.jwt.claim.sub;
do $$
begin
  begin
    perform count(*) from public.profils;
    raise exception 'ÉCHEC : profils lisibles sans compte';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.rapports (spot_id, visibilite_m, observe_le) values ('ref-groix', 5, now());
    raise exception 'ÉCHEC : retour anonyme accepté';
  exception when insufficient_privilege then null;
  end;
end $$;

-- L'éditeur (administrateur) voit la liste des clients
reset role;
do $$
begin
  assert (select count(*) from admin.clients) = 2, 'deux clients';
  assert (select nombre_spots from admin.clients where email = 'nathan@exemple.fr') = 1, 'nombre de spots';
  assert (select nombre_retours from admin.clients where email = 'nathan@exemple.fr') = 1, 'nombre de retours';
  assert (select departement from admin.clients where email = 'nathan@exemple.fr') = '56', 'profil à jour';
  assert (select nom from public.spots_prives where id = 'prive-a') = 'Ma crique 2', 'spot intact malgré Lou';
  assert (select count(*) from public.favoris) = 1, 'favori intact malgré Lou';
end $$;

-- Suppression de son compte par Nathan : profil, spots et favoris effacés, retours anonymisés
set role authenticated;
set request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
select public.supprimer_mon_compte();
reset role;
do $$
begin
  assert (select count(*) from auth.users) = 1, 'compte supprimé';
  assert (select count(*) from public.spots_prives) = 0, 'spots supprimés';
  assert (select count(*) from public.favoris) = 0, 'favoris supprimés';
  assert (select count(*) from public.profils) = 1, 'profil supprimé';
  assert (select count(*) from public.rapports where utilisateur is null) = 1, 'retour gardé sans lien';
end $$;

-- Purge des comptes inactifs depuis 3 ans (clé secrète)
update auth.users set created_at = now() - interval '4 years', last_sign_in_at = null;
set role service_role;
do $$
begin
  assert public.purger_comptes_inactifs() = 1, 'un compte inactif purgé';
end $$;
reset role;

select 'schéma Supabase vérifié' as resultat;
