---
name: Incident d'exploitation
about: Consigner un incident détecté par une alerte de la vigie
title: "[incident] "
labels: ["incident"]
---

Remplir chaque section en texte. Ne coller aucun secret, aucun jeton, aucune valeur du `.env`.

## Symptôme

Ce qui est observé, en une ou deux phrases.

## Alerte reçue

Numéro AL-n, ou « aucune » si l'incident n'a pas été signalé par une alerte.

## Heure

Date et heure de l'alerte, avec le fuseau.

## Environnement

`staging` ou `production`.

## Requête KQL lancée

Nom du fichier `.kql` de la fiche et valeur lue dans la colonne `valeur`.

## Cause

La cause nommée, ou « inconnue » avec ce qui a été écarté.

## Correction

Action menée (voir la section 5 ou 6 de `docs/exploitation.md`) et son résultat.

## PR

Lien de la pull request qui corrige, ou « aucune » avec la raison.
