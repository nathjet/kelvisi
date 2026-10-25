-- Vérifie les alertes sur les favoris : niveau d'alerte, abonnements des appareils, alertes envoyées,
-- clés de notification inaccessibles aux comptes. À lancer après preparer.sql et schema.sql.
\set ON_ERROR_STOP on

insert into auth.users (id, email) values
  ('55555555-5555-5555-5555-555555555555', 'alerte@exemple.fr'),
  ('66666666-6666-6666-6666-666666666666', 'voisin@exemple.fr');

set role authenticated;
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
insert into public.favoris (point_id) values ('ref-groix'), ('ref-glenan');
update public.favoris set alerte = 'bonne' where point_id = 'ref-groix';
update public.favoris set alerte = 'excellente' where point_id = 'ref-glenan';
update public.favoris set alerte = null where point_id = 'ref-glenan';
-- Alerte sur un spot privé, sans toucher à son partage
insert into public.spots_prives (id, nom, lat, lon, region, orientation_deg, ouverture_deg, profondeur_m, fond, partage)
values ('prive-alerte', 'Ma crique', 47.49, -3.2, 'atlantique', 270, 90, 8, 'roche', 'en_attente');
update public.spots_prives set alerte = 'bonne' where id = 'prive-alerte';
insert into public.abonnements_push (endpoint, p256dh, auth)
values ('https://fcm.googleapis.com/fcm/send/abc', 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6', 'BTBZMqHH6r4Tts7J');

do $$
begin
  assert (select alerte from public.favoris where point_id = 'ref-groix') = 'bonne', 'alerte choisie';
  assert (select alerte from public.favoris where point_id = 'ref-glenan') is null, 'alerte retirée';
  assert (select count(*) from public.abonnements_push) = 1, 'un appareil abonné';
  assert (select alerte from public.spots_prives where id = 'prive-alerte') = 'bonne', 'alerte sur un spot privé';
  assert (select partage from public.spots_prives where id = 'prive-alerte') = 'en_attente', 'partage inchangé par l''alerte';
  begin
    update public.spots_prives set alerte = 'parfois' where id = 'prive-alerte';
    raise exception 'ÉCHEC : niveau d''alerte inconnu accepté sur un spot';
  exception when check_violation then null;
  end;
  -- Valeurs refusées
  begin
    update public.favoris set alerte = 'moyenne' where point_id = 'ref-groix';
    raise exception 'ÉCHEC : niveau d''alerte inconnu accepté';
  exception when check_violation then null;
  end;
  begin
    update public.favoris set point_id = 'autre' where point_id = 'ref-groix';
    raise exception 'ÉCHEC : favori renommé';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.abonnements_push (endpoint, p256dh, auth) values ('http://exemple.fr/x', 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV', 'BTBZMqHH6r4T');
    raise exception 'ÉCHEC : adresse de notification non chiffrée acceptée';
  exception when check_violation then null;
  end;
  begin
    insert into public.abonnements_push (proprietaire, endpoint, p256dh, auth)
    values ('66666666-6666-6666-6666-666666666666', 'https://exemple.fr/y', 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV', 'BTBZMqHH6r4T');
    raise exception 'ÉCHEC : appareil abonné au nom d''un autre compte';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.alertes_envoyees (proprietaire, point_id, jour) values ('55555555-5555-5555-5555-555555555555', 'ref-groix', current_date);
    raise exception 'ÉCHEC : un compte écrit dans les alertes envoyées';
  exception when insufficient_privilege then null;
  end;
  begin
    perform * from public.cles_push;
    raise exception 'ÉCHEC : clés de notification lisibles par un compte';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Dix appareils au plus
do $$
begin
  for i in 2..10 loop
    insert into public.abonnements_push (endpoint, p256dh, auth) values ('https://push.exemple.fr/' || i, 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV', 'BTBZMqHH6r4T');
  end loop;
  begin
    insert into public.abonnements_push (endpoint, p256dh, auth) values ('https://push.exemple.fr/11', 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV', 'BTBZMqHH6r4T');
    raise exception 'ÉCHEC : onzième appareil accepté';
  exception when raise_exception then
    if sqlerrm like 'ÉCHEC%' then raise; end if;
  end;
end $$;

-- Sans compte : rien
reset role;
set role anon;
do $$
begin
  begin
    perform * from public.abonnements_push;
    raise exception 'ÉCHEC : abonnements lisibles sans compte';
  exception when insufficient_privilege then null;
  end;
  begin
    perform * from public.alertes_envoyees;
    raise exception 'ÉCHEC : alertes envoyées lisibles sans compte';
  exception when insufficient_privilege then null;
  end;
end $$;

-- Le calcul horaire (clé secrète) crée les clés et note les alertes envoyées
reset role;
insert into public.cles_push (publique, privee) values ('PUBLIQUE', 'PRIVEE');
insert into public.alertes_envoyees (proprietaire, point_id, jour) values
  ('55555555-5555-5555-5555-555555555555', 'ref-groix', current_date),
  ('55555555-5555-5555-5555-555555555555', 'ref-groix', current_date - 40);
do $$
begin
  begin
    insert into public.cles_push (id, publique, privee) values (2, 'X', 'Y');
    raise exception 'ÉCHEC : deuxième jeu de clés';
  exception when check_violation then null;
  end;
end $$;

-- Chacun ne voit que ses alertes envoyées
set role authenticated;
set request.jwt.claim.sub = '66666666-6666-6666-6666-666666666666';
do $$
begin
  assert (select count(*) from public.alertes_envoyees) = 0, 'alertes d''autrui invisibles';
  assert (select count(*) from public.abonnements_push) = 0, 'abonnements d''autrui invisibles';
  assert (select count(*) from public.favoris) = 0, 'favoris d''autrui invisibles';
end $$;
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
do $$
begin
  assert (select count(*) from public.alertes_envoyees) = 2, 'ses alertes envoyées';
end $$;

-- Purge quotidienne : alertes envoyées de plus de 30 jours effacées
reset role;
set role service_role;
select public.purger_comptes_inactifs();
reset role;
do $$
begin
  assert (select count(*) from public.alertes_envoyees) = 1, 'ancienne alerte purgée';
end $$;

-- Suppression du compte : favoris, appareils et alertes envoyées partent avec lui
set role authenticated;
set request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
select public.supprimer_mon_compte();
reset role;
do $$
begin
  assert (select count(*) from public.abonnements_push) = 0, 'appareils supprimés';
  assert (select count(*) from public.alertes_envoyees) = 0, 'alertes envoyées supprimées';
  assert (select count(*) from public.favoris where proprietaire = '55555555-5555-5555-5555-555555555555') = 0, 'favoris supprimés';
  assert (select count(*) from public.spots_prives where proprietaire = '55555555-5555-5555-5555-555555555555') = 0, 'spots supprimés';
end $$;

select 'alertes vérifiées' as resultat;
